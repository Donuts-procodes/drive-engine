# Changelog


## [1.3.0] - 2026-07-14 Local Embeddings & Worker Fixes

### Added
- **Local Embeddings**: Replaced `OpenAIEmbeddings` with local Hugging Face `SentenceTransformers` (`all-MiniLM-L6-v2`), making vectorization completely free and offline.

### Removed
- **Rate Limiting**: Stripped out `tenacity` exponential backoff logic from `chroma_store.py` since local models don't trigger `HTTP 429` rate limit errors.

### Fixed
- **Duplicate ID Vectorization Crash**: Fixed an issue in `rag_core.py` where mathematically identical text chunks within a single file would generate duplicate batch IDs and crash ChromaDB. Chunks are now deduplicated in Python prior to insertion.
- **Orphaned Folder Data**: Fixed a bug in `worker.py` where Google Drive folder ingestion streams failed to attach the `namespace` metadata to files, causing the database registry to lose track of the vectors and throw "No databases found" errors.

## [1.2.0] - 2026-07-14

### Added
- **Hybrid Zero-Retention Architecture**: Integrated an Apache Kafka message queue to act as a shock-absorber for massive file ingestions.
- **Background Worker**: Created `engine/worker.py` to consume text-only payloads from Kafka, enforcing strict zero-retention (no raw files written to disk) while freeing up the FastAPI main thread.
- **Scalability Configuration**: Increased Kafka producer/consumer limits to 50MB to support extracting and processing 10MB PDFs.
- **Recursive Directory Scanning**: The Google Drive connector now dives into nested subfolders dynamically.
- **Advanced UI Error Reporting**: Added pre-flight file counting and explicit failure tracking to the UI load dialog.

## [1.1.0] - 2026-07-13 Kafka Refactoring

### Added
- **Infrastructure**: Added `docker-compose.yml` to run a local Apache Kafka broker and Zookeeper instance for local development.
- **Dependencies**: Added `kafka-python` to `requirements.txt` to enable message brokering.
- **Worker Microservice**: Created `engine/worker.py` as a standalone Kafka consumer that reads files from temporary storage, parses them using Apache Tika, chunks the text, and ingests the embeddings into ChromaDB asynchronously.

### Changed
- **API Routing (`api/routes.py`)**: 
  - Refactored the ingestion endpoints (`/load_link`, `/load_link_stream`) to operate asynchronously via the "Claim Check" pattern.
  - Replaced synchronous text processing with a Kafka producer that queues file metadata payloads to the `vectorize-tasks` topic.
  - Removed `asyncio.Semaphore`, completely decoupling API traffic bounds from the ingestion limits. The API can now accept thousands of files instantly without blocking.
- **Google Drive Connector (`engine/connectors/gdrive/google_drive.py`)**:
  - Replaced the in-memory `io.BytesIO` buffering. Files are now streamed directly to local disk (`./temp_downloads/`) using chunked I/O to prevent Memory Leaks / Out Of Memory (OOM) crashes on large files.
  - Connector now yields the temporary `file_path` on disk instead of the raw `text` content to the API router.
- **Tika Parser (`engine/connectors/tika_parser.py`)**:
  - Modified `parse_with_tika` to accept an absolute file path (`file_path: str`) instead of an `io.BytesIO` buffer, utilizing `parser.from_file` for parsing instead of `parser.from_buffer`.

### Removed
- **API Routing (`api/routes.py`)**: Removed the synchronous `/vectorize` and `/vectorize_batch` endpoints, as batch vectorization is now fully orchestrated by the Kafka `worker.py` microservice.
- **In-Memory Buffering**: Completely removed RAM buffering logic from the Google Drive download sequence.
