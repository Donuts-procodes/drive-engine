# VoiceLatex Google Drive Vector Engine

A high-performance, full-stack Retrieval-Augmented Generation (RAG) engine that natively ingests Google Drive files and folders, parses and indexes them into an embedded local ChromaDB, and performs Omni-Search queries across all databases using local Hugging Face embeddings and OpenAI's GPT models for chat.

---

### How It Works (Simple Workflow)

The system is designed to be extremely fast and robust, coordinating your browser, a background Python server, Cloud APIs, and a local database to process thousands of documents.

### 1. Preflighting (Checking Links)
When you paste a link (from Google Drive, Dropbox, or SharePoint) into the UI, you click **Check & Load**. 
The backend instantly pings the cloud provider to check if the link is a file or a folder, and if it requires a password (Access Token). If the link is locked and you didn't provide a token, it safely skips it to prevent the system from crashing.

### 2. Live Downloading & Parsing
The backend begins downloading the healthy files. Because downloading thousands of files one by one would take forever, the backend uses a **Thread Pool** to download 30 files at the exact same time. 
Instead of relying on fragile Python libraries (like PyPDF or python-docx), every single downloaded file is sent to an **Apache Tika Server**. Tika is an enterprise-grade engine that can flawlessly extract text from almost any file format (PDFs, Word Docs, Excel, PowerPoint, etc.).

As soon as a file is parsed, the backend instantly streams the text back to your browser UI so you can watch the progress live without the page freezing or timing out.

### 3. Vectorization (The Engine & Kafka Queue)
Once the files are loaded in your browser, you click **Start Engine**. 
To prevent your web server from crashing under heavy loads (e.g., 100,000 files), the text payloads are instantly pushed into an **Apache Kafka Message Queue**. The UI responds instantly, while a separate background `worker.py` script consumes the payloads.

Inside the worker, the text is split into small "chunks" (about 1,000 characters each). The backend mathematically calculates a unique ID for every chunk (so if you upload the exact same file twice, it automatically ignores the duplicate). 
The chunks are processed by a local Hugging Face model (`all-MiniLM-L6-v2`) to be converted into mathematical vectors, and then saved into a local database called **ChromaDB**. 

*Failsafe*: Because the vectorization is completely local via Hugging Face, there are no network rate limits. The entire folder structure is processed extremely fast offline.

### 4. Chatting & Searching
When you ask the chatbot a question, the system searches ChromaDB for the 8 most relevant text chunks across all your downloaded folders. It feeds those specific chunks to GPT-4o-mini, guaranteeing that the AI answers your question factually based *only* on your files, saving you massive amounts of money compared to feeding it entire books at once!

### 5. Cleaning Up
If you want to delete a folder from the AI's memory, you use the **Database Manager** panel in the UI. When you delete a folder, the backend physically deletes the data and runs a SQLite `VACUUM` command to instantly shrink the database file and give you your hard drive space back!

---

## Setup, Running & Deployment

### Local Running

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   cd frontend
   npm install
   cd ..
   ```

2. **Environment Variables**:
   Create a `.env` file in the root directory and add:
   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   KAFKA_BROKERS=localhost:9092
   # Optional: Configure dynamic database workspace folder for agent isolation
   # CHROMA_DB_PATH=./local_chroma_db
   ```

3. **Start the Application**:
   Simply run the start script, which automatically boots up the local Kafka cluster, the FastAPI backend, the React frontend, and the background Kafka Worker concurrently.
   ```bash
   .\start.bat
   ```

---

### Docker Deployment (Subsystem Isolation)

Since this backend serves as an isolated subsystem for individual agents, you can containerize it easily. Each agent can launch its own instance of the backend with its own database directory mounted to prevent cross-agent collisions.

#### 1. Build the Docker Image
```bash
docker build -t voicelatex-gdrive-engine .
```

#### 2. Run the Container (with Volume Mount & Env Path)
To launch an isolated database container for a specific agent (e.g. `agent_alpha`), run:
```bash
docker run -d \
  -p 8000:8000 \
  -v /path/to/agent_alpha_data:/app/local_chroma_db \
  -e OPENAI_API_KEY="your_openai_api_key_here" \
  -e CHROMA_DB_PATH="/app/local_chroma_db" \
  --name agent_alpha_vector_engine \
  voicelatex-gdrive-engine
```

- `-v /path/to/agent_alpha_data:/app/local_chroma_db`: Persists the ChromaDB vector database files on the host filesystem.
- `-e CHROMA_DB_PATH="/app/local_chroma_db"`: Instructs the engine to read and write all collection databases and registry names within this isolated volume folder.

---


## Detailed Project Codebase Map & Comments

Below is an overview of the key backend and frontend files and functions. Extensive comments and docstrings have been added directly to the source files:

