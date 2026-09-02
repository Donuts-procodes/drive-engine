import os
import logging
import pkgutil
import importlib
from pathlib import Path
from .base import BaseRAGEngine

logger = logging.getLogger(__name__)

# Dynamically discover and import all llms in this package
# This triggers __init_subclass__ in BaseRAGEngine which registers them.
package_dir = Path(__file__).resolve().parent
for (_, module_name, is_pkg) in pkgutil.iter_modules([str(package_dir)]):
    try:
        importlib.import_module(f".{module_name}", __name__)
    except Exception as e:
        logger.warning("Failed to load LLM plugin '%s': %s", module_name, e)

def get_rag_engine() -> BaseRAGEngine:
    """
    Factory function to instantiate the active RAG Engine implementation.
    """
    llm_type = os.getenv("RAG_LLM", "openai").lower()
    
    engine_cls = BaseRAGEngine.get_registered_engine(llm_type)
    if engine_cls:
        return engine_cls()
    else:
        raise ValueError(f"Unsupported RAG LLM Type: {llm_type}. Registered plugins: {list(BaseRAGEngine._registry.keys())}")
