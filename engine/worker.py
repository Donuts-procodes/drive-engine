import os
import json
import signal
import logging
import asyncio
from dotenv import load_dotenv
load_dotenv()
from confluent_kafka import Consumer, KafkaError

from engine.connectors import get_connector_for_url
from engine.rag_core import ingest_texts_async, file_exists_in_db

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# Wait for Kafka Broker and topic to be ready
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_VECTORIZE_TOPIC", "vectorize-tasks")

# Graceful shutdown flag
_shutdown_requested = False

def _handle_signal(signum, frame):
    global _shutdown_requested
    logger.info("Received shutdown signal (%s). Finishing current task...", signal.Signals(signum).name)
    _shutdown_requested = True

def start_worker():
    global _shutdown_requested
    
    # Register signal handlers for graceful shutdown (Fix #5)
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    
    logger.info("Starting Kafka Consumer on %s, Topic: %s", KAFKA_BROKERS, KAFKA_TOPIC)
    try:
        consumer = Consumer({
            'bootstrap.servers': KAFKA_BROKERS,
            'group.id': 'vectorize-group',
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': True,
            'fetch.message.max.bytes': 52428800,
            'max.poll.interval.ms': 3600000,
        })
        consumer.subscribe([KAFKA_TOPIC])
    except Exception as e:
        logger.error("Failed to connect to Kafka: %s", e)
        return
        
    logger.info("Listening for vectorization tasks...")
    try:
        while not _shutdown_requested:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    logger.error("Kafka error: %s", msg.error())
                    continue
                    
            try:
                payload = json.loads(msg.value().decode('utf-8'))
            except Exception as e:
                logger.error("Failed to decode message: %s", e)
                continue
                
            link = payload.get("link")
            access_token = payload.get("access_token")
            logger.info("Received URL task: %s", link)
            
            try:
                connector = get_connector_for_url(link)
                result = connector.check_link(link, access_token)
                
                # Progress tracking state
                progress_state = {"total": 0, "completed": 0, "failed": 0, "skipped": 0}
                log_file_path = "/app/local_chroma_db/worker_progress.log"
                
                def log_progress(msg):
                    logger.info(msg)
                    try:
                        with open(log_file_path, "a") as f:
                            f.write(msg + "\n")
                    except Exception as e:
                        logger.warning("Failed to write progress log: %s", e)

                log_progress(f"[Progress] Starting ingestion job for {link}")

                # Limit concurrent embedding tasks to prevent CPU/RAM overload
                semaphore = asyncio.Semaphore(5)
                
                async def process_file(file_data):
                    async with semaphore:
                        if file_data.get("skipped"):
                            progress_state["skipped"] += 1
                            log_progress(f"[Progress] {progress_state['completed'] + progress_state['skipped']}/{progress_state['total']} - Skipped duplicate: {file_data.get('name')}")
                            return
                        if file_data.get("status") in ["metadata", "error"]:
                            if file_data.get("status") == "error":
                                progress_state["failed"] += 1
                            else:
                                # Metadata status sets the total count
                                progress_state["total"] = file_data.get("total_files", 0)
                                log_progress(f"[Progress] Discovered {progress_state['total']} total files.")
                            return
                        
                        texts = file_data.get("texts", [])
                        if file_data.get("text"):
                            texts.append(file_data.get("text"))
                        if not texts:
                            progress_state["failed"] += 1
                            log_progress(f"[Progress] {progress_state['completed'] + progress_state['skipped'] + progress_state['failed']}/{progress_state['total']} - Failed (No Text): {file_data.get('name')}")
                            return
                        
                        try:
                            await ingest_texts_async(
                                texts=texts,
                                namespace=file_data.get("namespace"),
                                source=connector.source,
                                name=file_data.get("name", "Unknown"),
                                tika_metadata=file_data.get("tika_metadata"),
                                file_id=file_data.get("id")
                            )
                            progress_state["completed"] += 1
                            log_progress(f"[Progress] {progress_state['completed'] + progress_state['skipped'] + progress_state['failed']}/{progress_state['total']} - Successfully vectorized: {file_data.get('name')}")
                        except Exception as e:
                            progress_state["failed"] += 1
                            log_progress(f"[Progress] {progress_state['completed'] + progress_state['skipped'] + progress_state['failed']}/{progress_state['total']} - Error vectorizing {file_data.get('name')}: {e}")

                async def run_ingestion():
                    tasks = []
                    if result.type == "folder":
                        for file_data in connector.stream_folder(link, access_token, skip_callback=file_exists_in_db):
                            file_data["namespace"] = file_data.get("id") or link
                            tasks.append(asyncio.create_task(process_file(file_data)))
                    else:
                        file_data = connector.stream_file(link, access_token, skip_callback=file_exists_in_db)
                        file_data.update({"namespace": link, "id": file_data.get("id") or link})
                        progress_state["total"] = 1
                        tasks.append(asyncio.create_task(process_file(file_data)))
                        
                    if tasks:
                        await asyncio.gather(*tasks)
                        
                asyncio.run(run_ingestion())
                log_progress(f"[Progress] Finished job. Completed: {progress_state['completed']}, Skipped: {progress_state['skipped']}, Failed: {progress_state['failed']}")
                
            except Exception as e:
                logger.error("Error processing %s: %s", link, e, exc_info=True)
    finally:
        # Graceful shutdown: close consumer to commit final offsets
        logger.info("Closing Kafka consumer...")
        consumer.close()
        logger.info("Worker shut down gracefully.")

if __name__ == "__main__":
    start_worker()
