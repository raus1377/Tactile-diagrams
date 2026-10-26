"""Run the app with a FAKE vision model, so the naming flow works with no API key.

    python tests/serve_stub.py          # http://127.0.0.1:5055

The fake names a part by where the pointer sits (left third = Object, middle =
Converging lens, right third = Image). Useful for trying the UI offline and for
the automated UI test; it is not a real recogniser.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import app as webapp  # noqa: E402
from tactile import autolabel  # noqa: E402


def fake_ask(png, prompt, model, max_tokens):
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if "red circle" in prompt:
        red = (img[:, :, 2] > 200) & (img[:, :, 1] < 60) & (img[:, :, 0] < 60)
        xs = np.nonzero(red)[1]
        cx = xs.mean() / img.shape[1] if len(xs) else 0.5
        return "Object" if cx < 0.35 else ("Converging lens" if cx < 0.65 else "Image")
    return json.dumps([
        {"text": "Object", "tx": 0.2, "ty": 0.43, "x": 0.12, "y": 0.3},
        {"text": "Converging lens", "tx": 0.5, "ty": 0.25, "x": 0.5, "y": 0.1},
        {"text": "Image", "tx": 0.8, "ty": 0.64, "x": 0.88, "y": 0.75},
    ])


autolabel._ask = fake_ask

if __name__ == "__main__":
    webapp.app.run(host="127.0.0.1", port=5055, debug=False)
