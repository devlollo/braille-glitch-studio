# braille glitch studio

A real-time **webcam → braille / ASCII glitch-art** renderer, plus an offline video
processor. Built in Python (numpy · OpenCV · pygame · Pillow).

Move in front of the camera and the image tears, corrupts, and smears in response;
everything is live-tweakable from an on-screen control panel.

## What's here

- **`main.py`** — the entry point: run this (or double-click the app, below).
- **`braille_glitch/engine.py`** — the whole effect pipeline as a reusable,
  window-free `GlitchEngine` class. The single source of truth for every effect.
- **`braille_glitch/studio.py`** — the live app: webcam in, glitched
  braille/ASCII out, with a draggable knob panel, presets, and a stats overlay.
  Pure UI host — all processing goes through `GlitchEngine`.
- **`video_glitch.py`** — run a video *file* through the same effect and write a
  new video.
- **`packaging/`** — scripts that build the two double-clickable apps.
- **`legacy/`** — verbatim backups of the original pre-restructure scripts.

## Requirements

The python.org **3.14 framework build** (`/Library/Frameworks/Python.framework`)
— the launcher apps, VS Code configs, and packaging all point at it explicitly.

```sh
pip install -r requirements.txt
```

Note: this uses **pygame-ce** (not stock `pygame` — its wheel was missing the
`font` module) and **opencv-python-headless**.

## Run

**Double-click** `Braille Glitch Studio.app` in the repo folder — no terminal
needed. The first launch asks for camera permission. (This is the lightweight
dev launcher: it runs the code live from this folder with the system Python,
so edits take effect on the next launch. Rebuild it anytime with
`packaging/make_dev_launcher.sh`.)

From the terminal, the same thing is:

```sh
python3 main.py
```

(Always launch via `main.py` — running `braille_glitch/studio.py` directly
breaks the package imports.)

Process a video (terminal only for now):

```sh
python3 video_glitch.py input.mp4 output.mp4
```

Edit the settings block at the top of `video_glitch.py` to change the look
(charset / palette / preset / resolution).

## Build a standalone app

`packaging/build_app.sh` builds a fully self-contained
`dist/Braille Glitch Studio.app` with PyInstaller — Python and all
dependencies bundled inside. Drag it to /Applications; it keeps working even
if the system Python changes. Launch it from Finder (not the terminal) so
macOS attributes the camera permission to the app.

If the camera prompt ever stops appearing after a rebuild:
`tccutil reset Camera com.egs.brailleglitchstudio` (bundled app) or
`tccutil reset Camera com.egs.brailleglitchstudio.dev` (dev launcher).

## Controls (studio)

| key | action |
| --- | --- |
| `TAB` | show / hide the control panel |
| `I` | stats + FPS overlay |
| `SPACE` | effects on / off (bypass) |
| `A` | audio-reactive mode — the mic level drives the glitch (tune with the *audio gain* knob) |
| `V` | cycle character set — braille / blocks / ascii / dense |
| `C` | cycle palette — color / b&w / green / amber |
| `S` | scanlines · `F` fullscreen |
| `1`–`5` | load a preset (clean / vhs / datamosh / tunnel / chaos) |
| mouse | drag the sliders |
| `ESC` | quit |

## Notes

- Frame rate is **camera-bound** (~30 fps on a built-in FaceTime camera) — the
  full pipeline costs ~7 ms/frame even with every effect on, so there is a lot
  of headroom to spare.
- Audio-reactive mode (`A`) needs microphone permission the first time; sound
  level is added to the motion-driven glitch, so hits and beats tear the image.
- After touching `braille_glitch/engine.py`, run `python3 tests/parity_test.py`
  (proves output is bit-identical to the legacy reference pipeline) and
  `python3 tests/bench.py` (per-effect frame cost).
- The renderer works at a small internal resolution and upscales, so it stays
  fast even fullscreen.
- Video output is **silent**; to keep the source audio, mux it back with ffmpeg
  (the script prints the exact command).