### Backend Files
- [main.py](file:///c:/Users/Ayush/voicelatex-gdrive-engine/main.py): Sets up the FastAPI server, registers the router, and configures CORS.
- [api/routes.py](file:///c:/Users/Ayush/voicelatex-gdrive-engine/api/routes.py): Manages HTTP routes:
  - `extract_file_id`: Extracts resource IDs from Google Drive URLs.
  - `check_link`: Preflight checks for link permissions.
  - `load_link_stream`: Generates SSE events for real-time document loading.
  - `vectorize_batch`: Concurrently vectorizes documents, generates a markdown report, and waits for index compilation.
  - `query_endpoint` & `purge_endpoint`: Routes for retrieval and deletion.
- [engine/connectors.py](file:///c:/Users/Ayush/voicelatex-gdrive-engine/engine/connectors.py): Handles interaction with Google APIs and files:
  - `check_google_drive_link`: Performs magic byte scanning to check availability.
  - `stream_google_drive_file`: Handles OAuth credentials and parses PDF, Word, and text files.
  - `stream_google_drive_folder`: Downloads files from folders concurrently using a thread pool.
- [engine/rag_core.py](file:///c:/Users/Ayush/voicelatex-gdrive-engine/engine/rag_core.py): Orchestrates the vector database and RAG pipeline:
  - `get_master_vectorstore`: Initialise the Chroma client.
  - `ingest_texts_async`: Splits and vectorizes text with retry logic for rate limits.
  - `query_master_database`: Performs vector search and queries GPT-4o-mini.
  - `purge_namespace`: Cleans collections and executes `VACUUM`.
  - `verify_index_ready`: Smart-pings Chroma to verify indexing state.
- [debug_query.py](file:///c:/Users/Ayush/voicelatex-gdrive-engine/debug_query.py): Developer CLI utility for manual query debugging.
- [check_chroma.py](file:///c:/Users/Ayush/voicelatex-gdrive-engine/check_chroma.py): Diagnostic utility for auditing collections and vector distances.

### Frontend Files
- [frontend/src/api.js](file:///c:/Users/Ayush/voicelatex-gdrive-engine/frontend/src/api.js): Service wrapper for backend API calls.
- [frontend/src/cache.js](file:///c:/Users/Ayush/voicelatex-gdrive-engine/frontend/src/cache.js): Indexes downloaded document text in the browser's IndexedDB.
- [frontend/src/App.jsx](file:///c:/Users/Ayush/voicelatex-gdrive-engine/frontend/src/App.jsx): Main interface for file uploading, chat, and database management.

---

## Dependency Libraries & Features

1. **fastapi**:
   - Modern, high-performance web framework for Python.
   - Built-in asynchronous request processing (`async`/`await`).
   - Auto-generated OpenAPI (Swagger) API documentation.
   - Schema enforcement and JSON parsing using Pydantic.
2. **uvicorn**:
   - High-speed ASGI web server implementation.
   - Designed to run async-based Python applications with minimal latency.
3. **chromadb**:
   - Embedded open-source vector database.
   - Stores embeddings, documents, and metadata locally.
   - Optimized similarity searches utilizing native C++ HNSW indexing.
4. **google-api-python-client & google-auth-oauthlib**:
   - Official libraries for interacting with the Google Drive API.
   - Handles OAuth 2.0 user tokens and secure document downloads.
   - Exposes export endpoints for converting native Google Docs.
5. **pypdf**:
   - Lightweight, dependency-free PDF reading library.
   - Extracts plaintext from pages while filtering out layout styling.
6. **python-docx**:
   - Reads Microsoft Word `.docx` documents.
   - Parses paragraphs, headers, and runs.
7. **langchain & langchain-openai & langchain-chroma**:
   - Framework for building LLM applications.
   - Handles text splitting, OpenAI API calls, and vector store integration.
8. **python-dotenv**:
   - Manages environment variables from a local `.env` file.

---

## Features, Pros, & Limitations

### Core Features

- **Asynchronous Batch Vectorization**: Concurrently embeds multiple documents.
- **Server-Sent Events Ingestion**: Streams folder downloads in real-time.
- **Dynamic HNSW Index Verification**: Verifies indexing state before completing requests.
- **Binary Sniffing Magic Scan**: Detects file formats via magic bytes.
- **Self-Cleaning Storage**: Runs SQLite `VACUUM` commands to release disk space after purging.
- **Hybrid Local Storage**: Uses IndexedDB for client caching and local SQLite/Chroma for server-side index storage.

### Pros

- **High Speed**: Directly queries Chroma without wrapper overhead, yielding response times under 1 second.
- **Enhanced Reliability**: Retry logic handles OpenAI rate limits (HTTP 429) during batch processing.
- **Accurate Context Extraction**: Returns up to 8 high-relevance chunks for complex RAG tasks.
- **Low Memory Footprint**: Downloads files directly to in-memory buffers instead of writing to disk.

### Limitations

- **Chroma Global Lock**: Purging operations lock the database, blocking incoming queries during cleanup.
- **Rate Limit Constraints**: Batching very large collections can trigger OpenAI rate limits (1M tokens/min limit on standard tier), though the system safely absorbs and retries them.
- **OAuth Token Lifespan**: Google Access Tokens expire after 60 minutes, requiring users to periodically refresh credentials.

