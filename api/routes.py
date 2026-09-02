"""
API Routing Module
==================
Defines all FastAPI HTTP REST endpoints and Server-Sent Event (SSE) streaming paths.
This module controls:
1. Ingestion triggers: Paste Google Drive links/folders.
2. Checking link credentials: Verify public availability or token requirements.
3. Server-Sent Events (SSE) streaming: Yield file downloads in real-time.
4. Concurrency operations: Leverage asyncio network concurrency to ingest multiple documents simultaneously.
5. Search interface: Point Omni-Search requests at the Chroma database.
6. DB Maintenance: Clear namespaces and physically reclaim storage space.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
import json
from pydantic import BaseModel, Field
import re
import asyncio
import time
import os
import logging
from typing import Optional, List
from confluent_kafka import Producer

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
from engine.connectors import get_connector_for_url
from api.security import require_api_key
from engine.rag_core import (
    ingest_texts_async, 
    query_master_database, 
    list_namespaces, 
    purge_namespace,
    purge_namespaces,
    verify_index_ready,
    file_exists_in_db
)

from api.auth import router as auth_router
from api.browser import router as browser_router

router = APIRouter(dependencies=[Depends(require_api_key)])
router.include_router(auth_router, prefix="/auth")
router.include_router(browser_router)

# =====================================================================
# PYDANTIC SCHEMAS (Request/Response Models)
# =====================================================================

class LoadRequest(BaseModel):
    """Schema for loading a single file/folder Google Drive URL."""
    link: str = Field(..., description="The raw Google Drive share URL.")
    access_token: Optional[str] = Field(None, description="Optional Google OAuth2 credentials token.")

class EnqueueRequest(BaseModel):
    """Schema for queueing a file/folder for background processing."""
    link: str = Field(..., description="The raw Google Drive/Dropbox share URL.")
    access_token: Optional[str] = Field(None, description="Optional OAuth2 credentials token.")

class PickerItem(BaseModel):
    id: str
    type: str

class EnqueueItemsRequest(BaseModel):
    """Schema for queueing selected items from the native File Picker."""
    provider: str = Field(..., description="The cloud provider (e.g. google, dropbox)")
    items: List[PickerItem] = Field(..., description="List of native file or folder objects to ingest.")
    access_token: Optional[str] = Field(None, description="OAuth2 credentials token.")

class QueryRequest(BaseModel):
    """Schema for querying the vector search RAG bot."""
    query_text: str = Field(..., description="The user's question or search query.")
    n_results: int = Field(4, description="Count of relevant chunks to retrieve (retained for backward compatibility).")
    namespaces: Optional[List[str]] = Field(None, description="Optional list of specific namespaces (folders) to restrict the search to, preventing cross-tenant data leaks.")

class PurgeRequest(BaseModel):
    """Schema for deleting a single database collection."""
    namespace: str = Field(..., description="The namespace identifier to delete.")

class PurgeBatchRequest(BaseModel):
    """Schema for deleting multiple database collections in one batch."""
    namespaces: list[str] = Field(..., description="List of namespace identifiers to delete.")

class CheckLinkRequest(BaseModel):
    """Schema for preflight verification of Google Drive links."""
    link: str = Field(..., description="The Google Drive share URL to verify.")
    access_token: Optional[str] = Field(None, description="Optional Google OAuth2 token.")

class HealthCheckFlags(BaseModel):
    kafka_connected: bool
    vector_db_connected: bool
    llm_configured: bool
    issues: List[str]

class HealthCheckResponse(BaseModel):
    status: str
    flags: HealthCheckFlags

# =====================================================================
# API ENDPOINTS
# =====================================================================

@router.post("/check_link")
def check_link(request: CheckLinkRequest):
    """
    **What**: "Preflights" a URL to check if it's healthy, if it's a file or folder, and if it requires an OAuth password before attempting to download it.
    
    **How**: Routes the URL to the correct connector (Drive/Dropbox/Sharepoint) and uses the cloud API's metadata endpoint to check file permissions.
    
    **Why**: If a user pastes a private Google Drive link without providing an access token, trying to download it will crash the system. This route detects that instantly so the frontend UI can prompt the user for a token gracefully.
    """
    try:
        connector = get_connector_for_url(request.link)
        result = connector.check_link(request.link, request.access_token)
        # Map 'public' status to 'valid' for frontend UI compatibility
        status_val = "valid" if result.status == "public" else result.status
        return {"status": "success", "info": {"status": status_val, "type": result.type, "requires_auth": result.requires_auth, "message": result.message}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/load_link")
def load_link(request: LoadRequest):
    """
    Synchronous Ingestion Route.
    """
    try:
        connector = get_connector_for_url(request.link)
        result = connector.check_link(request.link, request.access_token)
        
        if result.type == "folder":
            if result.requires_auth and not request.access_token:
                raise ValueError("Folder ingestion requires an Access Token.")
            files_data = list(connector.stream_folder(request.link, request.access_token))
            # print(files_data)
            for f in files_data:
                if f.get("status") in ["metadata", "error"]:
                    continue
                logger.debug(f"Queuing file: {f}")
                f["source"] = connector.source
                print(f)
            return {"status": "success", "files": files_data}
        else:
            file_data = connector.stream_file(request.link, request.access_token)
            file_data.update({"id": request.link, "link": request.link, "source": connector.source})
            return {"status": "success", "files": [file_data]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

_producer = None

def get_producer():
    global _producer
    if _producer is None:
        _producer = Producer({
            'bootstrap.servers': os.getenv("KAFKA_BROKERS", "localhost:9092"),
            'message.max.bytes': 52428800
        })
    return _producer

@router.post("/enqueue_link")
def enqueue_link_endpoint(request: EnqueueRequest):
    """
    Pushes a URL to the Kafka background worker for downloading and vectorization.
    """
    try:
        producer = get_producer()
        topic = os.getenv("KAFKA_VECTORIZE_TOPIC", "vectorize-tasks")
        payload = json.dumps({
            "link": request.link,
            "access_token": request.access_token
        }).encode('utf-8')
        producer.produce(topic, payload)
        producer.flush()
        return {"status": "success", "message": "Ingestion task queued in background."}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/enqueue_items")
def enqueue_items_endpoint(request: EnqueueItemsRequest):
    """
    Pushes native file IDs to the Kafka background worker by constructing URLs.
    """
    try:
        producer = get_producer()
        topic = os.getenv("KAFKA_VECTORIZE_TOPIC", "vectorize-tasks")
        count = 0
        
        for item in request.items:
            # Construct standard URLs to maintain compatibility with the existing worker logic
            if request.provider == "google":
                if item.type == "folder":
                    link = f"https://drive.google.com/drive/folders/{item.id}"
                else:
                    link = f"https://drive.google.com/file/d/{item.id}/view"
            elif request.provider == "dropbox":
                link = f"https://www.dropbox.com/s/{item.id}" # Mock URL, worker handles this natively later
            else:
                link = item.id # Fallback
                
            payload = json.dumps({
                "link": link,
                "access_token": request.access_token
            }).encode('utf-8')
            producer.produce(topic, payload)
            count += 1
            
        producer.flush()
        return {"status": "success", "message": f"Queued {count} items for background ingestion."}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/namespaces")
def get_namespaces_endpoint():
    """
    Lists Active Namespaces.
    """
    try:
        return {"status": "success", "namespaces": list_namespaces()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream_progress")
async def stream_progress():
    """
    Server-Sent Events (SSE) endpoint to stream real-time background worker progress to the frontend.
    """
    async def event_generator():
        log_file_path = "/app/local_chroma_db/worker_progress.log"
        # Ensure file exists
        if not os.path.exists(log_file_path):
            open(log_file_path, "w").close()
            
        with open(log_file_path, "r") as f:
            # Seek to end so we only get new progress for this active session
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    await asyncio.sleep(0.2)
                    continue
                if "[Progress]" in line:
                    yield f"data: {line}\n\n"
                    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/query")
def query_endpoint(request: QueryRequest):
    """
    RAG Bot Omni-Search.
    
    Accepts search queries, queries Chroma DB for relevant chunks, and returns
    context-aware answers from GPT-4o-mini.
    """
    try:
        results = query_master_database(
            query_text=request.query_text, 
            n_results=request.n_results,
            namespaces=request.namespaces
        )
        return {"status": "success", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/purge")
def purge_endpoint(request: PurgeRequest):
    """
    Purges Collection.
    
    Deletes vectors belonging to the specified namespace and runs SQLite `VACUUM`
    to reclaim unused disk space.
    """
    try:
        if purge_namespace(request.namespace):
            return {"status": "success", "message": f"Database '{request.namespace}' purged successfully."}
        return {"status": "error", "message": "Failed to purge database."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/purge_batch")
def purge_batch_namespaces(request: PurgeBatchRequest):
    """
    Deletes multiple vector databases and runs vacuum only once.
    """
    try:
        if purge_namespaces(request.namespaces):
            return {"status": "success", "message": f"Successfully deleted {len(request.namespaces)} databases."}
        return {"status": "error", "message": "Failed to purge databases."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health", response_model=HealthCheckResponse)
def health_check_endpoint():
    """
    Flag system endpoint to verify the health of all pipeline components.
    """
    flags = {
        "kafka_connected": False,
        "vector_db_connected": False,
        "llm_configured": False,
        "issues": []
    }
    
    # 1. Check Vector DB
    try:
        list_namespaces()
        flags["vector_db_connected"] = True
    except Exception as e:
        flags["issues"].append(f"Vector DB connection failed: {e}")
        
    # 2. Check LLM Configuration
    if os.getenv("OPENAI_API_KEY"):
        flags["llm_configured"] = True
    else:
        flags["issues"].append("OPENAI_API_KEY is not set in the environment")
        
    # 3. Check Kafka
    try:
        producer = get_producer()
        topic = os.getenv("KAFKA_VECTORIZE_TOPIC", "vectorize-tasks")
        # Query metadata with a small timeout to avoid blocking forever if down
        metadata = producer.list_topics(timeout=3)
        if metadata.topics:
            flags["kafka_connected"] = True
        else:
            flags["issues"].append(f"Kafka broker returned no topics")
    except Exception as e:
        flags["issues"].append(f"Kafka connection failed: {e}")
        
    status = "healthy" if not flags["issues"] else "degraded"
    return HealthCheckResponse(status=status, flags=HealthCheckFlags(**flags))
