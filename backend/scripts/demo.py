"""Generate sample product photos, run the real pipeline on them and save every stage's output.

    python scripts/demo.py [output_dir]

Writes <output_dir>/<case>/{photo,background_removed,mask,outline,drawing}.png plus contact_sheet.png
(photo | mask | final drawing for each case). Defaults to ../samples.
"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.pipeline import run_pipeline  # noqa: E402
from tests import synthetic  # noqa: E402

CASES = {
    "organizer": synthetic.organizer,
    "cup_with_handle": synthetic.cup_with_handle,
    "thin_spoon": synthetic.thin_spoon,
    "logo_box": synthetic.logo_box,
}


def fit(img: np.ndarray, size: int = 360) -> np.ndarray:
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    s = size / max(h, w)
    img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    canvas = np.full((size, size, 3), 255, np.uint8)
    y, x = (size - img.shape[0]) // 2, (size - img.shape[1]) // 2
    canvas[y : y + img.shape[0], x : x + img.shape[1]] = img
    return canvas


def label(img: np.ndarray, text: str) -> np.ndarray:
    out = img.copy()
    cv2.putText(out, text, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 40, 40), 1, cv2.LINE_AA)
    return out


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, gen in CASES.items():
        photo, _truth = gen()
        t0 = time.perf_counter()
        out = run_pipeline(synthetic.encode(photo))
        elapsed = time.perf_counter() - t0

        case_dir = out_dir / name
        case_dir.mkdir(exist_ok=True)
        (case_dir / "photo.png").write_bytes(synthetic.encode(photo))
        for key, data in (
            ("background_removed", out.background_removed),
            ("mask", out.mask),
            ("outline", out.outline),
            ("drawing", out.drawing),
        ):
            (case_dir / f"{key}.png").write_bytes(data)

        decode = lambda b, f=cv2.IMREAD_COLOR: cv2.imdecode(np.frombuffer(b, np.uint8), f)  # noqa: E731
        rows.append(
            np.hstack(
                [
                    label(fit(photo), f"{name}: photo"),
                    label(fit(decode(out.mask)), "segmentation mask"),
                    label(fit(decode(out.outline)), "extracted outline"),
                    label(fit(decode(out.drawing)), "final drawing"),
                ]
            )
        )
        m = out.metrics
        print(
            f"{name:16s} {elapsed:5.2f}s  candidate={m['mask_candidate']:<15s} "
            f"contours={m['contours']} openings={m['openings']} drawing={m['drawing']['width']}x{m['drawing']['height']}"
        )

    cv2.imwrite(str(out_dir / "contact_sheet.png"), np.vstack(rows))
    print(f"\nSaved to {out_dir}")


if __name__ == "__main__":
    main()
