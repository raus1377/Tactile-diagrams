"""Grade-1 (uncontracted) English Braille encoder plus physical dot geometry.

Cells are tuples of dot numbers laid out like this:

    1 4
    2 5
    3 6

Number sign (3456), letter sign (56) and capital indicators (6 / 66) follow
UEB conventions. Math notation (Nemeth) is NOT covered: unsupported characters
are dropped and reported so the caller can warn the user.
"""
from __future__ import annotations

# --- physical geometry, millimetres (standard embossed-Braille spacing) -------
DOT_DIAMETER = 1.5
DOT_PITCH = 2.5          # centre-to-centre inside one cell
CELL_PITCH = 6.0         # cell to next cell
LINE_PITCH = 10.0        # line to next line
CELL_W = DOT_PITCH + DOT_DIAMETER           # 4.0
CELL_H = 2 * DOT_PITCH + DOT_DIAMETER       # 6.5

NUMBER_SIGN = (3, 4, 5, 6)
LETTER_SIGN = (5, 6)
CAPITAL_SIGN = (6,)

_LETTERS = {
    "a": (1,), "b": (1, 2), "c": (1, 4), "d": (1, 4, 5), "e": (1, 5),
    "f": (1, 2, 4), "g": (1, 2, 4, 5), "h": (1, 2, 5), "i": (2, 4), "j": (2, 4, 5),
    "k": (1, 3), "l": (1, 2, 3), "m": (1, 3, 4), "n": (1, 3, 4, 5), "o": (1, 3, 5),
    "p": (1, 2, 3, 4), "q": (1, 2, 3, 4, 5), "r": (1, 2, 3, 5), "s": (2, 3, 4),
    "t": (2, 3, 4, 5), "u": (1, 3, 6), "v": (1, 2, 3, 6), "w": (2, 4, 5, 6),
    "x": (1, 3, 4, 6), "y": (1, 3, 4, 5, 6), "z": (1, 3, 5, 6),
}
_DIGITS = dict(zip("1234567890", "abcdefghij"))
_PUNCT = {
    ".": (2, 5, 6), ",": (2,), ";": (2, 3), ":": (2, 5), "?": (2, 3, 6),
    "!": (2, 3, 5), "-": (3, 6), "'": (3,), "(": (2, 3, 5, 6), ")": (2, 3, 5, 6),
    "/": (3, 4),
}
_NUMERIC_DECIMAL = (4, 6)


def _is_ascii_letter(ch: str) -> bool:
    return ch.isascii() and ch.isalpha()


def encode_word(word: str):
    """Encode one whitespace-free word. Returns (cells, unsupported_chars)."""
    cells: list[tuple] = []
    bad: list[str] = []
    in_number = False
    i, n = 0, len(word)
    while i < n:
        ch = word[i]
        if ch in _DIGITS:
            if not in_number:
                cells.append(NUMBER_SIGN)
                in_number = True
            cells.append(_LETTERS[_DIGITS[ch]])
            i += 1
        elif in_number and ch in ".," and i + 1 < n and word[i + 1] in _DIGITS:
            cells.append(_NUMERIC_DECIMAL if ch == "." else _PUNCT[ch])
            i += 1
        elif _is_ascii_letter(ch):
            if ch.isupper():
                j = i
                while j < n and _is_ascii_letter(word[j]) and word[j].isupper():
                    j += 1
                run = j - i
                if in_number and ch.lower() in "abcdefghij":
                    cells.append(LETTER_SIGN)
                in_number = False
                if run >= 2 and j == n:          # capitals run to end of word
                    cells += [CAPITAL_SIGN, CAPITAL_SIGN]
                    cells += [_LETTERS[c.lower()] for c in word[i:j]]
                else:                            # each capital gets its own sign
                    for c in word[i:j]:
                        cells.append(CAPITAL_SIGN)
                        cells.append(_LETTERS[c.lower()])
                i = j
            else:
                if in_number and ch in "abcdefghij":
                    cells.append(LETTER_SIGN)
                in_number = False
                cells.append(_LETTERS[ch])
                i += 1
        elif ch in _PUNCT:
            in_number = False
            cells.append(_PUNCT[ch])
            i += 1
        else:
            bad.append(ch)
            i += 1
    return cells, bad


def layout_text(text: str, max_cells: int):
    """Word-wrap text into lines of cells. Returns (lines, unsupported_chars)."""
    lines: list[list[tuple]] = []
    cur: list[tuple] = []
    bad: list[str] = []
    for word in text.split():
        cells, b = encode_word(word)
        bad += b
        if not cells:
            continue
        while len(cells) > max_cells:            # hard-break very long words
            if cur:
                lines.append(cur)
                cur = []
            lines.append(cells[:max_cells])
            cells = cells[max_cells:]
        needed = len(cells) + (1 if cur else 0)
        if len(cur) + needed > max_cells:
            lines.append(cur)
            cur = []
        if cur:
            cur.append(())                       # blank cell between words
        cur += cells
    if cur:
        lines.append(cur)
    return lines, bad


def to_unicode(cells) -> str:
    """Unicode Braille patterns (U+2800..) for a row of cells, for on-screen preview."""
    return "".join(chr(0x2800 + sum(1 << (d - 1) for d in cell)) for cell in cells)


def cells_width(n_cells: int) -> float:
    return 0.0 if n_cells <= 0 else (n_cells - 1) * CELL_PITCH + CELL_W


def render_cells(cells, x: float, y: float) -> str:
    """SVG circles for a row of cells; (x, y) is the top-left of the row's bbox."""
    out = []
    r = DOT_DIAMETER / 2
    for k, cell in enumerate(cells):
        ox = x + r + k * CELL_PITCH
        for d in cell:
            col = 0 if d <= 3 else 1
            row = (d - 1) % 3
            out.append(
                f'<circle cx="{ox + col * DOT_PITCH:.2f}" '
                f'cy="{y + r + row * DOT_PITCH:.2f}" r="{r}"/>'
            )
    return "".join(out)
