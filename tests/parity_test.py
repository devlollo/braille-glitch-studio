"""Prove the current engine renders bit-identically to the legacy pipeline.

The optimized GlitchEngine must produce the *exact same pixels* as the
original code in legacy/glitch_core.py: both engines get the same seeded RNG
and the same synthetic frames, and every output frame is compared exactly.
Run after any engine change:

    python3 tests/parity_test.py
"""
import sys
from pathlib import Path

import numpy as np
import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "legacy"))

import glitch_core as old_mod                 # noqa: E402  (legacy reference)
from braille_glitch import engine as new_mod  # noqa: E402


def make_frames(n=20, w=640, h=480):
    """Deterministic moving square over a color gradient — motion drives glitch."""
    yy, xx = np.mgrid[0:h, 0:w]
    base = ((xx / w) * 180).astype(np.uint8)
    frames = []
    for i in range(n):
        f = cv2.merge([base, np.roll(base, i * 9, axis=1), base[::-1]])
        x = int(i / n * (w - 80))
        cv2.rectangle(f, (x, 150), (x + 80, 300), (255, 255, 255), -1)
        frames.append(f)
    return frames


def main():
    frames = make_frames()
    mismatches = 0
    configs = 0

    for pname, pi in [("default", None), ("vhs", 1), ("chaos", 4)]:
        params = old_mod.PRESETS[pi] if pi is not None else None
        for charset in range(4):
            for palette in range(4):
                configs += 1
                eo = old_mod.GlitchEngine(params=params, charset=charset,
                                          palette=palette, mirror=True)
                en = new_mod.GlitchEngine(params=params, charset=charset,
                                          palette=palette, mirror=True)
                eo.rng = np.random.default_rng(99)
                en.rng = np.random.default_rng(99)
                for fi, f in enumerate(frames):
                    if not np.array_equal(eo.render(f), en.render(f)):
                        print(f"MISMATCH preset={pname} charset={charset} "
                              f"palette={palette} frame={fi}")
                        mismatches += 1
                        break

    # bypass and invert paths
    for kw in [{"fx": False}, {"invert": True}]:
        configs += 1
        eo = old_mod.GlitchEngine(mirror=True, **kw)
        en = new_mod.GlitchEngine(mirror=True, **kw)
        eo.rng = np.random.default_rng(5)
        en.rng = np.random.default_rng(5)
        for f in frames:
            if not np.array_equal(eo.render(f), en.render(f)):
                print(f"MISMATCH {kw}")
                mismatches += 1
                break

    # the audio drive hook must (a) default to a no-op and (b) actually work
    e1 = new_mod.GlitchEngine(mirror=True)
    e2 = new_mod.GlitchEngine(mirror=True)
    e1.rng = np.random.default_rng(2)
    e2.rng = np.random.default_rng(2)
    for _ in range(10):
        e1.render(frames[0], drive=0.0)
        e2.render(frames[0], drive=0.9)
    if not (e2.glitch > e1.glitch + 0.3):
        print(f"DRIVE FAILURE: silent={e1.glitch:.3f} driven={e2.glitch:.3f}")
        mismatches += 1

    label = "OK — bit-identical" if mismatches == 0 else "FAILED"
    print(f"{label}: {configs} configs x {len(frames)} frames, "
          f"{mismatches} mismatches")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
