"""Vision-model naming of diagram parts, using FREE providers.

Any provider with an OpenAI-compatible chat endpoint that accepts images works:
  gemini      Google AI Studio free key (default)
  openrouter  OpenRouter free ":free" models
  custom      any other (Groq, NVIDIA NIM, ...): you supply base URL + model

Two jobs:
  suggest_labels(img)   name the key parts of a whole diagram, with a marker
                        position and the point on the part each one refers to
  identify(img, x, y)   name whatever a pointer is touching (used when the user
                        drags a pointer to a new part)

The key is pasted into the UI (or set via env) and lives only in this process's
memory. Standard library only: no extra dependency.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import math
import unicodedata
import urllib.error
import urllib.request

import cv2


log = logging.getLogger(__name__)


class VisionError(Exception):
    """A problem worth showing to the user as-is."""


# Free-tier model names change often, so every default is editable in the UI.
PROVIDERS = {
    "gemini": {
        "name": "Google Gemini (free key)",
        "base": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-3.5-flash-lite",
        "fallbacks": ["gemini-3.1-flash-lite", "gemini-2.5-flash"],
        "help_url": "https://aistudio.google.com/apikey",
        "help": "Free key from Google AI Studio, no card needed. On the free tier Google may use what you send to improve its products, so don't upload anything private.",
    },
    "openrouter": {
        "name": "OpenRouter (free models)",
        "base": "https://openrouter.ai/api/v1",
        "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "fallbacks": [],
        "help_url": "https://openrouter.ai/keys",
        "help": "Free key from OpenRouter. Use a model whose name ends in :free and that accepts images; free models rotate, so change the model name if this one is gone.",
    },
    "custom": {
        "name": "Other (OpenAI-compatible)",
        "base": "",
        "model": "",
        "fallbacks": [],
        "help_url": "",
        "help": "Any provider with an OpenAI-style /chat/completions endpoint and an image-capable model, for example Groq or NVIDIA NIM, or a local Ollama (http://localhost:11434/v1 with a vision model). Enter its base URL and model name.",
    },
}

_cfg: dict = {}

SUGGEST_PROMPT = """This diagram will be converted into a tactile graphic for a blind student.
Identify the key parts that need a label, at most {n}. For each give:
- "text": a short label of 1-3 words, plain ASCII (no symbols or Greek letters)
- "tx", "ty": a point ON the part itself, as fractions of image width and height
  (0,0 is top-left, 1,1 is bottom-right)
- "x", "y": where a small marker should sit, in clear white space close to the part
  and not on top of other lines
