import os
import io
import re
import requests
from typing import Optional, List, Dict, Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import httplib2
import google_auth_httplib2
from tika import parser as tika_parser

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("google-drive-mcp")

# Types that CANNOT be exported or downloaded at all
GOOGLE_SKIP_TYPES = {
    'application/vnd.google-apps.form',
    'application/vnd.google-apps.map',
    'application/vnd.google-apps.site',
    'application/vnd.google-apps.jam',
    'application/vnd.google-apps.fusiontable',
    'application/vnd.google-apps.script',
    'application/vnd.google-apps.folder',
}

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

def get_drive_service(access_token: str):
    access_token = access_token.strip()
    creds = Credentials(token=access_token)
    http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http())
    return build('drive', 'v3', http=http)

@mcp.tool()
def list_google_drive_folder(url: str, access_token: str) -> str:
    """
    Lists all files and subfolders inside a given Google Drive folder URL.
    Args:
        url: The Google Drive folder URL (or ID).
        access_token: A valid Google OAuth2 access token.
    """
    folder_id, _ = extract_google_drive_file_id(url)
    
    if not access_token:
        return "Error: Missing access token."
        
    try:
        service = get_drive_service(access_token)
        query = f"'{folder_id}' in parents and trashed=false"
        
        results = service.files().list(
            q=query, 
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100
        ).execute()
        
        items = results.get('files', [])
        
        if not items:
            return "Folder is empty or not found."
            
        output = [f"Found {len(items)} items in folder {folder_id}:"]
        for item in items:
            kind = "Folder" if item.get("mimeType") == "application/vnd.google-apps.folder" else "File"
            output.append(f"- [{kind}] {item.get('name')} (ID: {item.get('id')}) - Type: {item.get('mimeType')}")
            
        return "\n".join(output)
        
    except Exception as e:
        return f"Error listing folder: {str(e)}"

@mcp.tool()
def read_google_drive_file(url: str, access_token: str) -> str:
    """
    Downloads and parses the text content of a Google Drive file, resolving shortcuts and handling exports.
    Args:
        url: The Google Drive file URL (or ID).
        access_token: A valid Google OAuth2 access token.
    """
    file_id, _ = extract_google_drive_file_id(url)
    
    if not access_token:
        return "Error: Missing access token."
        
    try:
        service = get_drive_service(access_token)
        file_metadata = service.files().get(fileId=file_id, fields='mimeType,name,shortcutDetails').execute()
        mime_type = file_metadata.get('mimeType', '')
        file_name = file_metadata.get('name', 'Unknown')
        
        if mime_type == 'application/vnd.google-apps.shortcut':
            file_id = file_metadata['shortcutDetails']['targetId']
            file_metadata = service.files().get(fileId=file_id, fields='mimeType,name').execute()
            mime_type = file_metadata.get('mimeType', '')
            file_name = file_metadata.get('name', 'Unknown')
            
        # The user explicitly ONLY wants txt, docs, pdf, md, docx
        ALLOWED_MIME_TYPES = {
            'text/plain',                                                                # txt, md
            'text/markdown',                                                             # md
            'application/pdf',                                                           # pdf
            'application/vnd.google-apps.document',                                      # docs
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',   # docx
            'application/msword'                                                         # doc
        }
        
        if mime_type not in ALLOWED_MIME_TYPES:
            return f"Cannot read file '{file_name}': Only txt, docs, pdf, md, docx are allowed. Got: ({mime_type})"
            
        buffer = io.BytesIO()
        
        GOOGLE_EXPORT_MAP = {
            'application/vnd.google-apps.document': 'text/plain',
            'application/vnd.google-apps.presentation': 'application/pdf',
            'application/vnd.google-apps.drawing': 'application/pdf',
        }
        
        if mime_type in GOOGLE_EXPORT_MAP:
            export_mime = GOOGLE_EXPORT_MAP[mime_type]
            request = service.files().export_media(fileId=file_id, mimeType=export_mime)
            mime_type = export_mime
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        elif 'application/vnd.google-apps' in mime_type:
            try:
                request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
                mime_type = 'application/pdf'
                downloader = MediaIoBaseDownload(buffer, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            except Exception as e:
                return f"PDF export failed for unknown type '{mime_type}': {e}"
        else:
            request = service.files().get_media(fileId=file_id)
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
                
        # Parse content
        buffer.seek(0)
        file_bytes = buffer.read()
        parsed = tika_parser.from_buffer(file_bytes)
        buffer.close()
        
        text_content = parsed.get("content", "")
        if not text_content or not text_content.strip():
            return f"File '{file_name}' was downloaded successfully but contained no readable text."
            
        return f"--- START OF '{file_name}' ---\n{text_content.strip()}\n--- END OF FILE ---"
        
    except Exception as e:
        return f"Error reading file: {str(e)}"

if __name__ == "__main__":
    # Start the FastMCP server with stdio transport
    mcp.run(transport='stdio')
