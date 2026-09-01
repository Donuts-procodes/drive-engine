# VoiceLatex Google Drive Vector Engine: Development & Production Workflow

This document explains the standard workflows for developing, running, testing, and deploying the Google Drive Vector Engine subsystem.

---

## 1. Local Development Workflow

Follow this loop when adding new features (e.g. new file parsers, alternative vector stores, or prompt adjustments):

```mermaid
graph LR
    Code[Write Code] --> Compile[py_compile Syntax Check]
    Compile --> LocalRun[Run Local Servers]
    LocalRun --> DebugCli[Test CLI Debugger]
    DebugCli --> Code
```

### Syntax Verification
Before committing or testing code, compile all files to verify syntax correctness:
```bash
python -m py_compile engine/connectors.py engine/rag_core.py api/routes.py main.py debug_query.py check_chroma.py tests/check_master.py
```

### Prompt Engineering
To modify the behavior or tone of the answering bot, edit the prompt template in [engine/rag_core.py](engine/rag_core.py):
```python
prompt = ChatPromptTemplate.from_messages([
    ("system", "Your custom instructions go here..."),
    ("human", "{question}")
])
```

---

## 2. Ingestion & Vectorization Workflow

When the frontend submits a document url, the system processes it as follows:

```mermaid
sequenceDiagram
    participant UI as React Frontend
    participant Route as api/routes.py
    participant Connect as engine/connectors.py
    participant Core as engine/rag_core.py
    participant Tika as Apache Tika
    participant DB as Chroma DB

    UI->>Route: Click "Check & Load"
    Route->>Connect: Check if link is locked or public
    Connect-->>Route: Return preflight status
    Route->>Connect: Download files (30 at a time via ThreadPoolExecutor)
    Connect->>Tika: Extract text from binary files
    Tika-->>Route: Yield extracted plaintext
    Route-->>UI: Stream live text to browser screen
    
    UI->>Route: Click "Start Engine"
    Route->>Kafka: Push raw text payloads to `vectorize-tasks` topic (Max 50MB)
    Route-->>UI: Complete response (Instant Success!)
    
    Kafka->>Worker: Consume text payloads asynchronously
    Worker->>Core: Split into 1000 char blocks and generate hash ID
    Core->>Core: Hugging Face Local Embeddings (all-MiniLM-L6-v2)
    Core->>DB: Save chunks (Ignore duplicates based on ID)
```

---

## 3. Query & Retrieval Workflow

Queries to the `/query` endpoint run the following steps:

1. **Embedding generation**: The query string is embedded into a high-dimensional vector exactly once using local Hugging Face.
2. **Direct database search**: The engine queries the `MASTER_COLLECTION` in ChromaDB, applying a `$in` namespace filter, using L2 distance similarity metrics. It fetches the top 8 absolute best matching text chunks for the allowed folders.
3. **Prompt construction**: Extracted text chunks are concatenated into a structured markdown block and wrapped securely inside `<context>` XML tags to prevent prompt injection.
4. **Answering**: The prompt is processed by `gpt-4o-mini` to stream or return the answer.

---

## 4. Multi-Agent Deployment Workflow (Subsystem Isolation)

Since this subsystem is embedded into individual agents, use the `CHROMA_DB_PATH` environment variable to isolate storage folders.

```mermaid
graph TD
    subgraph Host Machine [Host Storage]
        VolA[/host/agent_a_data/]
        VolB[/host/agent_b_data/]
    end
    
    subgraph ContainerA [Agent A Container]
        EngineA[Vector Engine] -->|CHROMA_DB_PATH=/data| DB_A[(chroma.sqlite3 & registry)]
    end
    
    subgraph ContainerB [Agent B Container]
        EngineB[Vector Engine] -->|CHROMA_DB_PATH=/data| DB_B[(chroma.sqlite3 & registry)]
    end

    VolA -->|Mount to /data| ContainerA
    VolB -->|Mount to /data| ContainerB
```

### Step-by-Step Isolation Set Up:
1. Define a persistent mount path for each agent on the host filesystem (e.g. `/var/data/agent_1`).
2. Build the docker image:
   ```bash
   docker build -t voicelatex-gdrive-engine .
   ```
3. Boot the container supplying the specific mount and path variable:
   ```bash
   docker run -d \
     -p 8001:8000 \
     -v /var/data/agent_1:/app/local_chroma_db \
     -e OPENAI_API_KEY="sk-..." \
     -e CHROMA_DB_PATH="/app/local_chroma_db" \
     --name agent_1_engine \
     voicelatex-gdrive-engine
   ```
   This isolates `namespaces_registry.json`, `chroma.sqlite3`, and `index` files completely to the `/var/data/agent_1` path.

---

## 5. Diagnostics & Maintenance Workflow

### Standalone Query Checking
Run raw query tests using the CLI utility:
```bash
# Power Shell env setup
$env:CHROMA_DB_PATH="./local_chroma_db/agent_1"
python debug_query.py
```

### Storage Vacuuming
When removing namespace items via `/purge`, the system automatically runs the `VACUUM` SQL statement to release free pages and shrink SQLite files:
```python
conn = sqlite3.connect("/app/local_chroma_db/chroma.sqlite3")
conn.execute("VACUUM")
```
No manual intervention is needed.
