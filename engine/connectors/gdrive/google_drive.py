import os
import uuid
import requests
import concurrent.futures
import io
from google.oauth2.credentials import Credentials
# pyrefly: ignore [missing-import]
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import re
import httplib2
import google_auth_httplib2
from typing import Optional, Iterator, Dict, Any

from ..base import BaseConnector, SourceType, LinkPreflightResult
from ..tika_parser import parse_with_tika

def extract_google_drive_file_id(link: str) -> tuple[str, str]:
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', link)
    if match:
        return match.group(1), "folder"
        
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', link)
    if match:
        return match.group(1), "file"
        
    match = re.search(r'id=([a-zA-Z0-9_-]+)', link)
    if match:
        return match.group(1), "file"
        
    return link, "file"

class GoogleDriveConnector(BaseConnector):
    source = SourceType.GOOGLE_DRIVE

    def matches(self, url: str) -> bool:
        return bool(re.search(r'drive\.google\.com|docs\.google\.com', url))

    def check_link(self, url: str, access_token: Optional[str]) -> LinkPreflightResult:
        file_id, link_type = extract_google_drive_file_id(url)
        
        if link_type == "folder":
            if access_token:
                access_token = access_token.strip()
                try:
                    creds = Credentials(token=access_token)
                    http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http())
                    service = build('drive', 'v3', http=http)
                    service.files().get(fileId=file_id, fields='id').execute()
                    return LinkPreflightResult(self.source, "public", "folder", False)
                except Exception as e:
                    return LinkPreflightResult(self.source, "invalid", "error", False, f"Folder not found or invalid ID: {str(e)}")
            else:
                return LinkPreflightResult(self.source, "locked", "folder", True, "Requires Access Token")
                
        if access_token:
            return LinkPreflightResult(self.source, "public", "authorized", False)
            
        download_url = f'https://drive.google.com/uc?export=download&id={file_id}'
        try:
            response = requests.get(download_url, stream=True)
            
            if response.status_code == 404:
                return LinkPreflightResult(self.source, "invalid", "error", False)
            
            if response.status_code == 500:
                export_url = f'https://docs.google.com/document/d/{file_id}/export?format=txt'
                response = requests.get(export_url, stream=True)
                if response.status_code == 404:
                    return LinkPreflightResult(self.source, "invalid", "error", False)
                
            preview = next(response.iter_content(chunk_size=1000), b"")
            response.close()
            
            if preview.startswith(b'<!DO') or preview.startswith(b'<htm') or preview.startswith(b'<!do'):
                preview_str = preview.decode('utf-8', errors='ignore')
                if "accounts.google.com/v3/signin" in preview_str or "Sign in - Google" in preview_str:
                    return LinkPreflightResult(self.source, "locked", "private", True)
                    
            if preview.startswith(b'%PDF'):
                return LinkPreflightResult(self.source, "public", "pdf", False)
            elif preview.startswith(b'PK\x03\x04'):
                return LinkPreflightResult(self.source, "public", "docx", False)
            elif preview.startswith(b'\xD0\xCF\x11\xE0'):
                return LinkPreflightResult(self.source, "locked", "legacy_doc", False)
            else:
                return LinkPreflightResult(self.source, "public", "text", False)
                
        except Exception as e:
            return LinkPreflightResult(self.source, "invalid", "error", False)

    def stream_file(self, url: str, access_token: Optional[str] = None, skip_callback: Optional[callable] = None) -> Dict[str, Any]:
        file_id, _ = extract_google_drive_file_id(url)
        
        if skip_callback and skip_callback(file_id):
            return {"skipped": True, "id": file_id}
            
        mime_type = ''
        file_name = "Unknown"
        buffer = io.BytesIO()
        
        if access_token:
            access_token = access_token.strip()
            creds = Credentials(token=access_token)
            http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http())
            service = build('drive', 'v3', http=http)
            
            file_metadata = service.files().get(fileId=file_id, fields='mimeType,name').execute()
            mime_type = file_metadata.get('mimeType', '')
            file_name = file_metadata.get('name', 'Unknown')
            
            if 'application/vnd.google-apps' in mime_type:
                if mime_type == 'application/vnd.google-apps.document':
                    request = service.files().export_media(fileId=file_id, mimeType='text/plain')
                    mime_type = 'text/plain'
                else:
                    request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
                    mime_type = 'application/pdf'
            else:
                request = service.files().get_media(fileId=file_id)
                
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        else:
            download_url = f'https://drive.google.com/uc?export=download&id={file_id}'
            response = requests.get(download_url, stream=True)
            
            if response.status_code == 500:
                export_url = f'https://docs.google.com/document/d/{file_id}/export?format=txt'
                response = requests.get(export_url, stream=True)
                
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    buffer.write(chunk)
                    
        text_content, metadata = parse_with_tika(buffer, mime_type)
        buffer.close()
        return {"text": text_content, "tika_metadata": metadata, "id": file_id, "name": file_name, "mime_type": mime_type}

    def stream_folder(self, url: str, access_token: str, skip_callback: Optional[callable] = None) -> Iterator[Dict[str, Any]]:
        folder_id, _ = extract_google_drive_file_id(url)
        if not access_token:
            raise ValueError("Folder ingestion requires a Google Drive Access Token.")
        access_token = access_token.strip()    
        creds = Credentials(token=access_token)
        http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http())
        service = build('drive', 'v3', http=http)
        
        files_found = False
        files_to_process = []
        
        def get_files_in_folder_recursive(current_folder_id):
            query = f"'{current_folder_id}' in parents and trashed=false"
            page_token = None
            while True:
                results = service.files().list(
                    q=query, 
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageToken=page_token
                ).execute()
                
                for item in results.get('files', []):
                    if item.get('mimeType') == 'application/vnd.google-apps.folder':
                        get_files_in_folder_recursive(item['id'])
                    else:
                        files_to_process.append(item)
                        
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
                    
        get_files_in_folder_recursive(folder_id)
        
        try:
            with open("discovered_files.log", "a", encoding="utf-8") as log_file:
                log_file.write(f"--- Found {len(files_to_process)} files in folder {folder_id} ---\n")
                for item in files_to_process:
                    log_file.write(f"ID: {item['id']} | Name: {item['name']}\n")
                log_file.write("\n")
        except Exception as e:
            print(f"Failed to write log: {e}")
            
        print(f"[GDrive] Total files to process: {len(files_to_process)}")
        yield {"status": "metadata", "total_files": len(files_to_process)}
        
        def process_item(item):
            print(f"[GDrive] Processing item: {item['name']} (ID: {item['id']})")
            if skip_callback and skip_callback(item['id']):
                print(f"[GDrive] Skipping duplicate: {item['name']}")
                return {"id": item['id'], "skipped": True, "name": item['name']}
                
            link = f"https://drive.google.com/file/d/{item['id']}/view"
            print(f"[GDrive] Downloading & parsing file: {item['name']}")
            result_dict = self.stream_file(link, access_token)
            print(f"[GDrive] Finished parsing file: {item['name']}")
            return {
                "id": item['id'],
                "link": link,
                "text": result_dict.get("text", ""),
                "tika_metadata": result_dict.get("tika_metadata", {}),
                "mime_type": result_dict.get("mime_type", ""),
                "name": item['name']
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=int(os.getenv('GDRIVE_MAX_WORKERS', 30))) as executor:
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
                    print(f"Skipping file {item['name']} inside folder due to error: {e}")
                    files_found = True # Prevent 'no files found' crash if all fail
                    yield {"status": "error", "id": item['id'], "name": item['name'], "error": str(e)}
                
        if not files_found:
            raise ValueError("No supported files found in this folder.")
