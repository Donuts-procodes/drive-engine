import requests

def test_query():
    print("Sending query...")
    try:
        response = requests.post(
            "http://localhost:8000/query",
            json={"query_text": "What is the secret password to the mainframe?"}
        )
        response.raise_for_status()
        print("Response:", response.json())
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_query()
