from abc import ABC, abstractmethod
import inspect

class BaseRAGEngine(ABC):
    """
    Abstract Base Class for the Retrieval-Augmented Generation LLM Engine.
    Implementations (OpenAI, Anthropic, local Llama) handle synthesizing answers from context.
    """
    
    _registry = {}

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not inspect.isabstract(cls):
            if not hasattr(cls, 'engine_name'):
                raise TypeError(f"Subclass {cls.__name__} must define an 'engine_name' attribute for the registry.")
            cls._registry[cls.engine_name] = cls

    @classmethod
    def get_registered_engine(cls, name: str):
        return cls._registry.get(name)
    
    @abstractmethod
    def answer_query(self, query_text: str, context: str) -> str:
        """
        Synthesizes an answer to the user's query based on the provided context block.
        
        Args:
            query_text (str): The natural language question asked by the user.
            context (str): The concatenated string of context chunks (with source metadata).
            
        Returns:
            str: The final generated response from the AI.
        """
        pass
