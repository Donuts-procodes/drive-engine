"""
VoiceLatex Google Drive Vector Engine - Main Application Entry Point
=====================================================================
This script initializes and starts the FastAPI backend server. It handles:
- Loading environment configurations from the local `.env` file (e.g. OpenAI keys).
- Initializing the core FastAPI application.
- Configuring Cross-Origin Resource Sharing (CORS) to allow secure requests
  from the frontend development server (Vite/React running on port 5173).
- Mounting and registering the API routes from the `api.routes` package.
- Starting the ASGI server (Uvicorn) to listen for incoming network traffic.
"""

from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from dotenv import load_dotenv
import warnings
import os

# Suppress Tika's noisy pkg_resources deprecation warning
warnings.filterwarnings("ignore", category=UserWarning, module="tika")

# Load environment variables from .env file (e.g., OPENAI_API_KEY)
# This makes it available globally via os.getenv()
load_dotenv()

# Initialize the FastAPI backend application
# FastAPI automatically handles serializations, routing, and generates OpenAPI docs
app = FastAPI(
    title="VoiceLatex GDrive RAG Engine Backend",
    description="High-performance vector ingestion and Omni-Search query engine.",
    version="1.0.0"
)

# Configure Cross-Origin Resource Sharing (CORS)
# This allows the React Frontend (running on port 5173) to securely communicate with this backend.
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],  # Permits all standard HTTP methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Permits all headers (Content-Type, Authorization, etc.)
)

# Register all the API endpoints defined in api/routes.py under the root router
app.include_router(router)

if __name__ == "__main__":
    # Start the Uvicorn ASGI server
    # Host '0.0.0.0' binds to all network interfaces, allowing remote or container-based access
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = int(os.getenv("API_PORT", 8000))
    uvicorn.run(app, host=api_host, port=api_port)

