import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
url = "https://api.groq.com/openai/v1/models"
headers = {"Authorization": f"Bearer {api_key}"}

response = requests.get(url, headers=headers)
if response.status_code == 200:
    models = response.json().get("data", [])
    print("Available Groq models:")
    for m in models:
        print(f" - {m['id']}")
else:
    print(f"Error fetching models: {response.text}")
