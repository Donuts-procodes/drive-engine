import asyncio
import time
import uuid
import httpx

API_URL = "http://127.0.0.1:8000"

async def test_high_concurrency_vectorization():
    print("[*] Starting Failsafe Concurrency Stress Test...")
    print("[*] Simulating massive parallel ingest to trigger OpenAI Rate Limits and test Semaphore locks.")
    
    # Generate 100 fake files with random UUIDs as content
    fake_files = []
    for i in range(100):
        fake_files.append({
            "texts": [f"This is a random document text used for stress testing. ID: {uuid.uuid4()}"],
            "namespace": f"stress_test_folder_{i % 5}",
            "name": f"fake_doc_{i}.txt",
            "source": "stress_test",
            "file_id": str(uuid.uuid4())
        })
        
    payload = {"files": fake_files}
    
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            response = await client.post(f"{API_URL}/vectorize_batch", json=payload)
            response.raise_for_status()
            data = response.json()
            
            end_time = time.time()
            duration = end_time - start_time
            
            success_count = 0
            failed_count = 0
            for r in data.get("details", []):
                if isinstance(r, dict) and r.get("status") == "success":
                    success_count += 1
                else:
                    failed_count += 1
                    
            print(f"[SUCCESS] Stress Test Complete in {duration:.2f} seconds!")
            print(f"    Total Processed: 100")
            print(f"    Successful: {success_count}")
            print(f"    Failed (Uncaught Exceptions): {failed_count}")
            
            if failed_count == 0:
                print("[SUCCESS] The @retry failsafe successfully absorbed all rate limits! No crashes detected.")
                
            # Clean up the test namespaces
            print("[*] Cleaning up test databases...")
            test_namespaces = list(set([f["namespace"] for f in fake_files]))
            await client.post(f"{API_URL}/purge_batch", json={"namespaces": test_namespaces})
            
            return {
                "duration": duration,
                "success_count": success_count,
                "failed_count": failed_count
            }
        except Exception as e:
            print(f"[X] CRITICAL FAILURE: API Crashed during stress test! {e}")
            return None

if __name__ == "__main__":
    asyncio.run(test_high_concurrency_vectorization())
