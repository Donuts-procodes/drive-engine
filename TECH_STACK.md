# VoiceLatex Google Drive Vector Engine: Tech Stack & Workflow Logic

This document details the libraries, workflow logic, and architectural decisions used in the VoiceLatex Vector Engine.

## Core Libraries & Why We Use Them

### Web Framework & Server
- **FastAPI (`fastapi==0.139.0`)**: 
  - **Why**: Used as the primary backend web framework. It supports highly concurrent asynchronous requests (`async/await`), which is strictly required when downloading 10,000 files simultaneously. Traditional frameworks like Flask or Django (synchronous) would crash or block when processing massive folder structures.
- **Uvicorn (`uvicorn==0.50.2`)**:
  - **Why**: The ASGI (Asynchronous Server Gateway Interface) web server used to run FastAPI. It's incredibly fast and built on `uvloop`, allowing the server to handle the high network throughput of live document streaming.

### Vector Storage & Search
- **ChromaDB (`chromadb==1.5.9`)**:
  - **Why**: Our local Vector Database. We use Chroma because it uses a highly optimized C++/SQLite backend (HNSWLib) that can run directly on the user's hard drive without requiring them to set up an external database like PostgreSQL/pgvector or pay for a cloud DB like Pinecone.

### LangChain Ecosystem
- **LangChain Core & Text Splitters (`langchain`, `langchain-text-splitters`)**:
  - **Why**: We use `RecursiveCharacterTextSplitter` to cut massive enterprise documents into 1,000-character chunks with a 100-character overlap. This prevents AI hallucinations by ensuring context isn't lost across chunk boundaries.
- **LangChain Hugging Face (`langchain-huggingface`)**:
  - **Why**: Provides the embedding wrapper for local Hugging Face `SentenceTransformers`. It turns our raw text chunks into mathematical vectors completely locally and for free, entirely bypassing OpenAI.
- **LangChain Chroma (`langchain-chroma`)**:
  - **Why**: The bridge connector that allows Langchain text chunks to be natively saved into the ChromaDB vector store.

### Message Queuing & Scale
- **Apache Kafka (`kafka-python`)**:
  - **Why**: Used as a shock absorber between the Web Server and the Vectorization Engine. When users upload thousands of files, passing them directly to the AI chunks would crash the web server. Kafka holds massive text payloads (up to 50MB per message) safely in a queue, allowing background workers to process them at a controlled pace.

### Cloud Connectors & Parsing
- **Apache Tika (`tika==2.6.0`)**:
  - **Why**: The most robust enterprise parsing engine available. We use it to sniff out magic bytes in binary files and extract raw plaintext from any format (PDFs, Word Docs, PPTX). It replaces fragile Python libraries like `PyPDF` and `python-docx` which frequently crash on corrupted files.
- **Google API Client (`google-api-python-client`, `google-auth-oauthlib`)**:
  - **Why**: Used to traverse Google Drive folders, check permissions, and download raw binaries.
- **Dropbox SDK (`dropbox>=12.0.2`)**:
  - **Why**: The official Dropbox API client required to securely traverse Dropbox shared links and download files.
- **HTTPX (`httpx`)**:
  - **Why**: An async-capable HTTP client used for making raw API calls to the Microsoft Graph API for SharePoint/OneDrive integration. We explicitly avoided the official Microsoft Graph SDK (`msgraph-sdk`) for three reasons:
    1. **Bloat**: The official SDK is massively over-engineered with complex type models that the project does not need.
    2. **Zero-Retention Control**: `httpx` gives us low-level control over the byte stream, ensuring we can pipe documents directly into `io.BytesIO()` memory buffers and destroy them without the SDK trying to save temporary files to the hard drive.
    3. **Async Native**: It integrates perfectly with our `ThreadPoolExecutor` allowing us to concurrently download 30 files from SharePoint without locking the event loop.

### Plugin Architecture
- **Dynamic Registry (`__init_subclass__`)**:
  - **Why**: Instead of hardcoding which LLM or Connector to use, base classes automatically register any inherited subclasses via Python's `__init_subclass__`. `pkgutil` dynamically discovers these at runtime. This allows seamless "plug and play" functionality without editing core routing code.

## Workflow Logic & Rationale

### 1. Preflight Failsafe (Checking Links)
**Logic**: Before attempting to download *anything*, the backend uses cloud APIs to sniff the link.
**Why**: If a user pastes a private/locked folder and the system blindly attempts to download 1,000 files, the system will throw 1,000 "Unauthorized" exceptions and crash. Preflighting safely checks the lock status and tells the frontend to ask the user for a token first.

### 2. Live Streaming (Server-Sent Events)
**Logic**: Files are downloaded and parsed one by one. As soon as a file is parsed by Tika, the text is yielded back to the React UI instantly using SSE.
**Why**: A standard HTTP request will time out after 60 seconds. If a folder takes 5 minutes to process, the browser will disconnect. SSE keeps the connection alive and provides the user with a live, real-time progress bar.

### 3. Concurrency Throttling & Retry Failsafe
**Logic**: The system uses `asyncio.Semaphore(10)` for vectorization and `ThreadPoolExecutor(max_workers=30)` for downloading.
**Why**: 30 threads maximize network bandwidth for cloud downloads. 10 concurrent connections push ChromaDB and OpenAI to their absolute limits without guaranteeing fatal bans. Because we use a local Hugging Face embedding model, we can vectorize as fast as the CPU allows without any network rate-limit retries.

### 4. Zero-Retention Data Privacy & Security
**Logic**: Files are downloaded strictly to `io.BytesIO()` memory buffers and passed directly to Apache Tika. During queries, context is wrapped in `<context>` XML tags.
**Why**: Ensures raw user files are never persisted on the server's hard drive, complying with strict zero-retention data privacy requirements. The XML tags instruct the LLM to strictly isolate user context from system prompt overrides, stopping malicious Prompt Injection attacks. Furthermore, queries are sandboxed mathematically using `$in` metadata filters for the `namespace`, guaranteeing no cross-tenant data leaks.

### 4. Deterministic Hashing (Deduplication)
**Logic**: Before saving chunks to ChromaDB, the system mathematically hashes the text (e.g., `SHA-256("FolderID_TextChunk")`) to generate an ID.
**Why**: If a user clicks "Load" on a folder they already loaded yesterday, the system generates the exact same IDs for the text chunks. ChromaDB sees the matching IDs and silently overwrites them instead of creating massive duplicate clones. This keeps the AI from repeating itself and saves hard drive space.

### 5. Smart Index Verification (The Ping)
**Logic**: After uploading the chunks, the backend queries the database with a tiny snippet of the text to ensure it's searchable before returning `Success`.
**Why**: ChromaDB compiles its search index (HNSW) on a background thread. If we tell the frontend "Success" the millisecond the upload finishes, and the user immediately asks a question, the index might not be compiled yet, resulting in an empty response. The ping guarantees the database is ready.
