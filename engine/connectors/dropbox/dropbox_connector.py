import io
import re
import concurrent.futures
from typing import Optional, Iterator, Dict, Any
import time
import os
import dropbox
from dropbox.exceptions import RateLimitError, AuthError

from ..base import BaseConnector, SourceType, LinkPreflightResult
from ..tika_parser import parse_with_tika

class DropboxConnector(BaseConnector):
    """
    **What**: The dedicated connector class for interfacing with Dropbox APIs.
    
    **How**: Uses the official `dropbox` Python SDK to recursively search shared folder links and download file streams in memory.
    
    **Why**: Unlike Google Drive, Dropbox doesn't allow unauthenticated downloads of files inside folders easily via standard HTTP, so we must rely heavily on the Dropbox SDK and a provided API token to crawl and download.
    """
    source = SourceType.DROPBOX

    def matches(self, url: str) -> bool:
        return bool(re.search(r'dropbox\.com/(scl|s|sh)/', url))

    def check_link(self, url: str, access_token: Optional[str]) -> LinkPreflightResult:
        # Fallback to application-wide token if the user didn't provide one
        token_to_use = access_token or os.getenv("DROPBOX_ACCESS_TOKEN")
        
        if not token_to_use:
            # We cannot use the SDK without a token at all
            return LinkPreflightResult(self.source, "locked", "private", True, "Dropbox requires an Access Token to read links via the API. Please provide one.")
            
        # Authenticated
        dbx = dropbox.Dropbox(token_to_use)
        try:
            meta = dbx.sharing_get_shared_link_metadata(url)
            if isinstance(meta, dropbox.sharing.FolderLinkMetadata):
                return LinkPreflightResult(self.source, "public", "folder", False)
            else:
                return LinkPreflightResult(self.source, "public", "file", False)
        except AuthError:
            return LinkPreflightResult(self.source, "invalid", "error", True, "Invalid Dropbox token.")
        except Exception as e:
            return LinkPreflightResult(self.source, "invalid", "error", False, str(e))

    def stream_file(self, url: str, access_token: Optional[str] = None, skip_callback: Optional[callable] = None) -> Dict[str, Any]:
        token_to_use = access_token or os.getenv("DROPBOX_ACCESS_TOKEN")
        if not token_to_use:
            raise ValueError("Dropbox access token is missing. Cannot stream file.")
            
        dbx = dropbox.Dropbox(token_to_use)
        
        try:
            meta = dbx.sharing_get_shared_link_metadata(url)
            file_id = meta.id
            if skip_callback and skip_callback(file_id):
                return {"skipped": True, "id": file_id}
        except Exception:
            pass

        buffer = io.BytesIO()
        
        max_retries = 5
        base_delay = 5
        
        for attempt in range(max_retries):
            try:
                # files_download takes a path, sharing_get_shared_link_file takes a url
                metadata, response = dbx.sharing_get_shared_link_file(url)
                buffer.write(response.content)
                break
            except RateLimitError as e:
                if attempt < max_retries - 1:
                    sleep_time = e.backoff if hasattr(e, 'backoff') else base_delay * (2 ** attempt)
                    print(f"Dropbox Rate Limit Hit. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    raise Exception("Failed to download file after multiple retries due to rate limits.") from e
                    
        text_content, metadata = parse_with_tika(buffer, '')
        buffer.close()
        return {"text": text_content, "tika_metadata": metadata}

    def stream_folder(self, url: str, access_token: str, skip_callback: Optional[callable] = None) -> Iterator[Dict[str, Any]]:
        token_to_use = access_token or os.getenv("DROPBOX_ACCESS_TOKEN")
        if not token_to_use:
            raise ValueError("Dropbox access token is missing. Cannot stream folder.")
            
        dbx = dropbox.Dropbox(token_to_use)
        
        # We need to get the shared folder's real path to list its contents
        try:
            meta = dbx.sharing_get_shared_link_metadata(url)
            shared_folder_path = meta.path_lower
        except Exception as e:
            raise ValueError(f"Could not resolve Dropbox shared folder: {e}")
            
        files_to_process = []
        
        def list_folder_recursive(path: str):
            try:
                result = dbx.files_list_folder(path)
                while True:
                    for entry in result.entries:
                        if isinstance(entry, dropbox.files.FileMetadata):
                            # We construct a mock URL that we can download using sharing_get_shared_link_file,
                            # actually it's easier to just use files_download for authenticated requests.
                            files_to_process.append(entry)
                        elif isinstance(entry, dropbox.files.FolderMetadata):
                            list_folder_recursive(entry.path_lower)
                    
                    if not result.has_more:
                        break
                    result = dbx.files_list_folder_continue(result.cursor)
            except RateLimitError as e:
                time.sleep(e.backoff)
                list_folder_recursive(path)

        list_folder_recursive(shared_folder_path)
        
        print(f"[Dropbox] Total files to process: {len(files_to_process)}")
        yield {"status": "metadata", "total_files": len(files_to_process)}
        
        files_found = False

        def process_item(item):
            print(f"[Dropbox] Processing item: {item.name} (ID: {item.id})")
            if skip_callback and skip_callback(item.id):
                print(f"[Dropbox] Skipping duplicate: {item.name}")
                return {"id": item.id, "skipped": True, "name": item.name}
            
            print(f"[Dropbox] Downloading & parsing file: {item.name}")
            buffer = io.BytesIO()
            # For authenticated folder items, download via path
            _, response = dbx.files_download(item.path_lower)
            buffer.write(response.content)
            text_content, metadata = parse_with_tika(buffer, '')
            buffer.close()
            print(f"[Dropbox] Finished parsing file: {item.name}")
            return {
                "id": item.id,
                "link": item.path_lower,  # or construct a real link
                "text": text_content,
                "tika_metadata": metadata,
                "name": item.name
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            future_to_file = {
                executor.submit(process_item, item): item
                for item in files_to_process
            }
            
            for future in concurrent.futures.as_completed(future_to_file):
                item = future_to_file[future]
                try:
                    result = future.result()
                    files_found = True
                    yield result
                except Exception as e:
                    print(f"Skipping file {item.name} inside folder due to error: {e}")
                
        if not files_found:
            raise ValueError("No supported files found in this Dropbox folder.")
