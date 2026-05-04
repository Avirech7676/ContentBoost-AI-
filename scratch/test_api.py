import requests
import json

url = "http://127.0.0.1:8000/generate"
payload = {
    "product_name": "Test Product",
    "tone": "persuasive"
}
# We need to login first or use a test account
# Actually I'll just check if the server logs show anything when I hit it.
# Or I can use the health check which worked.

def test_gen():
    # Try to generate without auth first to see if we get 401
    res = requests.post(url, json=payload)
    print(f"Status: {res.status_code}")
    print(f"Body: {res.text}")

if __name__ == "__main__":
    test_gen()
