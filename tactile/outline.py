"""Image -> tactile-friendly line work.

Pipeline: load -> binarise (3 modes) -> drop specks (printed text, noise) ->
thicken to a target line weight in mm -> trace to filled SVG paths.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps

WORKING_WIDTH = 1000          # every image is normalised to this width (px)


@dataclass
class Outline:
    path_d: str
    nodes: int
    stroke_px: float          # estimated final stroke width, pixels
    density: float            # fraction of the diagram covered by ink


def load_image(data: bytes) -> np.ndarray:
    """Decode bytes to a BGR array at WORKING_WIDTH, transparency flattened to white."""
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg
    arr = np.array(im.convert("RGB"))[:, :, ::-1].copy()
    return normalise(arr)


def normalise(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    if w == WORKING_WIDTH:
        return img
    interp = cv2.INTER_AREA if w > WORKING_WIDTH else cv2.INTER_CUBIC
    return cv2.resize(img, (WORKING_WIDTH, max(1, round(h * WORKING_WIDTH / w))), interpolation=interp)


def extract_mask(img: np.ndarray, mode: str, sensitivity: int, detail: int, erase=None) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if mode == "solid":                                  # clean digital art
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    elif mode == "edges":                                # photos of objects
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        low = max(10, 110 - 2 * sensitivity)
        mask = cv2.Canny(blur, low, low * 2.5)
    else:                                                # "auto": scans / phone photos of pages
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        c = max(2, 42 - sensitivity)
        mask = cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, c
        )

    h, w = mask.shape
    for x0, y0, x1, y1 in erase or []:                    # user-drawn rectangles, as 0..1 fractions
        mask[int(y0 * h):int(math.ceil(y1 * h)), int(x0 * w):int(math.ceil(x1 * w))] = 0
    return drop_small_marks(mask, detail)


def _angle_gap(a: float, b: float) -> float:
    d = abs(a - b) % 180
    return min(d, 180 - d)


def drop_small_marks(mask: np.ndarray, detail: int) -> np.ndarray:
    """Remove printed letters, specks and noise; keep dashed lines.

    A connected component is "small" when its bounding-box diagonal is under
    detail*1.6 px. Small components are dropped unless they are short straight
    dashes that line up with another dash (construction lines, vector
    components, dashed axes).
    """
    if detail <= 0 or not mask.any():
        return mask
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_diag = detail * 1.6
    keep = np.zeros(n, dtype=bool)
    dashes = []                                   # (idx, cx, cy, length, angle)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if math.hypot(w, h) >= min_diag:
            keep[i] = area >= 12
        elif area >= 8 and len(dashes) < 400:
            ys, xs = np.nonzero(lab[y:y + h, x:x + w] == i)
            pts = np.column_stack((xs, ys)).astype(np.float64)
            c = pts.mean(axis=0)
            q = pts - c
            _, vecs = np.linalg.eigh(q.T @ q / len(q) + 1e-9 * np.eye(2))
            major, minor = vecs[:, 1], vecs[:, 0]
            pl, pw = q @ major, q @ minor
            length = pl.max() - pl.min() + 1
            width = pw.max() - pw.min() + 1
            if length >= 6 and length / width >= 2.8:
                theta = math.degrees(math.atan2(major[1], major[0])) % 180
                dashes.append((i, x + c[0], y + c[1], length, theta))
    for a in range(len(dashes)):
        ia, ax, ay, la, ta = dashes[a]
        for b in range(a + 1, len(dashes)):
            ib, bx, by, lb, tb = dashes[b]
            dx, dy = bx - ax, by - ay
            dist = math.hypot(dx, dy)
            if dist > 2.5 * max(la, lb) + 10:
                continue
            phi = math.degrees(math.atan2(dy, dx)) % 180
            if (_angle_gap(phi, ta) < 25 and _angle_gap(phi, tb) < 25
                    and _angle_gap(ta, tb) < 25):
                keep[ia] = keep[ib] = True
    return (keep[lab] * 255).astype(np.uint8)


def _stroke_estimate(mask: np.ndarray) -> float:
    if not mask.any():
        return 0.0
    dt = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    return float(2 * np.percentile(dt[mask > 0], 90))


def thicken(mask: np.ndarray, target_px: float) -> np.ndarray:
    est = _stroke_estimate(mask)
    add = target_px - est
    if add >= 1:
        k = int(round(add)) + 1
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def mask_to_path(mask: np.ndarray, epsilon: float = 0.8):
    contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    parts, nodes = [], 0
    for c in contours:
        if len(c) < 3:
            continue
        approx = cv2.approxPolyDP(c, epsilon, True)
        if len(approx) < 3:
            continue
        pts = approx[:, 0, :]
        parts.append("M" + "L".join(f"{x} {y}" for x, y in pts) + "Z")
        nodes += len(pts)
    return "".join(parts), nodes


def make_outline(img, mode, sensitivity, detail, target_line_px, erase=None) -> Outline:
    mask = extract_mask(img, mode, sensitivity, detail, erase)
    # findContours traces pixel centres, which shaves ~1px off every stroke
    mask = thicken(mask, target_line_px + 1)
    path_d, nodes = mask_to_path(mask)
    return Outline(
        path_d=path_d,
        nodes=nodes,
        stroke_px=_stroke_estimate(mask),
        density=float((mask > 0).mean()),
    )
