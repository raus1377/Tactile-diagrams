"""Tactile diagram generator: upload a diagram, get a Braille-labelled SVG
ready for swell paper, embossing or 3D printing.

    pip install -r requirements.txt
    python app.py            # http://127.0.0.1:5000
"""
from __future__ import annotations

import collections
import uuid

import cv2
from flask import Flask, Response, jsonify, request

from tactile import autolabel, outline, pipeline, samples

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

_STORE: "collections.OrderedDict[str, object]" = collections.OrderedDict()
_STORE_MAX = 24


def _remember(key, img):
    _STORE[key] = img
    _STORE.move_to_end(key)
    while len(_STORE) > _STORE_MAX:
        _STORE.popitem(last=False)


def _image(image_id):
    if image_id in _STORE:
        return _STORE[image_id]
    if image_id and image_id.startswith("sample:"):
        sid = image_id.split(":", 1)[1]
        if sid in samples.SAMPLES:
            img = samples.render(sid)
            _remember(image_id, img)
            return img
    return None


def _erase_rects(raw):
    """Validate user-drawn erase rectangles: [[x0, y0, x1, y1], ...] as 0..1 fractions."""
    out = []
    for r in (raw or [])[:50]:
        if not isinstance(r, (list, tuple)) or len(r) != 4:
            continue
        x0, y0, x1, y1 = (min(max(float(v), 0.0), 1.0) for v in r)
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        if x1 - x0 > 0 and y1 - y0 > 0:
            out.append((x0, y0, x1, y1))
    return out


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/samples")
def api_samples():
    return jsonify({
        "samples": samples.catalog(),
        "ai_labels": autolabel.available(),
        "ai_provider": autolabel.active_provider(),
        "providers": autolabel.provider_list(),
    })


@app.post("/api/upload")
def api_upload():
    f = request.files.get("file")
    if not f:
        return jsonify(error="No file uploaded."), 400
    try:
        img = outline.load_image(f.read())
    except Exception:
        return jsonify(error="That file could not be read as an image."), 400
    image_id = uuid.uuid4().hex
    _remember(image_id, img)
    return jsonify(image_id=image_id, width=img.shape[1], height=img.shape[0])


@app.get("/api/source/<path:image_id>.png")
def api_source(image_id):
    img = _image(image_id)
    if img is None:
        return Response(status=404)
    ok, buf = cv2.imencode(".png", img)
    return Response(buf.tobytes(), mimetype="image/png")


@app.post("/api/process")
def api_process():
    p = request.get_json(silent=True) or {}
    img = _image(p.get("image_id"))
    if img is None:
        return jsonify(error="Unknown image. Upload it again."), 404
    mode = p.get("mode", "auto")
    if mode not in ("auto", "solid", "edges"):
        mode = "auto"
    try:
        out = pipeline.run(
            img,
            mode=mode,
            sensitivity=min(max(int(p.get("sensitivity", 30)), 1), 40),
            detail=min(max(int(p.get("detail", 25)), 0), 100),
            line_mm=min(max(float(p.get("line_mm", 1.4)), 0.6), 3.5),
            title=str(p.get("title", ""))[:200],
            labels=[l for l in (p.get("labels") or []) if isinstance(l, dict)],
            ink=bool(p.get("ink", True)),
            border=bool(p.get("border", True)),
            erase=_erase_rects(p.get("erase")),
        )
    except (TypeError, ValueError):
        return jsonify(error="Invalid settings."), 400
    return jsonify(out)


@app.post("/api/key")
def api_key():
    p = request.get_json(silent=True) or {}
    try:
        autolabel.configure(str(p.get("provider", "gemini")), str(p.get("key", "")),
                            str(p.get("model", "")) or None, str(p.get("base", "")) or None)
    except autolabel.VisionError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(ai_labels=True, ai_provider=autolabel.active_provider())


@app.post("/api/identify")
def api_identify():
    if not autolabel.available():
        return jsonify(error="Add a free API key to name parts automatically."), 501
    p = request.get_json(silent=True) or {}
    img = _image(p.get("image_id"))
    if img is None:
        return jsonify(error="Unknown image. Upload it again."), 404
    try:
        text = autolabel.identify(img, float(p.get("x", 0.5)), float(p.get("y", 0.5)))
    except autolabel.VisionError as exc:
        return jsonify(error=str(exc)), 502
    except (TypeError, ValueError) as exc:
        return jsonify(error=f"Could not name that part: {exc}"), 502
    return jsonify(text=text)


@app.post("/api/autolabel")
def api_autolabel():
    if not autolabel.available():
        return jsonify(error="Add a free API key to name parts automatically."), 501
    p = request.get_json(silent=True) or {}
    img = _image(p.get("image_id"))
    if img is None:
        return jsonify(error="Unknown image. Upload it again."), 404
    try:
        labels = autolabel.suggest_labels(img, min(int(p.get("max_labels", 8)), 12))
    except autolabel.VisionError as exc:
        return jsonify(error=str(exc)), 502
    except (TypeError, ValueError) as exc:
        return jsonify(error=f"Label suggestion failed: {exc}"), 502
    return jsonify(labels=labels)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
