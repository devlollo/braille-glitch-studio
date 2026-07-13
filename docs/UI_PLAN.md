# UI v2 — instrument panel (approved plan, 2026-07-13)

Status: **approved, not yet implemented**. This file is the source of truth for
the next work session; it assumes no other context.

## Context

The current control panel (`braille_glitch/studio.py`) is a flat list of 13
slider rows and 6 text-toggle rows drawn by `draw_panel` — functional but
skeletal. Goal: a much more developed control surface with real visual
feedback. Decisions already made by Emiliano:

- **One rich side panel** — no separate bottom toolbar.
- **Live meters** + **letterbox fix** are the feedback priorities
  (explicitly NOT tooltips, NOT smart preset chips — deferred).
- **Phosphor terminal aesthetic** — the panel speaks the app's own visual
  language.

Research already done (don't redo): pygame_gui rejected (generic widget
chrome, extra bundle dependency, fights a bespoke aesthetic); Dear ImGui
bindings rejected (pyimgui's pygame integration needs an OpenGL display; this
app blits a software surface). **Hand-rolled widget kit wins**: full aesthetic
control, zero new dependencies, ~1 ms draw budget easily met, and it doubles
as Emiliano's learning codebase (small classes, visible behavior).

The engine must stay untouched — `python3 tests/parity_test.py` must stay
green (bit-identical) throughout.

## Architecture

**New module `braille_glitch/ui.py`** — a small retained widget kit, written
to be read (docstrings aimed at a beginner who is strong on theory):

- `THEME` constants: phosphor green `(150,255,170)` fills/values, amber
  `(255,190,80)` active/dragging, red `(220,90,90)` bypass-off, dim green
  `(140,150,140)` labels, translucent black panel `(0,0,0,165)`, 1px borders
  `(90,100,90)`. Monospace via the existing font path.
- `text_surf` (+ its capped cache) moves here from studio.py; the stats
  overlay in studio.py imports it from ui.
- Widgets, each with `rect`, `draw(screen)`, `handle(event) -> bool`:
  - `Slider` — label, lo/hi/int, bound to `engine.P[key]`; track+fill+handle
    as today; while dragging the value renders amber. Drag capture: once
    grabbed, follows MOUSEMOTION until MOUSEBUTTONUP even outside the track
    (preserves current behavior).
  - `Button` — toggle with on/off colors and a label callback (fx bypass,
    scanlines, invert, audio on/off).
  - `Cycler` — click advances through a list (charset, palette), shows the
    current value.
  - `Meter` — horizontal level bar with peak-hold
    (`peak = max(peak*0.95, v)`, drawn as a tick); fill goes amber above 0.8.
    Feeds: `engine.glitch` and `mic.level`.
  - `PresetButton` row — five numbered buttons calling
    `engine.load_preset(i)` (mouse affordance for what is keyboard-only
    today; no modified-state tracking, deliberately).
  - `Section` — labeled header with a collapse triangle; click
    collapses/expands; contains widgets; panel relayouts on toggle.
  - `Panel` — owns sections, computes layout, draws the translucent
    background, routes events top-down.

**Panel structure** (left side, TAB toggles visibility, width ~320px):

1. Header: title + big FX button (green "EFFECTS ON" / red "BYPASS") +
   **glitch meter** (the app's heartbeat, always moving).
2. `GLITCH`: reactivity, glitch floor, corruption, tears, aberration,
   pixel sort.
3. `LOOK`: contrast, black lift, saturation, trails, charset cycler,
   palette cycler, scanlines + invert buttons.
4. `VIDEO`: vhs wobble, feedback zoom.
5. `AUDIO`: audio on/off button, audio gain slider, **mic meter** (dimmed
   when off).
6. `PRESETS`: buttons 1–5.
7. Footer: the two hint lines (update wording as needed).

Estimated full height ~550px < 720 window; sections collapse for small
windows.

**Letterboxing** (studio.py, independent of ui.py): compute the largest rect
with the engine's W:H aspect that fits the window, `pygame.transform.scale`
into that rect, fill the remaining bars with the engine background `(6,8,6)`.
Applies to windowed, resized, and fullscreen. (This is the long-deferred
stretch-distortion fix.)

**Unchanged**: all keyboard shortcuts (TAB/I/SPACE/A/V/C/S/F/1–5/ESC), the
stats overlay (`draw_stats`), the engine, video_glitch.py, packaging/.

## Steps (each leaves the app runnable)

1. **Letterbox fix** in studio.py — small, independent; verify by resizing to
   extreme shapes.
2. **ui.py** with THEME, moved `text_surf`, `Slider`, `Button`, `Cycler`,
   `Meter`, `Section`, `Panel`; plus **`tests/ui_smoke.py`**: headless
   construction, offscreen draw of every widget, synthetic
   `pygame.event.Event` click/drag assertions (slider drag writes `engine.P`,
   button toggles, section collapses, meter clamps).
3. **Rebuild the studio panel** on ui.py: build sections from a
   KNOBS-with-sections table; wire buttons/cyclers to engine attrs and mic;
   meters to `engine.glitch` / `mic.level`; delete `draw_panel`,
   `track_rects`, `toggle_rects`, `set_knob_from_mouse`; the mouse branch of
   the event loop becomes `panel.handle(event)`. Migration checklist: every
   control reachable by mouse exactly as before (13 sliders, fx, charset,
   palette, scanlines, invert, audio, presets).
4. **Polish**: peak-hold tuning, bypass button prominence, hint lines, panel
   width/spacing.
5. README controls section update; commit (push only on request).

## Verification

- `python3 tests/parity_test.py` — engine untouched, must stay bit-identical.
- `python3 tests/ui_smoke.py` — headless widget behavior (new).
- `python3 tests/bench.py` — unchanged engine numbers; add a one-off timing
  print of `panel.draw` on an offscreen surface (< 1 ms budget).
- Compile checks on all modules; brief `main.py` launch (in a shell without
  camera permission it should exit cleanly with "Could not open the webcam.").
- Manual (Emiliano): every control clickable, sliders drag smoothly, sections
  collapse, meters dance (glitch via motion, mic via `A` + sound), window
  resize letterboxes instead of stretching, fullscreen clean.

## Notes

- ui.py is deliberately the next learning surface: after this lands, a good
  first solo exercise is writing one widget yourself (e.g. a `Checkbox`
  replacing one `Button`), with `tests/ui_smoke.py` as the safety net.
- Still deferred (unchanged backlog): tooltips/hover states, smart preset
  chips, save/record, in-app video file picker, app icon (.icns), custom
  minimal OpenCV build to shrink the bundle below ~165 MB.
