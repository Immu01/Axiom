import json
import time
import httpx

BASE = "http://127.0.0.1:8000"


def ask(prompt="Say hi in one short sentence."):
    body = {"messages": [{"role": "user", "content": prompt}]}
    provider, text, error, first = None, "", None, None
    start = time.time()
    with httpx.Client(timeout=90) as c:
        with c.stream("POST", f"{BASE}/api/chat/stream", json=body) as r:
            event = None
            for line in r.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and event:
                    data = json.loads(line[5:].strip() or "{}")
                    if event == "meta":
                        provider = data.get("provider")
                    elif event == "token":
                        if first is None:
                            first = time.time() - start
                        text += data.get("text", "")
                    elif event == "error":
                        error = data.get("message")
                    event = None
    return provider, text, error, first


def get(path):
    return httpx.get(f"{BASE}{path}", timeout=30).json()


results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


print("\n== Config ==")
cfg = get("/api/config-check")
for name, info in cfg.items():
    print(f"  {name}: keys={info['keys_loaded']} model={info['model']}")
    check(f"{name} is configured", info["keys_loaded"] > 0 and info["model"] != "(not set)")

get("/api/debug/clear")

print("\n== Test 1: normal request (expect groq) ==")
p, t, e, f = ask()
check("Groq answers normally", p == "groq" and bool(t), f"provider={p} first_token={f and round(f, 2)}s")
print("  reply:", t[:100])

print("\n== Test 2: Groq broken (expect gemini) ==")
get("/api/debug/fail/groq")
p, t, e, f = ask()
check("Switches to Gemini", p == "gemini" and bool(t), f"provider={p} error={e}")
print("  reply:", t[:100])

print("\n== Test 3: Groq + Gemini broken (expect openrouter) ==")
get("/api/debug/fail/gemini")
p, t, e, f = ask()
check("Switches to OpenRouter", p == "openrouter" and bool(t), f"provider={p} error={e}")
print("  reply:", t[:100])

print("\n== Test 4: everything broken (expect friendly error) ==")
get("/api/debug/fail/openrouter")
p, t, e, f = ask()
check("Friendly error, no raw codes", bool(e) and not t and "429" not in e, f"message={e}")

print("\n== Test 5: healed (expect groq again) ==")
get("/api/debug/clear")
p, t, e, f = ask()
check("Back to Groq after healing", p == "groq" and bool(t), f"provider={p}")

print("\n== Test 6: memory ==")
body = {"messages": [
    {"role": "user", "content": "My favourite number is 47."},
    {"role": "assistant", "content": "Nice, 47 it is!"},
    {"role": "user", "content": "What is my favourite number?"},
]}
text = ""
with httpx.Client(timeout=60) as c:
    with c.stream("POST", f"{BASE}/api/chat/stream", json=body) as r:
        ev = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:") and ev == "token":
                text += json.loads(line[5:].strip())["text"]
check("Remembers earlier messages", "47" in text, f"reply={text[:80]!r}")

print(f"\n== RESULT: {sum(results)}/{len(results)} checks passed ==")
print("Final status:", json.dumps(get("/api/status")))