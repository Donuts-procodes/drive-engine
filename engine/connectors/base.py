from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator, Optional, Iterator, Dict, Any
import inspect

class SourceType(str, Enum):
    GOOGLE_DRIVE = "google_drive"
    DROPBOX = "dropbox"
    SHAREPOINT = "sharepoint"

@dataclass
class LinkPreflightResult:
    source: SourceType
    status: str                  # "public", "locked", "invalid"
    type: str                    # "pdf", "docx", "folder", "text", "private", "error"
    requires_auth: bool          # True => frontend must send the user through OAuth first
    message: Optional[str] = None

class BaseConnector(ABC):
    source: SourceType
    
    _registry = []

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Register concrete subclasses automatically
        if not inspect.isabstract(cls):
            cls._registry.append(cls)

    @classmethod
    def get_registered_connectors(cls):
        return cls._registry

    @abstractmethod
    def matches(self, url: str) -> bool:
        """True if this connector owns the given pasted URL."""

    @abstractmethod
    def check_link(self, url: str, access_token: Optional[str]) -> LinkPreflightResult:
        """Powers /check_link. Metadata only, no content download."""

    @abstractmethod
    def stream_file(self, url: str, access_token: Optional[str] = None, skip_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Downloads a single file, sniffs magic bytes, and returns extracted text."""
        
    @abstractmethod
    def stream_folder(self, url: str, access_token: str, skip_callback: Optional[callable] = None) -> Iterator[Dict[str, Any]]:
        """Yields extracted text dicts {id, link, text, name} concurrently."""