Return ONLY a JSON array like [{{"text": "Lens", "tx": 0.5, "ty": 0.3, "x": 0.5, "y": 0.15}}].
Do not wrap the list in prose. Coordinates must be numeric fractions between 0 and 1."""

IDENTIFY_PROMPT = """This is a diagram for a blind student. A red circle marks one point on it.
Name the part of the diagram that the circle is on or touching, in 1-3 plain ASCII words
(no symbols or Greek letters), the way a textbook would label it. If the circle is in empty
space, name the nearest part. Reply with the label only, nothing else."""


# ------------------------------------------------------------------ configuration
def provider_list():
    return [{"id": k, "name": v["name"], "model": v["model"], "help": v["help"],
             "help_url": v["help_url"], "needs_base": k == "custom"} for k, v in PROVIDERS.items()]


def configure(provider, key, model=None, base=None) -> None:
    if provider not in PROVIDERS:
        raise VisionError("Unknown provider.")
    key = (key or "").strip()
    if len(key) < 16:
        raise VisionError("That key looks too short. Copy the whole key from the provider's page.")
    p = PROVIDERS[provider]
    base = (base or p["base"]).strip()
    if not (base.startswith("https://") or re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?(/|$)", base)):
        raise VisionError("Enter the provider's base URL. It must start with https:// (http:// is only allowed for localhost).")
    model = (model or p["model"]).strip()
    if not model:
        raise VisionError("Enter the name of a model that accepts images.")
    _cfg.clear()
    _cfg.update(provider=provider, key=key, base=base, model=model,
                fallbacks=p["fallbacks"] if model == p["model"] else [])


def clear() -> None:
    _cfg.clear()


def _from_env():
    for prov, var, mvar in (("gemini", "GEMINI_API_KEY", "GEMINI_MODEL"),
                            ("openrouter", "OPENROUTER_API_KEY", "OPENROUTER_MODEL")):
        if os.environ.get(var):
            p = PROVIDERS[prov]
            return dict(provider=prov, key=os.environ[var], base=p["base"],
                        model=os.environ.get(mvar) or p["model"], fallbacks=p["fallbacks"])
    if os.environ.get("VISION_API_KEY") and os.environ.get("VISION_BASE_URL") and os.environ.get("VISION_MODEL"):
        return dict(provider="custom", key=os.environ["VISION_API_KEY"],
                    base=os.environ["VISION_BASE_URL"], model=os.environ["VISION_MODEL"], fallbacks=[])
    return None


def _active():
    return dict(_cfg) if _cfg.get("key") else _from_env()


def available() -> bool:
    return _active() is not None


def active_provider():
    a = _active()
    return {"id": a["provider"], "model": a["model"]} if a else None


# ------------------------------------------------------------------ transport
def _friendly(code: int, body: str, model: str) -> str:
    if code in (401, 403):
        return "The provider rejected the key. Check the key and that the right provider is selected."
    if code == 404:
        return f"The provider does not know the model '{model}'. Change the model name."
    if code == 429:
        return "Provider quota/rate limit reached (429). Check per-minute AND daily limits; daily quota may reset later."
    if code == 400 and "unexpected model name format" in body:
        return f"Invalid model ID '{model}'. Check the provider and model selection."
    snippet = re.sub(r"\s+", " ", body)[:300]
    return f"The provider returned an error ({code}): {snippet}"


def _post(cfg, model, payload_content, max_tokens, structured=False):
    payload = {
        "model": model, "max_tokens": max_tokens, "temperature": 0,
        "messages": [{"role": "user", "content": payload_content}],
    }
    if cfg["provider"] == "gemini":
        # Use Google's native generateContent API, not its OpenAI-compatibility shim.
        # The latter can reject otherwise-valid IDs with "unexpected model name format".
        native_model = model.removeprefix("models/")
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", native_model):
            raise VisionError("Invalid Gemini model ID. Use e.g. gemini-2.5-flash (not a display name or OpenRouter ID).")
        image_part = next((p for p in payload_content if p.get("type") == "image_url"), None)
        prompt_part = next((p for p in payload_content if p.get("type") == "text"), None)
        if not image_part or not prompt_part:
            raise VisionError("The image or prompt is missing.")
        image_url = image_part["image_url"]["url"]
        prefix = "data:image/png;base64,"
        if not image_url.startswith(prefix):
            raise VisionError("Expected a PNG diagram.")
        native_payload = {
            "contents": [{"role": "user", "parts": [
                {"text": prompt_part["text"]},
                {"inline_data": {"mime_type": "image/png", "data": image_url[len(prefix):]}},
            ]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
        }
        if structured:
            native_payload["generationConfig"].update({
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "text": {"type": "STRING"},
                            "x": {"type": "NUMBER"}, "y": {"type": "NUMBER"},
                            "tx": {"type": "NUMBER"}, "ty": {"type": "NUMBER"},
                        },
                        "required": ["text", "x", "y", "tx", "ty"],
                    },
                },
            })
        endpoint = cfg["base"].rstrip("/") + "/models/" + native_model + ":generateContent"
        req = urllib.request.Request(endpoint, data=json.dumps(native_payload).encode(),
            headers={"x-goog-api-key": cfg["key"], "Content-Type": "application/json"})
    else:
        if structured:
            # Other OpenAI-compatible providers vary in JSON-schema support;
            # request JSON where possible through the instruction, and parse defensively.
            pass
        req = urllib.request.Request(
            cfg["base"].rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"},
        )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.load(r)
            if cfg["provider"] == "gemini":
                try:
                    parts = result["candidates"][0]["content"]["parts"]
                    answer = "".join(p.get("text", "") for p in parts)
                    return {"choices": [{"message": {"content": answer}}]}
                except (KeyError, IndexError, TypeError):
                    raise VisionError("Gemini returned no readable text; check safety filters or model output.")
            return result
    except urllib.error.HTTPError as e:
        raise _HTTP(e.code, e.read().decode(errors="replace"), model)
    except urllib.error.URLError as e:
        raise VisionError(f"Could not reach the provider: {e.reason}")
    except (TimeoutError, OSError):
        raise VisionError("The provider took too long to answer. Try again.")


class _HTTP(VisionError):
    def __init__(self, code, body, model):
        super().__init__(_friendly(code, body, model))
        self.code = code


def _text_of(data) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise VisionError("The provider sent an unexpected reply.")
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    content = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S).strip()
    if not content:
        raise VisionError("The model returned nothing. Try again, or choose a different model.")
    return content


def _ask(png: bytes, prompt: str, model, max_tokens: int, structured=False) -> str:
    """One vision call. Kept separate so tests can replace it."""
    cfg = _active()
    if cfg is None:
        raise VisionError("Add a free API key to name parts automatically.")
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]
    candidates = [model or cfg["model"]] + (cfg["fallbacks"] if not model else [])
    last: VisionError | None = None
    for m in candidates:
        try:
            return _text_of(_post(cfg, m, content, max_tokens, structured=structured))
        except _HTTP as e:
            last = e
            if e.code != 404:                        # only an unknown model is worth a fallback
                raise
    raise last or VisionError("No model answered.")


# ------------------------------------------------------------------ jobs
def _png(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise VisionError("Could not encode the image.")
    return buf.tobytes()


def _clean_text(s: str) -> str:
    lines = [l for l in s.strip().splitlines() if l.strip()]
    s = lines[0] if lines else ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()   # e-acute -> e; theta is dropped
    s = re.sub(r"^\s*(label|answer|part)\s*:\s*", "", s, flags=re.I)
    s = re.sub(r"^[\"'`*\s]+|[\"'`*.\s]+$", "", s)
    return s[:40]


def _parse_parts(text: str):
    """Accept an array, an object containing parts/labels/items, or a fenced reply."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I).strip()
    candidates = [cleaned]
    # Handles introductory prose around a JSON value, without using greedy regex.
    decoder = json.JSONDecoder()
    for i, char in enumerate(cleaned):
        if char in "[{":
            try:
                val, _ = decoder.raw_decode(cleaned[i:])
                candidates.append(val)
                break
            except json.JSONDecodeError:
                continue
    for candidate in candidates:
        try:
            data = json.loads(candidate) if isinstance(candidate, str) else candidate
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            for k in ("parts", "labels", "items", "components", "annotations"):
                if isinstance(data.get(k), list):
                    data = data[k]
                    break
        if isinstance(data, list):
            return data
    # Log only a bounded portion of *model output*, never credentials or images.
    log.warning("Vision label response could not be parsed: %.500r", text[:500])
    raise VisionError("The AI reply contained no usable JSON list of parts. Check the server terminal for a short response preview and retry.")


