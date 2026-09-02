import os
import json
import logging
import tempfile
import threading
from typing import List, Dict, Any
from langchain_core.documents import Document
from langchain_milvus import Milvus
from langchain_huggingface import HuggingFaceEmbeddings

from pymilvus import connections, utility, Collection

from .base import BaseVectorStore

logger = logging.getLogger(__name__)

MILVUS_HOST = os.getenv("MILVUS_HOST", "milvus")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
MASTER_COLLECTION_NAME = "MASTER_COLLECTION"

# Reusing the JSON registry for namespace tracking to ensure UI compatibility
# Must be stored in the shared volume so API and Worker containers both see the updates!
REGISTRY_FILE = "/app/local_chroma_db/milvus_namespaces_registry.json"
registry_lock = threading.Lock()

class MilvusVectorStore(BaseVectorStore):
    db_name = "milvus"
    
    def __init__(self):
        self.connection_args = {"uri": f"http://{MILVUS_HOST}:{MILVUS_PORT}"}
        
        # Cache the embedding model and Langchain store to prevent loading weights from disk on every query/insertion
        self._embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self._langchain_store = Milvus(
            embedding_function=self._embeddings,
            collection_name=MASTER_COLLECTION_NAME,
            connection_args=self.connection_args,
            auto_id=True,
            enable_dynamic_field=True,
            drop_old=False
        )
        
    def _get_langchain_store(self) -> Milvus:
        return self._langchain_store

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
        except Exception as e:
            logger.warning("Failed to load namespace registry: %s", e)
            return {}

    def _save_registry(self, namespaces_dict: dict):
        """Atomic write: write to a temp file first, then rename to prevent corruption."""
        try:
            dir_name = os.path.dirname(REGISTRY_FILE)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json")
            with os.fdopen(fd, "w") as f:
                json.dump(namespaces_dict, f)
            os.replace(tmp_path, REGISTRY_FILE)
        except Exception as e:
            logger.error("Failed to save namespace registry: %s", e)

    async def add_documents(self, documents: List[Document]) -> None:
        if not documents:
            return

        vectorstore = self._get_langchain_store()
        
        # Batch size for Milvus
        batch_size = 1000
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            await vectorstore.aadd_documents(documents=batch)
                    
        with registry_lock:
            registry = self._load_registry()
            updated = False
            for doc in documents:
                ns = doc.metadata.get("namespace")
                name = doc.metadata.get("name", "Unknown")
                if ns and registry.get(ns) != name:
                    registry[ns] = name
                    updated = True
            if updated:
                self._save_registry(registry)

    def query_similar(self, query_text: str, n_results: int = 8, namespaces: List[str] = None) -> List[Dict[str, Any]]:
        vectorstore = self._get_langchain_store()
        
        expr = None
        if namespaces:
            ns_str = ", ".join([f"'{ns}'" for ns in namespaces])
            expr = f"namespace in [{ns_str}]"
            
        docs = vectorstore.similarity_search(query_text, k=n_results, expr=expr)
        
        results = []
        for d in docs:
            results.append({
                "text": d.page_content,
                "source": d.metadata.get("source", "Unknown"),
                "name": d.metadata.get("name", "Unknown"),
                "namespace": d.metadata.get("namespace")
            })
        return results

    def list_namespaces(self) -> List[Dict[str, str]]:
        with registry_lock:
            registry = self._load_registry()
        
        return [{"id": ns, "name": name} for ns, name in registry.items()]

    def _connect_pymilvus(self):
        connections.connect("default", uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")

    def delete_namespace(self, namespace: str) -> bool:
        return self.delete_namespaces([namespace])

    def delete_namespaces(self, namespaces: List[str]) -> bool:
        if not namespaces:
            return True
            
        try:
            self._connect_pymilvus()
            if not utility.has_collection(MASTER_COLLECTION_NAME):
                return True
                
            collection = Collection(MASTER_COLLECTION_NAME)
            
            ns_str = ", ".join([f"'{ns}'" for ns in namespaces])
            expr = f"namespace in [{ns_str}]"
            
            collection.delete(expr)
            
            with registry_lock:
                registry = self._load_registry()
                updated = False
                for ns in namespaces:
                    if ns in registry:
                        del registry[ns]
                        updated = True
                if updated:
                    self._save_registry(registry)
                    
            return True
        except Exception as e:
            print(f"Failed to delete namespaces from Milvus: {e}")
            return False

    async def verify_index_ready(self, test_text: str, namespace: str) -> bool:
        # Milvus needs an explicit flush to make data immediately searchable
        try:
            self._connect_pymilvus()
            if utility.has_collection(MASTER_COLLECTION_NAME):
                collection = Collection(MASTER_COLLECTION_NAME)
                collection.flush()
        except Exception as e:
            logger.warning("Failed to flush Milvus collection: %s", e)
        return True

    def check_file_exists(self, file_id: str) -> bool:
        try:
            self._connect_pymilvus()
            if not utility.has_collection(MASTER_COLLECTION_NAME):
                return False
                
            collection = Collection(MASTER_COLLECTION_NAME)
            
            expr = f"file_id == '{file_id}'"
            res = collection.query(expr=expr, output_fields=["file_id"], limit=1)
            
            return len(res) > 0
        except Exception as e:
            logger.warning("check_file_exists failed for '%s': %s", file_id, e)
            return False
