# braille glitch studio

A real-time **webcam → braille / ASCII glitch-art** renderer, plus an offline video
processor. Built in Python (numpy · OpenCV · pygame · Pillow).

Move in front of the camera and the image tears, corrupts, and smears in response;
everything is live-tweakable from an on-screen control panel.

## What's here

- **`braille_glitch_studio.py`** — the live app: webcam in, glitched braille/ASCII
  out, with a draggable knob panel, presets, and a stats overlay.
- **`glitch_core.py`** — the whole effect pipeline as a reusable, window-free
  `GlitchEngine` class.
- **`video_glitch.py`** — run a video *file* through the same effect and write a
  new video.

## Requirements

Python 3.11+ (developed on 3.14).

```sh
pip install -r requirements.txt
```

Note: this uses **pygame-ce** (not stock `pygame` — its wheel was missing the
`font` module) and **opencv-python-headless**.

## Run

Live studio:

```sh
python3 braille_glitch_studio.py
```

Process a video:

```sh
python3 video_glitch.py input.mp4 output.mp4
```

Edit the settings block at the top of `video_glitch.py` to change the look
(charset / palette / preset / resolution).

## Controls (studio)

| key | action |
| --- | --- |
| `TAB` | show / hide the control panel |
| `I` | stats + FPS overlay |
| `SPACE` | effects on / off (bypass) |
| `V` | cycle character set — braille / blocks / ascii / dense |
| `C` | cycle palette — color / b&w / green / amber |
| `S` | scanlines · `F` fullscreen |
| `1`–`5` | load a preset (clean / vhs / datamosh / tunnel / chaos) |
| mouse | drag the sliders |
| `ESC` | quit |

## Notes

- Frame rate is **camera-bound** (~30 fps on a built-in FaceTime camera) — the
  effects run with plenty of headroom to spare.
- The renderer works at a small internal resolution and upscales, so it stays
  fast even fullscreen.
- Video output is **silent**; to keep the source audio, mux it back with ffmpeg
  (the script prints the exact command).
