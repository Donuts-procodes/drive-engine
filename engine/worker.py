import os
import json
import asyncio
from dotenv import load_dotenv
load_dotenv()
from confluent_kafka import Consumer, KafkaError

from engine.connectors import get_connector_for_url
from engine.rag_core import ingest_texts_async, file_exists_in_db

# Wait for Kafka Broker and topic to be ready
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_VECTORIZE_TOPIC", "vectorize-tasks")

def start_worker():
    print(f"[Worker] Starting Kafka Consumer on {KAFKA_BROKERS}, Topic: {KAFKA_TOPIC}")
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
        print(f"[Worker] Failed to connect to Kafka: {e}")
        return
        
    print("[Worker] Listening for vectorization tasks...")
    while True:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            else:
                print(f"[Worker] Error: {msg.error()}")
                continue
                
        try:
            payload = json.loads(msg.value().decode('utf-8'))
        except Exception as e:
            print(f"[Worker] Failed to decode message: {e}")
            continue
            
        link = payload.get("link")
        access_token = payload.get("access_token")
        print(f"[Worker] Received URL task: {link}")
        
        try:
            connector = get_connector_for_url(link)
            result = connector.check_link(link, access_token)
            
            async def process_file(file_data):
                if file_data.get("skipped"):
                    print(f"[Worker] Skipped duplicate: {file_data.get('name')}")
                    return
                if file_data.get("status") in ["metadata", "error"]:
                    print(f"[Worker] Warning: {file_data.get('status')} - {file_data.get('name')}")
                    return
                
                texts = file_data.get("texts", [])
                if file_data.get("text"):
                    texts.append(file_data.get("text"))
                if not texts:
                    return
                
                await ingest_texts_async(
                    texts=texts,
                    namespace=file_data.get("namespace"),
                    source=connector.source,
                    name=file_data.get("name", "Unknown"),
                    tika_metadata=file_data.get("tika_metadata"),
                    file_id=file_data.get("id")
                )
                print(f"[Worker] Successfully vectorized {file_data.get('name')}")

            async def run_ingestion():
                if result.type == "folder":
                    for file_data in connector.stream_folder(link, access_token, skip_callback=file_exists_in_db):
                        file_data["namespace"] = file_data.get("id") or link
                        await process_file(file_data)
                else:
                    file_data = connector.stream_file(link, access_token, skip_callback=file_exists_in_db)
                    file_data.update({"namespace": link, "id": file_data.get("id") or link})
                    await process_file(file_data)
                    
            asyncio.run(run_ingestion())
            print(f"[Worker] Finished processing task for: {link}")
            
        except Exception as e:
            print(f"[Worker] Error processing {link}: {e}")

if __name__ == "__main__":
    start_worker()
