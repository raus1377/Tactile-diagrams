"""Naming flow with the vision call stubbed out (no API key or network needed)."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import app as webapp  # noqa: E402
from tactile import autolabel  # noqa: E402

calls = []


def fake_ask(png, prompt, model, max_tokens):
    calls.append({"png": png, "prompt": prompt, "model": model})
    if "red circle" in prompt:
        return '  "Converging lens."\nextra line ignored'
    return json.dumps([
        {"text": "Lens", "tx": 0.5, "ty": 0.3, "x": 0.5, "y": 0.1},
        {"text": "Object θ", "tx": 0.2, "ty": 0.4, "x": 0.1, "y": 0.2},   # non-ASCII must be stripped
        {"text": "", "tx": 0.1, "ty": 0.1, "x": 0.1, "y": 0.1},            # empty must be skipped
        {"text": "Bad", "tx": "nope"},                                      # malformed must be skipped
    ])


autolabel._ask = fake_ask
autolabel.clear()
import os  # noqa: E402
for v in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "VISION_API_KEY"):
    os.environ.pop(v, None)
c = webapp.app.test_client()
post = lambda url, body: c.post(url, json=body)

# 1. no key -> 501 on both naming endpoints
assert post("/api/identify", {"image_id": "sample:lens", "x": .5, "y": .5}).status_code == 501
assert post("/api/autolabel", {"image_id": "sample:lens"}).status_code == 501

# 2. key validation, then enabled
assert post("/api/key", {"provider": "gemini", "key": "short"}).status_code == 400
assert post("/api/key", {"provider": "custom", "key": "x" * 20, "model": "m", "base": ""}).status_code == 400
r = post("/api/key", {"provider": "gemini", "key": "AIza" + "x" * 30})
assert r.status_code == 200 and r.get_json()["ai_labels"] is True
cat = c.get("/api/samples").get_json()
assert cat["ai_labels"] is True and cat["ai_provider"]["id"] == "gemini"
assert [p["id"] for p in cat["providers"]] == ["gemini", "openrouter", "custom"]
assert cat["providers"][2]["needs_base"] is True

# 3. identify: cleaned text, fast model, red marker drawn at the pointer
r = post("/api/identify", {"image_id": "sample:lens", "x": 0.5, "y": 0.5})
assert r.status_code == 200 and r.get_json()["text"] == "Converging lens", r.get_json()
sent = cv2.imdecode(np.frombuffer(calls[-1]["png"], np.uint8), cv2.IMREAD_COLOR)
h, w = sent.shape[:2]
b, g, rr = sent[int(.5 * (h - 1)), int(.5 * (w - 1))]
assert rr > 200 and g < 60 and b < 60, "red marker missing at pointer position"

# 4. autolabel: parsed, ASCII-cleaned, bad rows dropped, targets returned as ax/ay
r = post("/api/autolabel", {"image_id": "sample:lens", "max_labels": 8})
labels = r.get_json()["labels"]
assert [l["text"] for l in labels] == ["Lens", "Object"], labels
assert labels[0]["ax"] == 0.5 and labels[0]["ay"] == 0.3 and labels[0]["y"] == 0.1

# 5. unknown image
assert post("/api/identify", {"image_id": "nope", "x": 0, "y": 0}).status_code == 404

# 6. a failing model call surfaces as a readable 502, not a crash
def boom(*a, **k):
    raise autolabel.VisionError("The provider rejected the key.")
autolabel._ask = boom
r = post("/api/identify", {"image_id": "sample:lens", "x": .5, "y": .5})
assert r.status_code == 502 and "rejected the key" in r.get_json()["error"]

print("naming flow OK (stubbed model)")
