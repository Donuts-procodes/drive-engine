import io
import os
import threading
from typing import Dict, Any, Tuple
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# Increase Tika's startup timeout tolerance for heavy load (e.g., stress tests)
# Default is 3 retries and 5s sleep. We increase to 10 retries to give the JVM time to boot.
os.environ['TIKA_STARTUP_MAX_RETRY'] = os.getenv('TIKA_STARTUP_MAX_RETRY', '10')
os.environ['TIKA_STARTUP_SLEEP'] = os.getenv('TIKA_STARTUP_SLEEP', '5')

# pyrefly: ignore [missing-import]
from tika import parser

_tika_init_lock = threading.Lock()
_tika_initialized = False

def init_tika():
    global _tika_initialized
    if not _tika_initialized:
        with _tika_init_lock:
            if not _tika_initialized:
                try:
                    parser.from_buffer(b'')
                except Exception:
                    pass
                _tika_initialized = True


def parse_with_tika(file_obj: io.BytesIO, default_mime: str = '') -> Tuple[str, Dict[str, Any]]:
    """
    Parses a file using Apache Tika.
    
    Returns:
        Tuple[str, Dict]: Extracted text content and extracted metadata.
    """
    magic_bytes = file_obj.read(4)
    file_obj.seek(0)
    
    # Keep the security check for private Google Drive links
    if magic_bytes.startswith(b'<!DO') or magic_bytes.startswith(b'<htm') or magic_bytes.startswith(b'<!do'):
        preview = file_obj.read(1000).decode('utf-8', errors='ignore')
        file_obj.seek(0)
        if "accounts.google.com/v3/signin" in preview or "Sign in - Google" in preview:
            raise ValueError("This file is private. Please change sharing to 'Anyone with the link'.")
                
    # Ensure Tika is initialized securely before hitting the server
    init_tika()
    
    # from_file starts up the Tika server if not already running, 
    # then sends the file over REST and returns JSON with content and metadata.
    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(Exception)
    )
    def _parse():
        return parser.from_buffer(file_obj.getvalue())
        
    parsed = _parse()
    
    text_content = parsed.get("content", "") or ""
    text_content = text_content.strip()
    
    tika_metadata = parsed.get("metadata", {})
    
    return text_content, tika_metadata
