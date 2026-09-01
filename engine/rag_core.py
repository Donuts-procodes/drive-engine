"""
Core Retrieval-Augmented Generation (RAG) Module
===============================================
This module serves as the primary data storage and orchestration engine for the
RAG pipeline. It handles chunking documents, embedding texts, persisting chunks
in the Vector Store, querying the vector database,
feeding context to the RAG LLM engine, and cleaning/purging databases.

Design Architecture:
- Vector Store and LLM Engine are modular and dynamically loaded based on config.
"""

from langchain_core.documents import Document
# pyrefly: ignore [missing-import]
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import Optional, Dict, Any
import hashlib
import os

from .vectorstore import get_vector_store
from .llm import get_rag_engine

async def ingest_texts_async(texts: list, namespace: str, source: str, name: str = "Unknown", tika_metadata: Optional[Dict[str, Any]] = None, file_id: Optional[str] = None):
    """
    **What**: Takes raw text strings from downloaded files, splits them into indexable chunks, and pushes them to the Vector Database.
    
    **How**: 
    1. Wraps raw text in Langchain `Document` objects with metadata.
    2. Uses a `RecursiveCharacterTextSplitter` to slice text into 1,000-character overlapping chunks.
    3. Hashes the text into a deterministic SHA-256 ID to guarantee exact deduplication.
    4. Submits the batch asynchronously to the active Vector Store instance.
    
    **Why**: LLMs cannot ingest 50,000-word documents all at once due to context window limits. Slicing them into 1,000-character chunks with a 100-character overlap ensures that semantic meaning is preserved across chunk boundaries, making search retrieval highly accurate.
    
    Args:
        texts (list[str]): List of raw extracted text bodies to vectorize.
        namespace (str): The identifier (e.g. Folder ID) to isolate these documents in the DB.
        source (str): Source platform (e.g. 'google_drive').
        name (str): Human-readable name of the document.
        tika_metadata (dict): Optional metadata extracted by Apache Tika.
    """
    base_meta = {"namespace": namespace, "name": name, "source": source}
    if file_id:
        base_meta["file_id"] = file_id
        
    if tika_metadata:
        for k, v in tika_metadata.items():
            # ChromaDB only accepts string, integer, float or boolean values in metadata.
            # Convert everything else to string.
            safe_key = f"tika_{k}"
            if isinstance(v, (str, int, float, bool)):
                base_meta[safe_key] = v
            elif isinstance(v, list):
                base_meta[safe_key] = ", ".join([str(x) for x in v])
            else:
                base_meta[safe_key] = str(v)
                
    # Map raw text to list of LangChain Document structures with proper metadata
    docs = [Document(page_content=t, metadata=base_meta) for t in texts]
    
    # Instantiate text splitter
    chunk_size = int(os.getenv("CHUNK_SIZE", 1000))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", 100))
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    split_docs = splitter.split_documents(docs)
    
    # Generate deterministic IDs for exact deduplication
    unique_docs = {}
    for doc in split_docs:
        # The unique mathematical hash ensures that the exact same chunk from the exact same file 
        # resolves to the exact same ID, allowing ChromaDB to silently overwrite duplicates.
        unique_string = f"{namespace}_{doc.page_content}"
        doc.id = hashlib.sha256(unique_string.encode('utf-8')).hexdigest()
        if doc.id not in unique_docs:
            unique_docs[doc.id] = doc
            
    split_docs = list(unique_docs.values())
    
    vector_store = get_vector_store()
    await vector_store.add_documents(split_docs)

def query_master_database(query_text: str, n_results: int = 4, namespaces: list = None) -> str:
    """
    **What**: Triggers the entire RAG (Retrieval-Augmented Generation) pipeline.
    
    **How**: 
    1. Uses `get_vector_store` to perform a semantic similarity search across the vector database (optionally constrained to specific namespaces).
    2. Merges the most relevant results into a massive block of text.
    3. Feeds that block into the LLM as "Context".
    
    **Why**: This is what gives the AI its "memory" of your specific documents.
    """
    vector_store = get_vector_store(force_reload=True)
    results = vector_store.query_similar(query_text, n_results=n_results, namespaces=namespaces)
    
    # Concatenate the text chunks to construct a comprehensive context block.
    top_docs = []
    for res in results:
        top_docs.append(f"[Source: {res['source']} | Document: {res['name']}]\n{res['text']}")
        
    context = "\n\n".join(top_docs)
    
    rag_engine = get_rag_engine()
    return rag_engine.answer_query(query_text, context)

def list_namespaces() -> list:
    """
    **What**: Retrieves all registered "Namespaces" (Folders/Documents) currently stored in the Vector Database.
    
    **How**: Queries the vector store's internal metadata registry to return a list of dictionaries containing IDs and human-readable names.
    
    **Why**: Used by the React Frontend to populate the "Database Manager" UI panel.
    """
    vector_store = get_vector_store(force_reload=True)
    return vector_store.list_namespaces()

def purge_namespace(namespace: str) -> bool:
    """
    **What**: Completely deletes all vectorized data associated with a specific namespace.
    
    **How**: Forwards the deletion command to the active Vector Store implementation.
    
    **Why**: Allows users to cleanly remove outdated or incorrect documents from their AI's memory without needing to wipe the entire database.
    """
    vector_store = get_vector_store()
    return vector_store.delete_namespace(namespace)

def purge_namespaces(namespaces: list) -> bool:
    """
    **What**: Deletes a batch of namespaces in a single transaction.
    
    **How**: Iterates and executes deletion across the active Vector Store, followed by a system-level vacuum command.
    
    **Why**: Much faster and safer than calling `purge_namespace` in a loop when deleting multiple folders from the frontend UI.
    """
    vector_store = get_vector_store()
    return vector_store.delete_namespaces(namespaces)

async def verify_index_ready(test_text: str, namespace: str) -> bool:
    """
    Smart Index Ping: Blocks until newly inserted chunks are searchable in index.
    """
    vector_store = get_vector_store()
    return await vector_store.verify_index_ready(test_text, namespace)

def file_exists_in_db(file_id: str) -> bool:
    """
    Checks if a given cloud file ID has already been fully ingested into the database.
    """
    if not file_id:
        return False
    vector_store = get_vector_store()
    return vector_store.check_file_exists(file_id)
