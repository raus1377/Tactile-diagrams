# Tactile diagrams

Turn a textbook diagram (photo, scan or digital drawing) into a **Braille-labelled
tactile page**: simplified high-contrast line work, Braille key letters on the
diagram, and a full Braille key underneath. Output is an A4 SVG in millimetres,
ready for swell paper, and usable as a starting point for embossing or 3D printing.

## Why this exists

Transcription services charge per page and take weeks, and STEM diagrams are the
hardest material to get in tactile form. The expensive step is turning a
cluttered figure into something fingers can read. This tool automates that step
and keeps a teacher in the loop for the one thing that needs judgement:
where each label goes.

## Run it

```bash
pip install -r requirements.txt
python app.py            # http://127.0.0.1:5000
```

## Naming parts automatically (one free key)

Everything except naming works with no key. To have parts named from the image
(on upload, and when you drag a pointer onto another part) the app needs a
vision model. It uses **free** providers only, picked in the sidebar:

| Provider | Key from | Notes |
|---|---|---|
| Google Gemini (default) | https://aistudio.google.com/apikey | Free tier, no card. On the free tier Google may use what you send to improve its products, so don't upload anything private. |
| OpenRouter | https://openrouter.ai/keys | Use a model whose name ends in `:free` that accepts images. Free models rotate. |
| Other (OpenAI-compatible) | Groq, NVIDIA NIM, ... | Enter base URL + model. `http://localhost` is allowed, so a local Ollama vision model costs nothing and sends nothing off your machine. |

Paste the key in the app. It stays in the running process's memory and is never
written to disk. You can also use environment variables instead:
`GEMINI_API_KEY`, `OPENROUTER_API_KEY`, or `VISION_API_KEY` + `VISION_BASE_URL` + `VISION_MODEL`.

Free-tier model names and limits change often (Google no longer publishes fixed
free limits). If a model stops working, change the **Model** field. A rate-limit
message means: wait a minute.

Try the naming flow with **no key at all**: `python tests/serve_stub.py` serves
the app on http://127.0.0.1:5055 with a fake namer that names a part by the third
of the diagram the pointer lands in. It exists for demos and tests; it is not a
real recogniser.

Tests:

```bash
python tests/test_braille.py            # encoder vs known cells
python tests/test_naming.py             # naming endpoints, stubbed model
python tests/test_vision_transport.py   # real HTTP path vs a local fake OpenAI-style server
python tests/run_samples.py             # runs all samples, writes SVGs to out/
# UI test (drives static/app.js in jsdom against the stub server):
python tests/serve_stub.py &            # terminal 1
cd tests && npm install jsdom && node ui_test.js
```

## How it works

| Stage | File | What it does |
|---|---|---|
| Load | `tactile/outline.py` | Decodes, fixes EXIF rotation, flattens transparency, normalises to 1000 px wide |
| Binarise | `tactile/outline.py` | Adaptive threshold (scans/photos), Otsu (clean art) or Canny (object photos) |
| Clean | `tactile/outline.py` | Drops small components (printed letters, specks) but **keeps dashed lines** that line up with each other |
| Thicken | `tactile/outline.py` | Measures stroke width, dilates to the target line weight in mm |
| Trace | `tactile/outline.py` | Contours to a single filled SVG path (even-odd) |
| Braille | `tactile/braille.py` | Grade-1 encoder: number sign, letter sign, capital indicators, word wrap |
| Page | `tactile/svgbuild.py` | A4 layout, key letters with white knock-outs and optional leader lines, Braille key table; scales the diagram so the page fits A4 |

Printed text in the source is removed on purpose. It is too small to feel, so
each label becomes a one-cell Braille key letter on the diagram, with the full
label in the key table. Standard embossed-Braille geometry is used: 1.5 mm dots,
2.5 mm dot pitch, 6 mm cell pitch, 10 mm line pitch.

## Printing

- **Swell paper**: print the SVG at 100 % scale on a black-and-white laser or
  photocopier, black only, then run it through a heater. Untick "Print the text
  as well" first, because grey text swells partially.
- **Embossing / 3D printing**: import the SVG into your embosser software or CAD
  tool and extrude the `#diagram`, `#braille` and `#frame` groups. The Braille
  dots are real circles at standard spacing.

## Limits worth knowing

- **Grade-1 Braille only.** Math notation (Nemeth) is not implemented. Symbols
  such as θ, μ or Δ are skipped and reported as a warning, so write them out
  ("theta") in labels for now.
- Have a Braille reader or a teacher of the visually impaired check a page before
  it goes to a student. The encoder is tested against known cells, but not by a
  human Braille reader.
- Very dense diagrams do not become readable by thresholding alone; the tool warns
  when ink density is high and when lines would be under about 1 mm.
- Naming has been tested against a stubbed model and a local fake OpenAI-style
  server, not against live Gemini/OpenRouter. Small free models place markers
  roughly and sometimes name parts wrongly: check each label, and drag markers
  (or use the arrow keys) before exporting.

## Layout

```
app.py              Flask app and JSON API
tactile/            pipeline (outline, braille, svgbuild, samples, autolabel = free vision providers)
static/             single-page UI (index.html, style.css, app.js)
tests/              encoder, naming, transport and UI tests; stub server; sample runner
examples/           pre-rendered output for the three sample diagrams
```

## Troubleshooting API errors

The Gemini provider now uses the **native** Google `v1beta/models/{model}:generateContent` API instead of the OpenAI-compatible endpoint. Use a real API model ID such as `gemini-2.5-flash` (not a display name like `Gemini 2.5 Flash`). The default can be changed in the Model field. A configured key is **not validated** until the first actual naming request. Open the browser Network tab and inspect `/api/autolabel` if labels do not appear. `400` usually means a malformed model ID/request; `429` means a quota or rate-limit issue; `502` is the local app relaying a provider failure. The outline-to-SVG converter runs locally without any API key.

**Security:** API credentials are held in one global process variable, so do not expose this demo server to other users or publish it to the Internet with your key. Use a private local machine while testing.

### Vision labeling fixes (October 2026)

Gemini automatic label suggestions now request an explicit JSON array using
`responseMimeType: application/json` and a schema. Other compatible providers
can return a JSON array or a JSON object containing `parts`, `labels`,
`items`, `components`, or `annotations`. Invalid coordinates are ignored.

If the model returns text without usable JSON, the terminal logs a short
preview of its reply (never your key). The page shows an actionable message.
To see the log, keep the terminal running `python app.py` visible.

The project still generates diagram outlines locally with OpenCV. The vision
API suggests labels, not a complete semantic redraw. Braille and print output
require human review before educational/tactile use.
