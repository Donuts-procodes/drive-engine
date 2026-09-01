import io
import re
import concurrent.futures
from typing import Optional, Iterator, Dict, Any
import time
import os
import httpx
import base64

from ..base import BaseConnector, SourceType, LinkPreflightResult
from ..tika_parser import parse_with_tika

class SharePointConnector(BaseConnector):
    """
    **What**: The dedicated connector class for interfacing with Microsoft SharePoint and OneDrive APIs.
    
    **How**: Transforms the raw shareable URL into a base64 encoded string (`u!{base64}`) that the Microsoft Graph API requires. Uses HTTPX to traverse the graph and download files into memory.
    
    **Why**: Enterprise files are heavily guarded. The Microsoft Graph API requires specific header injections and encoded IDs to read enterprise files securely.
    """
    source = SourceType.SHAREPOINT

    def matches(self, url: str) -> bool:
        return bool(re.search(r'(\.sharepoint\.com|onedrive\.live\.com|1drv\.ms)', url))

    def _encode_share_id(self, url: str) -> str:
        """Encodes URL to a Graph Share ID (`u!{base64_encoded}`)"""
        base64_val = base64.urlsafe_b64encode(url.encode('utf-8')).decode('utf-8')
        return "u!" + base64_val.rstrip("=")

    def check_link(self, url: str, access_token: Optional[str]) -> LinkPreflightResult:
        token_to_use = access_token or os.getenv("SHAREPOINT_ACCESS_TOKEN")
        if not token_to_use:
            return LinkPreflightResult(self.source, "locked", "private", True, "SharePoint always requires auth. Please provide an access token.")

        share_id = self._encode_share_id(url)
        headers = {"Authorization": f"Bearer {token_to_use}"}
        graph_url = f"https://graph.microsoft.com/v1.0/shares/{share_id}/driveItem"
        
        try:
            with httpx.Client() as client:
                response = client.get(graph_url, headers=headers)
                if response.status_code == 404:
                    return LinkPreflightResult(self.source, "invalid", "error", False, "File not found.")
                elif response.status_code == 401 or response.status_code == 403:
                    return LinkPreflightResult(self.source, "invalid", "error", True, "Invalid token or insufficient permissions.")
                
                response.raise_for_status()
                data = response.json()
                
                if "folder" in data:
                    return LinkPreflightResult(self.source, "public", "folder", False)
                else:
                    return LinkPreflightResult(self.source, "public", "file", False)
        except Exception as e:
            return LinkPreflightResult(self.source, "invalid", "error", False, str(e))

    def stream_file(self, url: str, access_token: Optional[str] = None, skip_callback: Optional[callable] = None) -> Dict[str, Any]:
        token_to_use = access_token or os.getenv("SHAREPOINT_ACCESS_TOKEN")
        if not token_to_use:
            raise ValueError("SharePoint ingestion requires an Access Token.")

        share_id = self._encode_share_id(url)
        
        if skip_callback and skip_callback(share_id):
            return {"skipped": True, "id": share_id}
            
        headers = {"Authorization": f"Bearer {token_to_use}"}
        
        graph_url = f"https://graph.microsoft.com/v1.0/shares/{share_id}/driveItem/content"
        buffer = io.BytesIO()
        
        max_retries = 5
        base_delay = 5
        
        with httpx.Client() as client:
            for attempt in range(max_retries):
                response = client.get(graph_url, headers=headers, follow_redirects=True)
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        retry_after = int(response.headers.get("Retry-After", base_delay * (2 ** attempt)))
                        print(f"SharePoint Rate Limit Hit. Retrying in {retry_after}s...")
                        time.sleep(retry_after)
                        continue
                    else:
                        raise Exception("Failed to download file after multiple retries due to rate limits.")
                
                response.raise_for_status()
                buffer.write(response.content)
                break
                
        text_content, metadata = parse_with_tika(buffer, '')
        buffer.close()
        return {"text": text_content, "tika_metadata": metadata}

    def stream_folder(self, url: str, access_token: str, skip_callback: Optional[callable] = None) -> Iterator[Dict[str, Any]]:
        token_to_use = access_token or os.getenv("SHAREPOINT_ACCESS_TOKEN")
        if not token_to_use:
            raise ValueError("SharePoint ingestion requires an Access Token.")

        share_id = self._encode_share_id(url)
        headers = {"Authorization": f"Bearer {token_to_use}"}
        graph_url = f"https://graph.microsoft.com/v1.0/shares/{share_id}/driveItem/children"
        
        files_to_process = []

        with httpx.Client() as client:
            def list_children(url):
                while url:
                    response = client.get(url, headers=headers)
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        time.sleep(retry_after)
                        continue
                    response.raise_for_status()
                    data = response.json()
                    
                    for item in data.get("value", []):
                        if "folder" in item:
                            list_children(f"https://graph.microsoft.com/v1.0/drives/{item['parentReference']['driveId']}/items/{item['id']}/children")
                        elif "file" in item:
                            files_to_process.append(item)
                    
                    url = data.get("@odata.nextLink")
            
            list_children(graph_url)

        print(f"[SharePoint] Total files to process: {len(files_to_process)}")
        yield {"status": "metadata", "total_files": len(files_to_process)}

        files_found = False

        def process_item(item):
            print(f"[SharePoint] Processing item: {item['name']} (ID: {item['id']})")
            if skip_callback and skip_callback(item["id"]):
                print(f"[SharePoint] Skipping duplicate: {item['name']}")
                return {"id": item["id"], "skipped": True, "name": item["name"]}
                
            print(f"[SharePoint] Downloading & parsing file: {item['name']}")
            buffer = io.BytesIO()
            download_url = item.get("@microsoft.graph.downloadUrl")
            if not download_url:
                raise ValueError("No download URL available for item.")
                
            with httpx.Client() as dl_client:
                # download_url is pre-authenticated, so no headers are strictly needed
                response = dl_client.get(download_url)
                response.raise_for_status()
                buffer.write(response.content)
                
            text_content, metadata = parse_with_tika(buffer, '')
            buffer.close()
            print(f"[SharePoint] Finished parsing file: {item['name']}")
            return {
                "id": item["id"],
                "link": item.get("webUrl", ""),
                "text": text_content,
                "tika_metadata": metadata,
                "name": item["name"]
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
                    print(f"Skipping file {item.get('name')} inside folder due to error: {e}")
                
        if not files_found:
            raise ValueError("No supported files found in this SharePoint folder.")
