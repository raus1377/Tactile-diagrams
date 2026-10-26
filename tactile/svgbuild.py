"""Compose the printable tactile page as an SVG in millimetres (A4 width).

Layout, top to bottom: ink + Braille title, framed diagram with Braille key
letters (optionally with leader lines), then a key table (Braille key letter +
full Braille label). Everything that should swell/emboss is pure black; the
optional ink text lives in group #ink (grey) and can be switched off.

plan_scale() decides the diagram size so the whole page fits on A4 when it can;
compose() then draws the page at that scale.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from .braille import (CELL_H, CELL_PITCH, CELL_W, LINE_PITCH, layout_text,
                      render_cells, to_unicode)

PAGE_W = 210.0
A4_H = 297.0
MARGIN = 10.0
CONTENT_W = PAGE_W - 2 * MARGIN                       # 190 mm
MAX_DIAGRAM_H = 170.0
MIN_DIAGRAM_H = 80.0
MAX_CELLS = int((CONTENT_W + (CELL_PITCH - CELL_W)) // CELL_PITCH)    # 32
INK = "#6b6b6b"
MAX_LABELS = 26
PAD = 2.5                                              # white margin around a key letter
INK_ROW = 4.5
INK_HEAD = 5.5
LEADER_W = 0.9


def key_letter(i: int) -> str:
    return chr(ord("a") + i)


def _clamp01(v) -> float:
    return min(max(float(v), 0.0), 1.0)


def _clean_labels(labels):
    out = []
    for lab in labels or []:
        text = str(lab.get("text", "")).strip()
        if not text:
            continue
        if len(out) >= MAX_LABELS:
            break
        d = {"key": key_letter(len(out)), "text": text,
             "x": _clamp01(lab.get("x", 0.5)), "y": _clamp01(lab.get("y", 0.5))}
        if lab.get("ax") is not None and lab.get("ay") is not None:
            d["ax"], d["ay"] = _clamp01(lab["ax"]), _clamp01(lab["ay"])
        out.append(d)
    return out


def _leader(x1, y1, x2, y2) -> str:
    """Line from the key letter to the part, ending in a solid arrowhead on the part."""
    dx, dy = x2 - x1, y2 - y1
    n = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / n, dy / n
    head_len, head_w = 3.6, 2.8
    bx, by = x2 - ux * head_len, y2 - uy * head_len            # base centre of the arrowhead
    px, py = -uy * head_w / 2, ux * head_w / 2
    return (f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{bx:.2f}" y2="{by:.2f}" stroke="#000" '
            f'stroke-width="{LEADER_W}" stroke-linecap="round"/>'
            f'<polygon points="{x2:.2f},{y2:.2f} {bx + px:.2f},{by + py:.2f} {bx - px:.2f},{by - py:.2f}" fill="#000"/>')


def _prepare(labels, title, ink):
    unsupported: set[str] = set()
    placed = _clean_labels(labels)
    title = (title or "").strip()
    title_lines = []
    if title:
        title_lines, bad = layout_text(title, MAX_CELLS)
        unsupported.update(bad)
    rows = []
    for lab in placed:
        lines, bad = layout_text(lab["text"], MAX_CELLS - 2)
        unsupported.update(bad)
        rows.append(lines)
    head_lines, _ = layout_text("key", MAX_CELLS)

    title_h = 0.0
    if title_lines:
        title_h = (INK_HEAD if ink else 0) + len(title_lines) * LINE_PITCH + 3
    key_h = 0.0
    if placed:
        key_h = 8 + (INK_HEAD if ink else 0) + len(head_lines) * LINE_PITCH + 2
        for lines in rows:
            key_h += (INK_ROW if ink else 0) + max(len(lines), 1) * LINE_PITCH + 2
    return {
        "placed": placed, "title": title, "title_lines": title_lines, "rows": rows,
        "head_lines": head_lines, "title_h": title_h, "key_h": key_h,
        "unsupported": unsupported,
    }


def _fixed_height(p) -> float:
    return 2 * MARGIN + p["title_h"] + (p["key_h"] - 2 if p["placed"] else 0)


def plan_scale(w_px: int, h_px: int, labels, title: str = "", ink: bool = True) -> float:
    """mm per pixel such that the page fits A4 when possible."""
    p = _prepare(labels, title, ink)
    max_h = min(MAX_DIAGRAM_H, A4_H - _fixed_height(p))
    max_h = max(max_h, MIN_DIAGRAM_H)
    return min(CONTENT_W / w_px, max_h / h_px)


def compose(path_d, w_px, h_px, scale, labels, title="", ink=True, border=True):
    p = _prepare(labels, title, ink)
    placed = p["placed"]
    dw, dh = w_px * scale, h_px * scale
    braille, ink_parts, leaders, knock, label_dots = [], [], [], [], []

    # -- title ---------------------------------------------------------------------
    y = MARGIN
    if p["title_lines"]:
        if ink:
            ink_parts.append(
                f'<text x="{MARGIN}" y="{y + 3.4:.1f}" font-size="3.6">{escape(p["title"])}</text>')
            y += INK_HEAD
        for line in p["title_lines"]:
            braille.append(render_cells(line, MARGIN, y))
            y += LINE_PITCH
        y += 3

    # -- diagram frame -------------------------------------------------------------
    diag_y = y
    x0 = MARGIN + (CONTENT_W - dw) / 2
    frame = ""
    if border:
        frame = (f'<rect x="{x0:.2f}" y="{diag_y:.2f}" width="{dw:.2f}" height="{dh:.2f}" '
                 f'fill="none" stroke="#000" stroke-width="1"/>')

    # -- key letters on the diagram -------------------------------------------------
    top_extra = 4.0 if ink else 0.0
    out_labels = []
    for lab in placed:
        cx = min(max(x0 + lab["x"] * dw, x0 + CELL_W / 2 + PAD + 1), x0 + dw - CELL_W / 2 - PAD - 1)
        cy = min(max(diag_y + lab["y"] * dh, diag_y + CELL_H / 2 + PAD + top_extra + 1),
                 diag_y + dh - CELL_H / 2 - PAD - 1)
        if "ax" in lab:
            ax, ay = x0 + lab["ax"] * dw, diag_y + lab["ay"] * dh
            leaders.append(_leader(cx, cy, ax, ay))
        knock.append(
            f'<rect x="{cx - CELL_W / 2 - PAD:.2f}" y="{cy - CELL_H / 2 - PAD - top_extra:.2f}" '
            f'width="{CELL_W + 2 * PAD:.2f}" height="{CELL_H + 2 * PAD + top_extra:.2f}" fill="#fff"/>')
        key_cells, _ = layout_text(lab["key"], 1)
        label_dots.append(render_cells(key_cells[0], cx - CELL_W / 2, cy - CELL_H / 2))
        if ink:
            ink_parts.append(
                f'<text x="{cx:.2f}" y="{cy - CELL_H / 2 - 1.2:.2f}" font-size="3.4" '
                f'text-anchor="middle">{lab["key"]}</text>')
        out_labels.append(dict(lab))

    y = diag_y + dh

    # -- key table -------------------------------------------------------------------
    key_braille = []
    if placed:
        y += 8
        if ink:
            ink_parts.append(f'<text x="{MARGIN}" y="{y + 3.4:.1f}" font-size="3.6">Key</text>')
            y += INK_HEAD
        for line in p["head_lines"]:
            braille.append(render_cells(line, MARGIN, y))
            y += LINE_PITCH
        y += 2
        for lab, lines in zip(placed, p["rows"]):
            if ink:
                ink_parts.append(
                    f'<text x="{MARGIN}" y="{y + 3.0:.1f}" font-size="3.2">'
                    f'{lab["key"]} = {escape(lab["text"])}</text>')
                y += INK_ROW
            key_cells, _ = layout_text(lab["key"], 1)
            braille.append(render_cells(key_cells[0], MARGIN, y))
            for line in lines:
                braille.append(render_cells(line, MARGIN + 2 * CELL_PITCH, y))
                y += LINE_PITCH
            if not lines:
                y += LINE_PITCH
            y += 2
            key_braille.append({
                "key": lab["key"], "text": lab["text"],
                "unicode": " ".join(to_unicode(l) for l in lines),
            })
        page_h = y + MARGIN - 2
    else:
        page_h = y + MARGIN

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_W}mm" height="{page_h:.1f}mm" '
        f'viewBox="0 0 {PAGE_W} {page_h:.1f}">'
        f'<rect width="{PAGE_W}" height="{page_h:.1f}" fill="#fff"/>'
        f'<g id="diagram" transform="translate({x0:.2f} {diag_y:.2f}) scale({scale:.5f})">'
        f'<path d="{path_d}" fill="#000" fill-rule="evenodd"/></g>'
        f'<g id="frame">{frame}</g>'
        f'<g id="leaders">{"".join(leaders)}</g>'
        f'<g id="knockouts">{"".join(knock)}</g>'
        f'<g id="braille" fill="#000">{"".join(label_dots)}{"".join(braille)}</g>'
        + (f'<g id="ink" fill="{INK}" font-family="Helvetica, Arial, sans-serif">'
           f'{"".join(ink_parts)}</g>' if ink else "")
        + "</svg>"
    )
    return {
        "svg": svg,
        "page_mm": [PAGE_W, round(page_h, 1)],
        "diagram_mm": [round(x0, 2), round(diag_y, 2), round(dw, 2), round(dh, 2)],
        "scale_mm_per_px": scale,
        "labels": out_labels,
        "key_braille": key_braille,
        "title_braille": " ".join(to_unicode(l) for l in p["title_lines"]),
        "overflow": page_h > A4_H + 0.5,
        "unsupported": sorted(p["unsupported"]),
    }
