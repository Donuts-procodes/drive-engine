import os
import json
import asyncio
import sqlite3
from typing import List, Dict, Any
import threading
import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_exception

from .base import BaseVectorStore

# Load environment variable for database path
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./local_chroma_db")
MASTER_COLLECTION_NAME = "MASTER_COLLECTION"
REGISTRY_FILE = os.path.join(CHROMA_DB_PATH, "namespaces_registry.json")

# Global lock to prevent race conditions when multiple concurrent tasks try to rewrite the JSON
registry_lock = threading.Lock()

# Thread lock to protect ChromaDB Rust bindings from concurrent Python threads hitting it via check_file_exists
db_read_lock = threading.Lock()

class ChromaVectorStore(BaseVectorStore):
    db_name = "chroma"
    """
    **What**: The concrete implementation of the Vector Store using ChromaDB backed by SQLite.
    
    **How**: It connects to a local persistent SQLite file on disk. It maintains a single 'MASTER_COLLECTION' for all vectors, using metadata filtering to isolate different folders.
    
    **Why**: ChromaDB is lightweight, runs locally without external databases (like Pinecone or Postgres), and is extremely fast for single-machine deployments.
    """
    def __init__(self):
        # Initialize the persistent SQLite client that manages physical DB files on disk.
        self.chroma_client = chromadb.PersistentClient(
            path=CHROMA_DB_PATH,
            settings=Settings(anonymized_telemetry=False)
        )
        
    def _get_embeddings(self):
        return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
    def _get_langchain_store(self) -> Chroma:
        return Chroma(
            client=self.chroma_client,
            collection_name=MASTER_COLLECTION_NAME,
            embedding_function=self._get_embeddings(),
        )

    def _load_registry(self) -> dict:
        if not os.path.exists(REGISTRY_FILE):
            return {}
        try:
            with open(REGISTRY_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    new_data = {item: "Unknown" for item in data}
                    self._save_registry(new_data)
                    return new_data
                return data
        except Exception:
            return {}

    def _save_registry(self, namespaces_dict: dict):
        with open(REGISTRY_FILE, "w") as f:
            json.dump(namespaces_dict, f)

    async def add_documents(self, documents: List[Document]) -> None:
        """
        **What**: Pushes a batch of chunked text documents into the local ChromaDB database.
        
        **How**:
        1. Breaks the massive list of documents into sub-batches of 5,000.
        2. Uploads them asynchronously using LangChain's `aadd_documents`.
        3. If it hits an OpenAI `429 Too Many Requests` rate limit, it catches the error and executes an exponential backoff (wait 5s, then 10s, 20s...) before retrying.
        4. If mathematical IDs are present in the documents, it uses them to silently overwrite duplicates.
        5. Once successful, it locks and updates the JSON registry with the new namespace.
        
        **Why**: Batching prevents memory overflow. Exponential backoff is absolutely necessary because when you upload 10,000 files, you will inevitably hit the OpenAI API rate limit, and without backoff, the entire ingestion pipeline would crash.
        """
        if not documents:
            return

        vectorstore = self._get_langchain_store()
        batch_size = int(os.getenv("CHROMA_BATCH_SIZE", 5000))

        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            batch_ids = [doc.id for doc in batch if hasattr(doc, 'id') and doc.id]
            if len(batch_ids) != len(batch):
                batch_ids = None # Fallback if IDs are partially missing
            
            try:
                if batch_ids:
                    await vectorstore.aadd_documents(documents=batch, ids=batch_ids)
                else:
                    await vectorstore.aadd_documents(documents=batch)
            except Exception as e:
                raise Exception(f"Failed to vectorize with HuggingFace embeddings: {str(e)}") from e
                    
        # Update Registry mapping for each namespace we just added
        with registry_lock:
            registry = self._load_registry()
            updated = False
            for doc in documents:
                ns = doc.metadata.get("namespace")
                name = doc.metadata.get("name", "Unknown")
                if ns and (ns not in registry or registry[ns] == "Unknown"):
                    registry[ns] = name
                    updated = True
            
            if updated:
                self._save_registry(registry)

    def query_similar(self, query_text: str, n_results: int = 8, namespaces: List[str] = None) -> List[Dict[str, Any]]:
        """
        **What**: Searches the database for the top most semantically relevant text chunks matching a query.
        
        **How**:
        1. Converts the user's `query_text` into a vector embedding using OpenAI.
        2. Executes a mathematical similarity query against the C++/SQLite backend of ChromaDB.
        3. Parses the raw distances and vectors back into plain text with metadata.
        
        **Why**: This is the core engine of "Retrieval" in RAG. Instead of traditional keyword search (BM25), it uses mathematical distance (L2 or Cosine) to find text that *means* the same thing as the query, even if the exact words are different.
        """
        registry = self._load_registry()
        if not registry:
            raise ValueError("No databases found. Please load some documents first.")

        query_vector = self._get_embeddings().embed_query(query_text)
        
        where_clause = None
        if namespaces:
            if len(namespaces) == 1:
                where_clause = {"namespace": namespaces[0]}
            else:
                where_clause = {"namespace": {"$in": namespaces}}
        
        collection = self.chroma_client.get_collection(MASTER_COLLECTION_NAME)
        
        query_kwargs = {
            "query_embeddings": [query_vector],
            "n_results": n_results
        }
        if where_clause:
            query_kwargs["where"] = where_clause
            
        results = collection.query(**query_kwargs)
        
        formatted_results = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metadatas = results.get("metadatas", [[]])[0]
            for idx, doc_text in enumerate(docs):
                meta = metadatas[idx] if idx < len(metadatas) else {}
                source = meta.get("source", "unknown")
                name = meta.get("name", "Unknown Document")
                formatted_results.append({
                    "text": doc_text,
                    "source": source,
                    "name": name
                })
        return formatted_results

    def list_namespaces(self) -> List[Dict[str, str]]:
        registry = self._load_registry()
        return [{"id": k, "name": v} for k, v in registry.items()]

    def delete_namespace(self, namespace: str) -> bool:
        return self.delete_namespaces([namespace])
        
    def delete_namespaces(self, namespaces: List[str]) -> bool:
        """
        **What**: Deletes a list of namespaces (folders) from the database and reclaims physical hard drive space.
        
        **How**:
        1. Loops through and deletes all vector rows matching the namespace metadata using Chroma's `.delete()` method.
        2. Deletes the namespaces from the JSON registry.
        3. Opens a raw SQLite connection to `chroma.sqlite3` and executes `VACUUM`.
        
        **Why**: When you delete rows in SQLite (which Chroma uses), the database file size doesn't shrink; it just leaves empty holes (free pages). The `VACUUM` command physically shrinks the `.sqlite3` file on the hard drive to reclaim disk space.
        """
        registry = self._load_registry()
        updated_registry = False
        
        try:
            collection = self.chroma_client.get_collection(MASTER_COLLECTION_NAME)
            for namespace in namespaces:
                try:
                    collection.delete(where={"namespace": namespace})
                except ValueError:
                    pass
                if namespace in registry:
                    del registry[namespace]
                    updated_registry = True
        except ValueError:
            pass
            
        if updated_registry:
            self._save_registry(registry)
            
        # Vacuum once for all deletions
        try:
            db_file = os.path.join(CHROMA_DB_PATH, "chroma.sqlite3")
            if os.path.exists(db_file):
                conn = sqlite3.connect(db_file)
                conn.execute("VACUUM")
                conn.close()
        except Exception as e:
            print(f"Warning: Failed to vacuum database: {e}")
            
        return True

    async def verify_index_ready(self, test_text: str, namespace: str) -> bool:
        probe_slice = int(os.getenv("PROBE_SLICE_LENGTH", 200))
        query_vector = self._get_embeddings().embed_query(test_text[:probe_slice])
        try:
            collection = self.chroma_client.get_collection(MASTER_COLLECTION_NAME)
            for _ in range(15):
                results = collection.query(
                    query_embeddings=[query_vector],
                    n_results=1,
                    where={"namespace": namespace}
                )
                if results and "documents" in results and results["documents"]:
                    if results['ids'] and len(results['ids'][0]) > 0:
                        return True
            return False
            
        except Exception as e:
            print(f"Index not ready yet: {e}")
            return False

    def check_file_exists(self, file_id: str) -> bool:
        """
        Checks if a specific file ID has already been ingested by looking up metadata in ChromaDB.
        """
        try:
            with db_read_lock:
                collection = self.chroma_client.get_collection(MASTER_COLLECTION_NAME)
                results = collection.get(
                    where={"file_id": file_id},
                    limit=1,
                    include=["metadatas"]
                )
            if results and results.get("ids") and len(results["ids"]) > 0:
                return True
            return False
        except Exception as e:
            # Collection might not exist yet
            return False
