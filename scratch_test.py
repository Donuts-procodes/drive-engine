import os
os.environ["MILVUS_HOST"] = "milvus"

from pymilvus import connections, utility

connections.connect("default", uri="http://milvus:19530")

if utility.has_collection("MASTER_COLLECTION"):
    print("Dropping collection...")
    utility.drop_collection("MASTER_COLLECTION")
    print("Dropped!")
else:
    print("Collection doesn't exist.")
