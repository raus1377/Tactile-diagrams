"""One call from image to finished tactile SVG + diagnostics."""
from __future__ import annotations

from . import outline, svgbuild


def run(img, *, mode="auto", sensitivity=30, detail=25, line_mm=1.4,
        title="", labels=None, ink=True, border=True, erase=None):
    h, w = img.shape[:2]
    labels = labels or []
    scale = svgbuild.plan_scale(w, h, labels, title, ink)
    res = outline.make_outline(img, mode, int(sensitivity), int(detail), float(line_mm) / scale, erase)
    out = svgbuild.compose(res.path_d, w, h, scale, labels, title, ink, border)

    stroke_mm = res.stroke_px * scale
    warnings = []
    if not res.path_d:
        warnings.append("No lines found. Raise sensitivity, lower the small-mark filter, or try another mode.")
    if res.path_d and stroke_mm < 0.9:
        warnings.append(f"Lines are about {stroke_mm:.1f} mm wide; below ~1 mm they are hard to feel.")
    if res.density > 0.15:
        warnings.append("Very busy diagram: fingers cannot separate lines this dense. Raise the small-mark filter.")
    if out["overflow"]:
        warnings.append("The key is too long for one A4 page. Shorten labels or use fewer of them.")
    if out["unsupported"]:
        warnings.append("Characters not supported in Grade-1 Braille were skipped: " + " ".join(out["unsupported"]))
    out["warnings"] = warnings
    out["stats"] = {
        "nodes": res.nodes,
        "stroke_mm": round(stroke_mm, 2),
        "ink_density_pct": round(res.density * 100, 1),
        "svg_kb": round(len(out["svg"]) / 1024, 1),
    }
    return out
