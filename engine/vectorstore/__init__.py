import os
import logging
import pkgutil
import importlib
import threading
from pathlib import Path
from .base import BaseVectorStore

logger = logging.getLogger(__name__)

# Dynamically discover and import all vector stores in this package
# This triggers __init_subclass__ in BaseVectorStore which registers them.
package_dir = Path(__file__).resolve().parent
for (_, module_name, is_pkg) in pkgutil.iter_modules([str(package_dir)]):
    try:
        importlib.import_module(f".{module_name}", __name__)
    except Exception as e:
        logger.warning("Failed to load VectorStore plugin '%s': %s", module_name, e)

_global_store_instance = None
_store_lock = threading.Lock()

def get_vector_store(force_reload: bool = False) -> BaseVectorStore:
    """
    Factory function to instantiate the active Vector Store implementation.
    Uses a singleton pattern to prevent instantiating multiple database clients concurrently.
    Pass force_reload=True to re-instantiate the client (useful to pick up changes made by other processes).
    """
    global _global_store_instance
    if _global_store_instance is not None and not force_reload:
        return _global_store_instance
        
    with _store_lock:
        if _global_store_instance is not None and not force_reload:
            return _global_store_instance
            
        db_type = os.getenv("VECTOR_DB", "chroma").lower()
        
        store_cls = BaseVectorStore.get_registered_store(db_type)
        if store_cls:
            _global_store_instance = store_cls()
            return _global_store_instance
        else:
            raise ValueError(f"Unsupported Vector Database Type: {db_type}. Registered plugins: {list(BaseVectorStore._registry.keys())}")
