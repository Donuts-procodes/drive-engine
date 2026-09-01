// Base URL for the FastAPI backend
const BASE_URL = 'http://localhost:8000';

/**
 * Sends a Google Drive link to the backend to be downloaded, parsed, and text-extracted.
 * @param {string} link - The raw URL.
 * @param {string} access_token - Optional OAuth token.
 * @returns {Promise<Object>} An object containing the extracted files data.
 */
export const loadDriveLink = async (link, access_token) => {
  const response = await fetch(`${BASE_URL}/load_link`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ link, access_token }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Loading failed');
  }
  return response.json();
};

/**
 * Sends a Google Drive link to the backend and consumes a live Server-Sent Event (SSE) stream.
 * @param {string} link - The raw URL.
 * @param {string} access_token - Optional OAuth token.
 * @param {function} onChunk - Callback fired instantly when a new file chunk is received.
 */


/**
 * Pre-flights a Google Drive link to determine if it is public or requires authentication,
 * without actually downloading the file contents.
 * @param {string} link - The raw URL.
 * @param {string} access_token - Optional OAuth token.
 * @returns {Promise<Object>} Status object (public/locked).
 */
export const checkLink = async (link, access_token) => {
  const response = await fetch(`${BASE_URL}/check_link`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ link, access_token }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Checking failed');
  }
  return response.json();
};

/**
 * Fetches all vector database collections (namespaces) currently stored in ChromaDB.
 * @returns {Promise<Object>} List of namespace strings.
 */
export const fetchNamespaces = async () => {
  const response = await fetch(`${BASE_URL}/namespaces`);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch namespaces');
  }
  return response.json();
};

/**
 * Enqueues a folder/file link to the Kafka background ingestion pipeline.
 * @param {string} link - The raw URL.
 * @param {string} access_token - Optional OAuth token.
 */
export const enqueueLink = async (link, access_token = null) => {
  const response = await fetch(`${BASE_URL}/enqueue_link`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ link, access_token }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to enqueue link');
  }
  return response.json();
};

/**
 * Sends extracted text chunks to the backend to be mathematically embedded and saved into ChromaDB.
 * @param {Array<string>} texts - The raw text strings.
 * @param {string} namespace - The collection ID.
 */
export const vectorizeTexts = async (texts, namespace) => {
  const response = await fetch(`${BASE_URL}/vectorize`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ texts, namespace }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Vectorization failed');
  }
  return response.json();
};

/**
 * Submits a natural language query to the backend Omni-Search RAG pipeline.
 * @param {string} query_text - The user's question.
 * @param {number} n_results - Number of chunks to retrieve per database.
 * @returns {Promise<Object>} The AI's answer.
 */
export const queryNamespace = async (query_text, namespaces = null, n_results = 4) => {
  const body = { query_text, n_results };
  if (namespaces && namespaces.length > 0) {
    body.namespaces = namespaces;
  }
  const response = await fetch(`${BASE_URL}/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Query failed');
  }
  return response.json();
};

/**
 * Deletes a vector database collection and triggers a SQLite VACUUM to reclaim disk space.
 * @param {string} namespace - The collection ID to delete.
 */
export const purgeNamespace = async (namespace) => {
  const response = await fetch(`${BASE_URL}/purge`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ namespace }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Purge failed');
  }
  return response.json();
};

/**
 * Deletes multiple vector databases in a single batch and triggers a SQLite VACUUM once.
 * @param {Array<string>} namespaces - The collection IDs to delete.
 */
export const purgeBatchNamespaces = async (namespaces) => {
  const response = await fetch(`${BASE_URL}/purge_batch`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ namespaces }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Batch purge failed');
  }
  return response.json();
};
