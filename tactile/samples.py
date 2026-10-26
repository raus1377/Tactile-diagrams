"""Built-in physics diagrams for the demo: optics + classical mechanics.

Each is drawn like a textbook figure, including small printed letters. Those
letters are deliberately tiny: the pipeline strips them and the Braille key
replaces them, which is the whole point of the tool.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

W, H = 1000, 700
K = (0, 0, 0)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _canvas():
    return np.full((H, W, 3), 255, np.uint8)


def _line(img, p1, p2, t=3):
    cv2.line(img, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), K, t, cv2.LINE_AA)


def _arrow(img, p1, p2, t=3, head=24):
    length = math.dist(p1, p2)
    cv2.arrowedLine(img, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), K, t,
                    cv2.LINE_AA, tipLength=head / length)


def _dashed(img, p1, p2, t=3, dash=16, gap=12):
    length = math.dist(p1, p2)
    ux, uy = (p2[0] - p1[0]) / length, (p2[1] - p1[1]) / length
    d = 0.0
    while d < length:
        e = min(d + dash, length)
        _line(img, (p1[0] + ux * d, p1[1] + uy * d), (p1[0] + ux * e, p1[1] + uy * e), t)
        d += dash + gap


def _lab(text, mx, my, ax=None, ay=None):
    """Label with marker at (mx, my) px and optional leader target (ax, ay) px."""
    d = {"text": text, "x": mx / W, "y": my / H}
    if ax is not None:
        d["ax"], d["ay"] = ax / W, ay / H
    return d


def _text(img, s, org, scale=0.8):
    cv2.putText(img, s, (int(org[0]), int(org[1])), FONT, scale, K, 2, cv2.LINE_AA)


# --- 1. converging lens ----------------------------------------------------------
def lens():
    img = _canvas()
    ax = 350
    f = 150
    lx = 500
    _line(img, (40, ax), (960, ax))                                   # principal axis
    cv2.ellipse(img, (lx, ax), (26, 175), 0, 0, 360, K, 3, cv2.LINE_AA)   # lens
    for x in (lx - 2 * f, lx - f, lx + f, lx + 2 * f):                # focus ticks
        _line(img, (x, ax - 10), (x, ax + 10))
    obj_x, obj_h = lx - 2 * f, 100
    img_x = lx + 2 * f
    _arrow(img, (obj_x, ax), (obj_x, ax - obj_h))                     # object
    _arrow(img, (img_x, ax), (img_x, ax + obj_h))                     # inverted real image
    tip = (obj_x, ax - obj_h)
    img_tip = (img_x, ax + obj_h)
    _line(img, tip, (lx, ax - obj_h))                                 # ray 1: parallel ...
    _line(img, (lx, ax - obj_h), img_tip)                             # ... then through far focus
    _line(img, tip, img_tip)                                          # ray 2: through centre
    _line(img, tip, (lx, ax + obj_h))                                 # ray 3: via near focus ...
    _line(img, (lx, ax + obj_h), img_tip)                             # ... then parallel
    _text(img, "F", (lx - f - 22, ax + 42))
    _text(img, "F", (lx + f + 8, ax - 28))
    _text(img, "2F", (obj_x - 24, ax + 42))
    _text(img, "2F", (img_x - 24, ax - 28))
    labels = [
        _lab("Object", 140, 300, obj_x, 300),
        _lab("Converging lens", lx, 120, lx, ax - 175),
        _lab("Principal axis", 85, 440, 85, ax),
        _lab("Focal point", 705, 285, lx + f, ax),
        _lab("Real inverted image", 875, 420, img_x, 420),
    ]
    return img, "Converging lens ray diagram", labels


# --- 2. block on an incline ------------------------------------------------------
def incline():
    img = _canvas()
    th = math.radians(30)
    d = (math.cos(th), -math.sin(th))            # up the slope
    n = (-math.sin(th), -math.cos(th))           # outward normal
    p0, p1 = (100, 600), (850, 600)
    p2 = (850, 600 - 750 * math.tan(th))
    cv2.polylines(img, [np.array([p0, p1, p2], np.int32)], True, K, 3, cv2.LINE_AA)
    c0 = (p0[0] + 400 * d[0], p0[1] + 400 * d[1])
    half = 50
    corners = [
        (c0[0] - half * d[0], c0[1] - half * d[1]),
        (c0[0] + half * d[0], c0[1] + half * d[1]),
        (c0[0] + half * d[0] + 100 * n[0], c0[1] + half * d[1] + 100 * n[1]),
        (c0[0] - half * d[0] + 100 * n[0], c0[1] - half * d[1] + 100 * n[1]),
    ]
    cv2.polylines(img, [np.array(corners, np.int32)], True, K, 3, cv2.LINE_AA)
    cen = (c0[0] + 50 * n[0], c0[1] + 50 * n[1])
    w_tip = (cen[0], cen[1] + 130)
    n_tip = (cen[0] + 100 * n[0], cen[1] + 100 * n[1])
    f_tip = (cen[0] + 110 * d[0], cen[1] + 110 * d[1])
    _arrow(img, cen, w_tip)                                           # weight
    _arrow(img, cen, n_tip)                                           # normal force
    _arrow(img, cen, f_tip)                                           # friction
    cv2.ellipse(img, p0, (180, 180), 0, -30, 0, K, 3, cv2.LINE_AA)    # angle arc
    _text(img, "mg", (w_tip[0] + 14, w_tip[1] + 10))
    _text(img, "N", (n_tip[0] - 40, n_tip[1] - 6))
    _text(img, "f", (f_tip[0] + 14, f_tip[1] - 8))
    _text(img, "30", (p0[0] + 235, p0[1] - 22), 0.7)
    on_slope = (600, 600 - 500 * math.tan(th))
    arc_mid = (p0[0] + 180 * math.cos(math.radians(15)), p0[1] - 180 * math.sin(math.radians(15)))
    labels = [
        _lab("Inclined plane", 650, 440, on_slope[0], on_slope[1]),
        _lab("Block", 290, 395, corners[3][0] * 0.5 + corners[0][0] * 0.5,
             corners[3][1] * 0.5 + corners[0][1] * 0.5),
        _lab("Weight", 490, 545, w_tip[0], w_tip[1] - 8),
        _lab("Normal force", 290, 215, n_tip[0], n_tip[1]),
        _lab("Friction", 580, 225, f_tip[0], f_tip[1]),
        _lab("Angle of incline", 350, 556, arc_mid[0], arc_mid[1]),
    ]
    return img, "Block on an inclined plane: forces", labels


# --- 3. projectile ---------------------------------------------------------------
def projectile():
    img = _canvas()
    ground, amp = 520, 330
    _line(img, (40, ground), (960, ground))
    curve = lambda x: ground - amp * (1 - ((x - 500) / 400) ** 2)
    pts = [(x, curve(x)) for x in range(100, 901, 8)]
    cv2.polylines(img, [np.array(pts, np.int32)], False, K, 3, cv2.LINE_AA)
    start = (100, ground)
    slope = 2 * amp / 400                                             # dy/dx magnitude at launch
    norm = math.hypot(1, slope)
    ux, uy = 1 / norm, -slope / norm
    tip = (start[0] + 170 * ux, start[1] + 170 * uy)
    _arrow(img, start, tip)                                           # launch velocity
    _dashed(img, start, (tip[0], start[1]))                           # horizontal component
    _dashed(img, (tip[0], start[1]), tip)                             # vertical component
    cv2.ellipse(img, start, (95, 95), 0, -58, 0, K, 3, cv2.LINE_AA)
    ry = ground + 55
    _arrow(img, (100, ry), (900, ry))                                 # range
    _arrow(img, (900, ry), (100, ry))
    _line(img, (100, ry - 15), (100, ry + 15))
    _line(img, (900, ry - 15), (900, ry + 15))
    _text(img, "v", (tip[0] + 12, tip[1] - 6))
    _text(img, "vx", (start[0] + 40, ground + 38), 0.7)
    _text(img, "R", (490, ry + 70))
    mid = (start[0] + 85 * ux, start[1] + 85 * uy)
    labels = [
        _lab("Launch point", 60, 440, start[0], start[1]),
        _lab("Launch velocity", 250, 450, mid[0], mid[1]),
        _lab("Parabolic path", 320, 330, 330, curve(330)),
        _lab("Highest point", 500, 120, 500, ground - amp),
        _lab("Ground", 935, 430, 935, ground),
        _lab("Horizontal range", 500, 668, 500, ry),
    ]
    return img, "Projectile motion", labels


SAMPLES = {
    "lens": ("Optics: converging lens", lens),
    "incline": ("Mechanics: block on incline", incline),
    "projectile": ("Mechanics: projectile motion", projectile),
}


def catalog():
    out = []
    for sid, (name, fn) in SAMPLES.items():
        _, title, labels = fn()
        out.append({"id": f"sample:{sid}", "name": name, "title": title, "labels": labels})
    return out


def render(sid: str):
    return SAMPLES[sid][1]()[0]
