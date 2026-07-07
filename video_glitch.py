"""Run a video file through the braille/ASCII glitch effect and write a new video.

Usage:
    python3 video_glitch.py input.mp4 output.mp4

Edit the settings below to change the look. Output is video-only (no audio); see
the note printed at the end for how to keep the original soundtrack.
"""
import sys
import cv2
from glitch_core import GlitchEngine, CHARSET_NAMES, PALETTES, PRESET_NAMES, PRESETS

# ---- Look (edit these) ----
CHARSET = "braille"    # braille | blocks | ascii | dense
PALETTE = "color"      # color | bw | green | amber
PRESET = "vhs"         # clean | vhs | datamosh | tunnel | chaos | None
TARGET_COLS = 100      # internal detail (higher = finer, slower)
OUTPUT_SCALE = 1.0     # output size relative to the input video


def main():
    args = sys.argv[1:]
    inp = args[0] if len(args) >= 1 else "input.mp4"
    outp = args[1] if len(args) >= 2 else "output.mp4"

    cap = cv2.VideoCapture(inp)
    if not cap.isOpened():
        print(f"Could not open input video: {inp}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    in_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    in_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_w = max(2, int(in_w * OUTPUT_SCALE))
    out_h = max(2, int(in_h * OUTPUT_SCALE))

    params = PRESETS[PRESET_NAMES.index(PRESET)] if PRESET in PRESET_NAMES else None
    charset = CHARSET_NAMES.index(CHARSET) if CHARSET in CHARSET_NAMES else 0
    palette = PALETTES.index(PALETTE) if PALETTE in PALETTES else 0
    engine = GlitchEngine(params=params, charset=charset, palette=palette,
                          target_cols=TARGET_COLS, mirror=False)

    writer = cv2.VideoWriter(outp, cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h))
    if not writer.isOpened():
        print("Could not open the video writer (codec issue).")
        cap.release()
        return

    print(f"Processing {inp}  ({in_w}x{in_h}, {total or '?'} frames @ {fps:.0f}fps)")
    print(f"look: charset={CHARSET} palette={PALETTE} preset={PRESET} -> {out_w}x{out_h}")

    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        rgb = engine.render(frame)                                   # internal-res RGB
        big = cv2.resize(rgb, (out_w, out_h), interpolation=cv2.INTER_NEAREST)
        writer.write(cv2.cvtColor(big, cv2.COLOR_RGB2BGR))           # cv2 wants BGR
        i += 1
        if total:
            print(f"\r  {i}/{total} frames ({100 * i / total:.0f}%)", end="", flush=True)

    cap.release()
    writer.release()
    print(f"\nDone: wrote {i} frames -> {outp}")
    print("Note: output has no audio. To keep the original soundtrack, run:")
    print(f'  ffmpeg -i "{outp}" -i "{inp}" -map 0:v -map 1:a? -c:v copy -shortest out_with_audio.mp4')


if __name__ == "__main__":
    main()
