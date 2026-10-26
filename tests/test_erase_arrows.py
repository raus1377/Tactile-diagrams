"""Erase rectangles and arrowheads."""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as webapp  # noqa: E402
from tactile import outline, pipeline, samples  # noqa: E402

# --- API-side validation of erase rectangles ---------------------------------------------
f = webapp._erase_rects
assert f(None) == [] and f([]) == []
assert f([[0.5, 0.5, 0.2, 0.1]]) == [(0.2, 0.1, 0.5, 0.5)], "corners are normalised"
assert f([[-1, -1, 2, 2]]) == [(0.0, 0.0, 1.0, 1.0)], "values are clamped to 0..1"
assert f([[0.1, 0.1, 0.1, 0.5]]) == [], "zero-width boxes are dropped"
assert f([[0.1, 0.2], "x", None]) == [], "malformed entries are ignored"
assert len(f([[0, 0, 1, 1]] * 80)) == 50, "at most 50 boxes"

# --- erasing removes ink inside the box only ----------------------------------------------
img = samples.render("lens")
box = (0.45, 0.2, 0.55, 0.85)
full = outline.extract_mask(img, "solid", 30, 0)
cut = outline.extract_mask(img, "solid", 30, 0, [box])
h, w = full.shape
inside = (slice(int(box[1] * h), int(box[3] * h)), slice(int(box[0] * w), int(box[2] * w)))
assert (full[inside] > 0).any() and not (cut[inside] > 0).any(), "ink inside the box must be gone"
outside = full.copy(); outside[inside] = 0
chk = cut.copy(); chk[inside] = 0
assert (outside == chk).all(), "ink outside the box must be untouched"

# --- arrowheads: a filled triangle whose tip is exactly on the target point ---------------------
labels = [{"text": "Lens", "x": 0.5, "y": 0.1, "ax": 0.5, "ay": 0.3}, {"text": "Plain", "x": 0.2, "y": 0.8}]
res = pipeline.run(img, mode="solid", labels=labels)
svg = res["svg"]
polys = re.findall(r'<polygon points="([^"]+)"', svg)
assert len(polys) == 1, "one arrowhead for the one label that has an arrow"
tip = [float(v) for v in polys[0].split()[0].split(",")]
x0, y0, dw, dh = res["diagram_mm"]
assert abs(tip[0] - (x0 + 0.5 * dw)) < 0.02 and abs(tip[1] - (y0 + 0.3 * dh)) < 0.02, "arrow tip sits on the target"
assert 'r="1.1"' not in svg, "old dot terminator is gone"
print("erase + arrowheads OK")
