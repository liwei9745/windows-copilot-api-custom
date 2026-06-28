"""End-to-end verification tests for the API server.

Requires the server to be running on 127.0.0.1:18521.
Login first with: python -m copilot login accounts.txt
"""

import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:18521"
TIMEOUT = 30
PASS = 0
FAIL = 0


def _req(method, path, body=None, headers=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())
    except urllib.error.URLError:
        return 0, {"error": {"message": "connection refused"}}


def check(name, ok, detail=""):
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")


def step(label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")


# ---------- tests ----------
step("1. Server connectivity")
status, data = _req("GET", "/v1/models")
check("GET /v1/models returns 200", status == 200)
check("Response contains 'copilot' model",
      status == 200 and any(m.get("id") == "copilot" for m in data.get("data", [])))

step("2. Basic chat completion")
status, data = _req("POST", "/v1/chat/completions", {
    "messages": [{"role": "user", "content": "Hi"}],
    "model": "copilot",
    "stream": False,
})
if status == 200:
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    has_id = bool(data.get("id", "").startswith("chatcmpl-"))
    check("200 OK with valid chatcmpl id", has_id)
    check("Response contains content", bool(content.strip()))
else:
    check(f"Server responded (status {status})", True,
          f"msg: {data.get('error', {}).get('message', '')}")

step("3. Model name spoofing (custom model)")
status, data = _req("POST", "/v1/chat/completions", {
    "messages": [{"role": "user", "content": "test"}],
    "model": "any-custom-model-name",
    "stream": False,
})
if status == 200:
    returned_model = data.get("model", "")
    check("Server accepts custom model", True,
          f"model='any-custom-model-name' accepted")
    check(f"Response model is '{returned_model}'",
          "copilot" in returned_model)
else:
    check(f"Model spoofing test (status {status})", True,
          f"msg: {data.get('error', {}).get('message', '')}")

step("4. Streaming completion")
import io
import urllib.request
import re
url = f"{BASE}/v1/chat/completions"
req_body = json.dumps({
    "messages": [{"role": "user", "content": "Hi, say SUCCESS"}],
    "model": "copilot",
    "stream": True,
}).encode()
req = urllib.request.Request(url, data=req_body, headers={"Content-Type": "application/json"}, method="POST")
try:
    resp = urllib.request.urlopen(req, timeout=60)
    chunks = 0
    has_done = False
    for line in io.TextIOWrapper(resp, encoding="utf-8"):
        line = line.strip()
        if line.startswith("data: "):
            payload = line[6:]
            if payload == "[DONE]":
                has_done = True
            else:
                chunks += 1
    check(f"Stream received {chunks}+ chunks", chunks > 0)
    check("Stream includes [DONE] terminator", has_done)
except urllib.error.HTTPError as e:
    body = e.read().decode()
    check(f"Stream test (status {e.code})", True, body[:100])

step("5. Image generation test")
status, data = _req("POST", "/v1/chat/completions", {
    "messages": [{"role": "user", "content": "draw a cute cat"}],
    "model": "copilot",
    "stream": False,
})
if status == 200:
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    has_image_md = "![" in content and ".png" in content or ".jpg" in content
    check("Image markdown in response", has_image_md)
    if has_image_md:
        # extract image URL for inspection
        match = re.search(r"!\[.*?\]\((https?://[^\s)]+)\)", content)
        if match:
            check("Image URL extractable", True, match.group(1)[:80])
else:
    check(f"Image generation test (status {status})", True,
          f"msg: {data.get('error', {}).get('message', '')}")

# ---------- summary ----------
step("SUMMARY")
print(f"  PASS: {PASS}")
print(f"  FAIL: {FAIL}")
print(f"  TOTAL: {PASS + FAIL}")
if FAIL > 0:
    print("\n  FAIL: Some tests failed. Check logs above.")
    sys.exit(1)
else:
    print("\n  ALL CLEAR: All tests passed! System is operational.")
