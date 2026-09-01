from abc import ABC, abstractmethod
import inspect
from typing import List, Dict, Any
from langchain_core.documents import Document

class BaseVectorStore(ABC):
    """
    Abstract Base Class representing the interface for a Vector Database.
    All specific vector store implementations (Chroma, Pinecone, etc.) must implement these methods.
    """
    
    _registry = {}

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not inspect.isabstract(cls):
            if not hasattr(cls, 'db_name'):
                raise TypeError(f"Subclass {cls.__name__} must define a 'db_name' attribute for the registry.")
            cls._registry[cls.db_name] = cls

    @classmethod
    def get_registered_store(cls, name: str):
        return cls._registry.get(name)
    
    @abstractmethod
    async def add_documents(self, documents: List[Document]) -> None:
        """
        Embeds and adds a list of Document objects to the vector store.
        
        Args:
            documents (List[Document]): The documents to be vectorized and stored.
        """
        pass
        
    @abstractmethod
    def query_similar(self, query_text: str, n_results: int = 8, namespaces: List[str] = None) -> List[Dict[str, Any]]:
        """
        Queries the vector store for chunks mathematically similar to the query text.
        
        Args:
            query_text (str): The search string.
            n_results (int): Number of top results to return.
            namespaces (List[str]): Optional list of namespaces to restrict the search to.
            
        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each containing at least:
                                  - 'text': the content of the chunk
                                  - 'source': source metadata
                                  - 'name': document name metadata
        """
        pass
        
    @abstractmethod
    def list_namespaces(self) -> List[Dict[str, str]]:
        """
        Retrieves all active vector databases (namespaces/collections) registered.
        
        Returns:
            List[Dict[str, str]]: A list of objects containing {"id": namespace_id, "name": human_readable_name}.
        """
        pass
        
    @abstractmethod
    def delete_namespace(self, namespace: str) -> bool:
        """
        Deletes all text chunks belonging to a specific namespace and reclaims resources if applicable.
        
        Args:
            namespace (str): The namespace identifier to purge.
            
        Returns:
            bool: True if successful.
        """
        pass
        
    @abstractmethod
    def delete_namespaces(self, namespaces: List[str]) -> bool:
        """
        Deletes multiple namespaces in a batch, running resource reclamation only once at the end.
        
        Args:
            namespaces (List[str]): List of namespace identifiers to purge.
            
        Returns:
            bool: True if successful.
        """
        pass
        
    @abstractmethod
    async def verify_index_ready(self, test_text: str, namespace: str) -> bool:
        """
        Smart Index Ping: Blocks until newly inserted chunks are searchable.
        
        Args:
            test_text (str): A snippet of the document to search for.
            namespace (str): The target metadata namespace.
            
        """
        pass

    @abstractmethod
    def check_file_exists(self, file_id: str) -> bool:
        """
        Checks if a specific file ID has already been ingested into the vector store.
        
        Args:
            file_id (str): The cloud provider's unique file identifier.
            
        Returns:
            bool: True if the file exists, False otherwise.
        """
        pass
