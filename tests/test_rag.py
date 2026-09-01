from engine.rag_core import query_master_database

def test():
    print("Testing query_master_database...")
    try:
        ans = query_master_database("What is the secret password to the mainframe?", 4)
        print("Answer:", ans)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test()