def suggest_labels(img, max_labels: int = 8):
    text = _ask(_png(img), SUGGEST_PROMPT.format(n=max_labels), None, 3000, structured=True)
    items = _parse_parts(text)[:max_labels]
    clamp = lambda v: min(max(v, 0.0), 1.0)
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            label = _clean_text(str(item.get("text", item.get("name", ""))))
            if not label:
                continue
            x, y = float(item["x"]), float(item["y"])
            tx, ty = float(item.get("tx", x)), float(item.get("ty", y))
            if not all(map(math.isfinite, (x, y, tx, ty))):
                continue
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        out.append({"text": label, "x": clamp(x), "y": clamp(y), "ax": clamp(tx), "ay": clamp(ty)})
    if not out:
        log.warning("Vision returned %d parts but none had valid text and numeric x/y coordinates", len(items))
        raise VisionError("The AI response had no valid labels with x/y coordinates. Try another model or image.")
    return out


def identify(img, x: float, y: float) -> str:
    h, w = img.shape[:2]
    marked = img.copy()
    px, py = int(min(max(x, 0), 1) * (w - 1)), int(min(max(y, 0), 1) * (h - 1))
    cv2.circle(marked, (px, py), 18, (0, 0, 255), 3, cv2.LINE_AA)
    cv2.circle(marked, (px, py), 2, (0, 0, 255), -1, cv2.LINE_AA)
    label = _clean_text(_ask(_png(marked), IDENTIFY_PROMPT, None, 600))
    if not label:
        raise VisionError("The model returned no label. Try again.")
    return label
