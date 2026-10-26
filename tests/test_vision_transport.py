"""Real HTTP path of the vision client, against a local fake OpenAI-compatible server."""
import base64
import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from tactile import autolabel, samples  # noqa: E402

LOG = []
BEHAVIOUR = {"fn": None}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        LOG.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        code, payload = BEHAVIOUR["fn"](body)
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_port}/v1"
reply = lambda text: (200, {"choices": [{"message": {"content": text}}]})
img = samples.render("lens")


def expect_error(fn, needle):
    try:
        fn()
    except autolabel.VisionError as e:
        assert needle in str(e), f"wanted {needle!r} in {e}"
        return
    raise AssertionError(f"no error raised (wanted {needle!r})")


# --- configuration validation -------------------------------------------------------
autolabel.clear()
assert not autolabel.available()
expect_error(lambda: autolabel.configure("gemini", "short"), "too short")
expect_error(lambda: autolabel.configure("nope", "x" * 20), "Unknown provider")
expect_error(lambda: autolabel.configure("custom", "x" * 20, "m", "http://evil.example.com/v1"), "base URL")
expect_error(lambda: autolabel.configure("custom", "x" * 20, "", "https://ok.example.com/v1"), "model")
autolabel.configure("gemini", "AIza" + "x" * 30)
assert autolabel.available() and autolabel.active_provider()["id"] == "gemini"
assert autolabel._active()["base"].startswith("https://generativelanguage.googleapis.com")
autolabel.clear()

# --- happy path: request shape + reply cleaning ------------------------------------
autolabel.configure("custom", "k" * 20, "m1", BASE)
BEHAVIOUR["fn"] = lambda b: reply("<think>the circle is on the lens</think>\nLabel: \"Converging lens.\"\nmore text")
assert autolabel.identify(img, 0.5, 0.5) == "Converging lens"
req = LOG[-1]
assert req["path"] == "/v1/chat/completions", req["path"]
assert req["auth"] == "Bearer " + "k" * 20
assert req["body"]["model"] == "m1" and req["body"]["max_tokens"] >= 300
parts = req["body"]["messages"][0]["content"]
assert parts[0]["type"] == "text" and "red circle" in parts[0]["text"]
assert parts[1]["type"] == "image_url"
url = parts[1]["image_url"]["url"]
assert url.startswith("data:image/png;base64,")
sent = cv2.imdecode(np.frombuffer(base64.b64decode(url.split(",", 1)[1]), np.uint8), cv2.IMREAD_COLOR)
h, w = sent.shape[:2]
b, g, r = sent[int(.5 * (h - 1)), int(.5 * (w - 1))]
assert r > 200 and g < 60 and b < 60, "red marker not at the pointer position in the image that was sent"

# --- reply shapes ------------------------------------------------------------------
BEHAVIOUR["fn"] = lambda b: (200, {"choices": [{"message": {"content": [{"type": "text", "text": "Lens"}]}}]})
assert autolabel.identify(img, .5, .5) == "Lens"
BEHAVIOUR["fn"] = lambda b: reply("")
expect_error(lambda: autolabel.identify(img, .5, .5), "returned nothing")
BEHAVIOUR["fn"] = lambda b: (200, {"unexpected": True})
expect_error(lambda: autolabel.identify(img, .5, .5), "unexpected reply")

# --- HTTP errors map to readable messages --------------------------------------------
for code, needle in ((401, "rejected the key"), (403, "rejected the key"), (429, "rate limit"),
                     (404, "does not know the model 'm1'"), (500, "(500)")):
    BEHAVIOUR["fn"] = lambda b, c=code: (c, {"error": {"message": "boom"}})
    expect_error(lambda: autolabel.identify(img, .5, .5), needle)

# --- unknown model falls back to the next one (preset providers only) -----------------
saved = dict(autolabel.PROVIDERS["custom"])
autolabel.PROVIDERS["custom"].update(model="m1", fallbacks=["m2"])
autolabel.configure("custom", "k" * 20, None, BASE)
BEHAVIOUR["fn"] = lambda b: reply("Image") if b["model"] == "m2" else (404, {"error": "no such model"})
n = len(LOG)
assert autolabel.identify(img, .8, .6) == "Image"
assert [x["body"]["model"] for x in LOG[n:]] == ["m1", "m2"], "should try m1 then fall back to m2"
BEHAVIOUR["fn"] = lambda b: (401, {})                      # but a bad key must NOT cycle through models
n = len(LOG)
expect_error(lambda: autolabel.identify(img, .5, .5), "rejected the key")
assert len(LOG) == n + 1, "auth errors must not trigger model fallback"
autolabel.PROVIDERS["custom"].update(saved)

# --- suggest_labels with a code-fenced JSON reply -------------------------------------
autolabel.configure("custom", "k" * 20, "m1", BASE)
BEHAVIOUR["fn"] = lambda b: reply('Here you go:\n```json\n[{"text":"Lens","tx":0.5,"ty":0.3,"x":0.5,"y":0.1},'
                                  '{"text":"Objéct","tx":0.2,"ty":0.4,"x":0.1,"y":0.2}]\n```')
labs = autolabel.suggest_labels(img, 8)
assert [l["text"] for l in labs] == ["Lens", "Object"] and labs[0]["ax"] == 0.5, labs
BEHAVIOUR["fn"] = lambda b: reply("I cannot do that")
expect_error(lambda: autolabel.suggest_labels(img, 8), "no usable JSON list")
BEHAVIOUR["fn"] = lambda b: reply("[not json]")
expect_error(lambda: autolabel.suggest_labels(img, 8), "no usable JSON list")

BEHAVIOUR["fn"] = lambda b: reply('{"parts":[{"text":"Lens","x":0.5,"y":0.2,"tx":0.4,"ty":0.3}]}')
assert autolabel.suggest_labels(img)[0]["text"] == "Lens"
BEHAVIOUR["fn"] = lambda b: reply('{"parts":[{"text":"Lens","x":"bad","y":0.2}]}')
expect_error(lambda: autolabel.suggest_labels(img), "no valid labels")

# --- unreachable provider ---------------------------------------------------------------
autolabel.configure("custom", "k" * 20, "m1", "http://127.0.0.1:9/v1")
expect_error(lambda: autolabel.identify(img, .5, .5), "Could not reach")

print("vision transport OK (8 groups, against a local fake server)")
