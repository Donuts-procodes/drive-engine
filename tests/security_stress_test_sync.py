import time
import requests
import uuid

API_URL = "http://127.0.0.1:8000"

def run_stress_test():
    print("[*] Starting synchronous stress test...")
    
    fake_files = []
    for i in range(10):
        fake_files.append({
            "texts": [f"This is a random document text used for stress testing. ID: {uuid.uuid4()}"],
            "namespace": f"stress_test_folder_{i % 2}",
            "name": f"fake_doc_{i}.txt",
            "source": "stress_test",
            "file_id": str(uuid.uuid4())
        })
        
    payload = {"files": fake_files}
    
    start_time = time.time()
    
    try:
        response = requests.post(f"{API_URL}/vectorize_batch", json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        end_time = time.time()
        print(f"[SUCCESS] Stress Test Complete in {end_time - start_time:.2f} seconds!")
        print(f"Data: {data}")
    except Exception as e:
        print(f"[X] CRITICAL FAILURE: {e}")

if __name__ == "__main__":
    run_stress_test()
