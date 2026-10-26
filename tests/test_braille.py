"""Encoder checks against known Grade-1 / UEB cells."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from tactile.braille import layout_text, to_unicode

def enc(text, n=40):
    lines, bad = layout_text(text, n)
    return " ".join(to_unicode(l) for l in lines), bad

cases = {
    "hello": "⠓⠑⠇⠇⠕",
    "Block": "⠠⠃⠇⠕⠉⠅",           # capital sign + b-l-o-c-k
    "mg": "⠍⠛",
    "2F": "⠼⠃⠰⠠⠋",                # number sign, 2, letter sign, capital sign, f
    "30": "⠼⠉⠚",
    "NASA": "⠠⠠⠝⠁⠎⠁",            # capital word indicator
    "a b": "⠁\u2800⠃",       # blank cell between words
    "z.": "⠵⠲",
}
fails = 0
for text, want in cases.items():
    got, _ = enc(text)
    ok = got == want
    fails += not ok
    print("PASS" if ok else "FAIL", repr(text), got, "" if ok else f"(want {want})")

lines, _ = layout_text("Real inverted image of the object", 12)
assert all(len(l) <= 12 for l in lines), "wrap exceeded width"
_, bad = layout_text("v = θ", 20)
assert bad == ["θ"] or "θ" in bad, bad
print("wrap + unsupported-char reporting OK")
sys.exit(1 if fails else 0)
