"""Smoke test: run every sample through the pipeline and write SVGs to out/."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from tactile import pipeline, samples  # noqa: E402

out_dir = ROOT / "out"
out_dir.mkdir(exist_ok=True)
for item in samples.catalog():
    sid = item["id"].split(":", 1)[1]
    img = samples.render(sid)
    cv2.imwrite(str(out_dir / f"{sid}_source.png"), img)
    res = pipeline.run(img, title=item["title"], labels=item["labels"])
    (out_dir / f"{sid}_tactile.svg").write_text(res["svg"])
    print(sid, res["stats"], res["warnings"], f"page={res['page_mm']}")
