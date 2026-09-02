from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from google.oauth2.credentials import Credentials
# pyrefly: ignore [missing-import]
import google_auth_httplib2
import httplib2
from googleapiclient.discovery import build

router = APIRouter()

@router.get("/browse/google/root")
def browse_google_root(authorization: Optional[str] = Header(None)):
    """
    Lists the top-level files and folders in Google Drive using the provided OAuth access token.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
        
    token = authorization.split("Bearer ")[1]
    
    try:
        creds = Credentials(token=token)
        http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http())
        service = build('drive', 'v3', http=http)
        
        # Query for root folders and files
        results = service.files().list(
            q="'root' in parents and trashed=false",
            fields="files(id, name, mimeType)",
            pageSize=100
        ).execute()
        
        items = results.get('files', [])
        return {"status": "success", "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/browse/google/folder/{folder_id}")
def browse_google_folder(folder_id: str, authorization: Optional[str] = Header(None)):
    """
    Lists the files and folders inside a specific Google Drive folder.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
        
    token = authorization.split("Bearer ")[1]
    
    try:
        creds = Credentials(token=token)
        http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http())
        service = build('drive', 'v3', http=http)
        
        # Query for folders and files inside folder_id
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id, name, mimeType)",
            pageSize=100
        ).execute()
        
        items = results.get('files', [])
        return {"status": "success", "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
