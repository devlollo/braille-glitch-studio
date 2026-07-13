"""Per-effect frame-cost benchmark for the engine.

Reference numbers (M-series MacBook, 2026-07): base ~4.5 ms, everything-on
~7 ms. The original pre-optimization pipeline was ~23 ms on the vhs preset.

    python3 tests/bench.py
"""
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from braille_glitch.engine import GlitchEngine, PRESETS  # noqa: E402

rng = np.random.default_rng(7)
frames = [(rng.random((480, 640, 3)) * 255).astype(np.uint8) for _ in range(40)]


def bench(label, **kw):
    params = {"wobble": 0.0, "feedback": 0.0, "pixelsort": 0.0, "aberr_max": 0,
              "glitch_floor": 0.3, "motion_gain": 6.0}   # steady glitch level
    params.update(kw.pop("params", {}))
    e = GlitchEngine(params=params, target_cols=90, mirror=True, **kw)
    e.rng = np.random.default_rng(1)
    for f in frames[:8]:
        e.render(f)
    t0 = time.perf_counter()
    for f in frames:
        e.render(f)
    dt = (time.perf_counter() - t0) / len(frames) * 1000
    print(f"{label:34s} {dt:6.2f} ms/frame")


bench("braille + color (no extras)")
bench("braille + bw flat", palette=1)
bench("blocks + color", charset=1)
bench("ascii + color", charset=2)
bench("+ wobble 12", params={"wobble": 12.0})
bench("+ feedback 0.5", params={"feedback": 0.5})
bench("+ pixelsort 6", params={"pixelsort": 6.0})
bench("+ aberration 10", params={"aberr_max": 10})
bench("everything (chaos-ish)", params={"wobble": 18.0, "feedback": 0.5,
                                        "pixelsort": 10.0, "aberr_max": 16})
bench("vhs preset", params=dict(PRESETS[1]))
