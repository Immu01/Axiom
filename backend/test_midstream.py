import json
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = "http://127.0.0.1:8000"


def debug(path):
    r = httpx.post(f"{BASE}{path}", headers={"X-Admin-Token": os.getenv("ADMIN_TOKEN", "")}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"Debug call failed ({r.status_code}). Set ADMIN_TOKEN in backend/.env and restart the server.")
    return r.json()
debug("/api/debug/clear")
print(debug("/api/debug/break/groq/15"))

body = {"messages": [{"role": "user", "content":
        "Write a 120-word story about a lighthouse keeper and a lost robot. Plain text, no formatting."}]}

parts, current, event = [], None, None
with httpx.Client(timeout=90) as c:
    with c.stream("POST", f"{BASE}/api/chat/stream", json=body) as r:
        for line in r.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:") and event:
                data = json.loads(line[5:].strip() or "{}")
                if event == "meta":
                    current = data["provider"]
                    parts.append([current, ""])
                elif event == "token":
                    parts[-1][1] += data["text"]
                elif event == "error":
                    print("ERROR EVENT:", data)
                event = None

debug("/api/debug/clear")

print("\n===== ANSWER, SHOWN AS THE PROVIDERS WROTE IT =====")
for provider, text in parts:
    print(f"\n[{provider}] {text}")

print("\n===== WHAT THE USER SEES =====")
print("".join(t for _, t in parts))
print("\nProviders used:", [p for p, _ in parts])
print("PASS" if len(parts) >= 2 else "FAIL", "- answer continued on a second provider" if len(parts) >= 2 else "- no switch happened")
