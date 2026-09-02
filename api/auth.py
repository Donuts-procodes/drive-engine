from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import os
import urllib.parse
import httpx

router = APIRouter()

# These should be configured in your .env file
OAUTH_CONFIGS = {
    "google": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", "your_google_client_id"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", "your_google_client_secret"),
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/drive.readonly"]
    },
    "dropbox": {
        "client_id": os.getenv("DROPBOX_CLIENT_ID", "your_dropbox_client_id"),
        "client_secret": os.getenv("DROPBOX_CLIENT_SECRET", "your_dropbox_client_secret"),
        "auth_url": "https://www.dropbox.com/oauth2/authorize",
        "token_url": "https://api.dropboxapi.com/oauth2/token",
        "scopes": [] # Dropbox uses app-level permissions usually
    },
    "sharepoint": {
        "client_id": os.getenv("MS_CLIENT_ID", "your_ms_client_id"),
        "client_secret": os.getenv("MS_CLIENT_SECRET", "your_ms_client_secret"),
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scopes": ["Files.Read.All", "offline_access"]
    }
}

@router.get("/login/{provider}")
def login_provider(provider: str, request: Request):
    """
    Redirects the user to the Cloud Provider's OAuth Consent Screen.
    """
    if provider not in OAUTH_CONFIGS:
        raise HTTPException(status_code=404, detail="Provider not supported")
        
    config = OAUTH_CONFIGS[provider]
    redirect_uri = str(request.url_for("auth_callback", provider=provider))
    
    params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
    }
    
    if config["scopes"]:
        params["scope"] = " ".join(config["scopes"])
        
    auth_url = f"{config['auth_url']}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(auth_url)


@router.get("/callback/{provider}")
async def auth_callback(provider: str, code: str, request: Request):
    """
    Trades the authorization code for an Access Token.
    In a production environment with a DB, we would save this to the user's session.
    Since this is a local tool, we will redirect back to the frontend with the token.
    """
    if provider not in OAUTH_CONFIGS:
        raise HTTPException(status_code=404, detail="Provider not supported")
        
    config = OAUTH_CONFIGS[provider]
    redirect_uri = str(request.url_for("auth_callback", provider=provider))
    
    data = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(config["token_url"], data=data)
        
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Failed to get token: {response.text}")
        
    tokens = response.json()
    access_token = tokens.get("access_token")
    
    # Redirect back to the frontend (running on port 5173 typically) 
    # and pass the token via URL hash fragment (secure against server logs)
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    return RedirectResponse(f"{frontend_url}#provider={provider}&access_token={access_token}")
