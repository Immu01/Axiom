import json
import httpx

BASE = "http://127.0.0.1:8000"
httpx.get(f"{BASE}/api/debug/clear")
print(httpx.get(f"{BASE}/api/debug/break/groq/15").json())

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

httpx.get(f"{BASE}/api/debug/clear")

print("\n===== ANSWER, SHOWN AS THE PROVIDERS WROTE IT =====")
for provider, text in parts:
    print(f"\n[{provider}] {text}")

print("\n===== WHAT THE USER SEES =====")
print("".join(t for _, t in parts))
print("\nProviders used:", [p for p, _ in parts])
print("PASS" if len(parts) >= 2 else "FAIL", "- answer continued on a second provider" if len(parts) >= 2 else "- no switch happened")
