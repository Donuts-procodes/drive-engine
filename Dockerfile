# Use official Python runtime as base image
FROM python:3.11-slim

# Set environment variables
# Prevent Python from writing pyc files to disk
ENV PYTHONDONTWRITEBYTECODE=1
# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1
# Default ChromaDB Path inside container
ENV CHROMA_DB_PATH=/app/local_chroma_db

# Set work directory
WORKDIR /app

# Install system dependencies required for compiling C++ libraries (ChromaDB) and running Apache Tika (Java)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    default-jre \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements.txt first to leverage Docker build cache
COPY requirements.txt /app/

# Create virtual environment and add to PATH
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install python dependencies using uv
RUN pip install --no-cache-dir uv && \
    uv pip install -r requirements.txt

# Pre-download Hugging Face Sentence-Transformer model into the image cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy the rest of the application code
COPY api /app/api
COPY engine /app/engine
COPY main.py /app/main.py

# Expose port 8000 for FastAPI
EXPOSE 8000

# Create volume mount point for persistent ChromaDB storage
VOLUME ["/app/local_chroma_db"]

# Run ASGI server using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
