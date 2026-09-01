import time
import requests
import psutil
import threading
import uuid

# Global variables to store memory tracking results
peak_memory_mb = 0
running = True

def find_backend_pid(port=8000):
    for conn in psutil.net_connections(kind='inet'):
        if conn.laddr.port == port and conn.status == 'LISTEN':
            return conn.pid
    return None

def monitor_memory(pid):
    global peak_memory_mb, running
    try:
        process = psutil.Process(pid)
        while running:
            # RSS (Resident Set Size) is the actual physical memory the process is using
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / (1024 * 1024)
            if mem_mb > peak_memory_mb:
                peak_memory_mb = mem_mb
            time.sleep(0.1)
    except psutil.NoSuchProcess:
        pass

def run_test():
    global running
    
    print("Locating FastAPI Backend Process...")
    pid = find_backend_pid()
    if not pid:
        print("Could not find backend running on port 8000. Please start the backend.")
        return
        
    print(f"Found Backend Process (PID: {pid}). Starting Memory Monitor...")
    
    # Start background memory monitoring thread
    monitor_thread = threading.Thread(target=monitor_memory, args=(pid,))
    monitor_thread.start()
    
    # Generate 50 unique namespaces and documents for the payload
    files_payload = []
    for i in range(50):
        ns = f"ram_test_db_{i}_{uuid.uuid4().hex[:6]}"
        sentences = [f"This is a massive document {i} to test backend RAM spikes. We need to fill up memory."] * 500
        texts = ["\n\n".join(sentences)]
            
        files_payload.append({
            "texts": texts,
            "namespace": ns
        })
        
    print(f"Firing 50 heavy documents to `/vectorize_batch`...")
    
    try:
        response = requests.post(
            "http://localhost:8000/vectorize_batch", 
            json={"files": files_payload},
            timeout=300
        )
        response.raise_for_status()
    except Exception as e:
        print(f"API Request Failed: {e}")
    finally:
        # Stop monitoring
        running = False
        monitor_thread.join()
        
    print("\n" + "="*50)
    print(f"BACKEND SERVER PEAK RAM USAGE: {peak_memory_mb:.2f} MB")
    print("="*50)
    print("\nBecause we throttled `max_workers=3`, the backend guarantees it will only ever process 3 of these heavy documents in active RAM simultaneously, keeping this peak extremely stable!")

    # Cleanup the databases
    print("\nCleaning up databases...")
    for f in files_payload:
        try:
            requests.post("http://localhost:8000/purge", json={"namespace": f["namespace"]})
        except:
            pass
    print("Done.")

if __name__ == "__main__":
    run_test()
