import requests

# Base URL for your local backend
BASE_URL = "http://localhost:8000"

# Add your tokens here
TOKENS = {
    "CEO": "eyJhbGciOi...",
    "CFO": "eyJhbGciOi...",
    "HR": "eyJhbGciOi..."
}

# Add the endpoints you want to test safely (Avoid POST/PUT/DELETE for automated blank testing)
ENDPOINTS_TO_TEST = [
    "/person/me",
    "/company/profile",
    "/industry/classifications"
]

def test_endpoints():
    for role, token in TOKENS.items():
        print(f"\\n--- Testing as {role} ---")
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        for endpoint in ENDPOINTS_TO_TEST:
            url = f"{BASE_URL}{endpoint}"
            try:
                response = requests.get(url, headers=headers)
                print(f"[{response.status_code}] GET {endpoint}")
                
                # Optional: print response data for successful requests
                # if response.status_code == 200:
                #     print(response.json())
                    
            except Exception as e:
                print(f"[ERROR] GET {endpoint} failed: {e}")

if __name__ == "__main__":
    test_endpoints()
