"""The live studio: webcam in, glitched braille/ASCII out, pygame window + UI.

All image processing lives in engine.GlitchEngine — this module is only the
host: camera capture, the window, the control panel, and the stats overlay.
Launch via main.py (running this file directly breaks the relative import).
"""
if __package__ in (None, ""):
    raise SystemExit(
        "studio.py is a module inside the braille_glitch package and can't be run "
        "directly.\nRun the app with:  python3 main.py   (in VS Code: press F5, "
        "or open main.py and hit play)."
    )

import time
from collections import deque

import pygame
import cv2
from PIL import Image, ImageDraw, ImageFont

from .engine import GlitchEngine, CHARSETS, PALETTES
from .audio import MicLevel

target_cols = 90      # internal resolution, scaled up to the window

# key, label, min, max, integer?  (keys match GlitchEngine's P dict)
KNOBS = [
    ("contrast", "contrast", 0.5, 5.0, False),
    ("black_lift", "black lift", 0.0, 1.0, False),
    ("decay", "trails", 0.0, 0.98, False),
    ("motion_gain", "reactivity", 0.0, 15.0, False),
    ("glitch_floor", "glitch floor", 0.0, 0.5, False),
    ("corrupt_max", "corruption", 0.0, 0.4, False),
    ("max_tears", "tears", 0.0, 20.0, True),
    ("aberr_max", "aberration", 0.0, 20.0, True),
    ("saturation", "saturation", 0.0, 3.0, False),
    ("wobble", "vhs wobble", 0.0, 25.0, False),
    ("feedback", "feedback zoom", 0.0, 1.0, False),
    ("pixelsort", "pixel sort", 0.0, 20.0, True),
    ("audio_gain", "audio gain", 0.0, 15.0, False),
]

# ---------------- Panel text: real pygame.font, with a PIL fallback ----------------
_text_cache = {}
try:
    pygame.font.init()
    _pyfont = pygame.font.SysFont("menlo,monaco,couriernew", 14)
except Exception:
    _pyfont = None
pil_font = ImageFont.load_default()


def text_surf(s, color=(220, 220, 220)):
    key = (s, color)
    if key not in _text_cache:
        if _pyfont is not None:
            _text_cache[key] = _pyfont.render(s, True, color)
        else:
            box = pil_font.getbbox(s)
            w, h = max(1, box[2]), max(1, box[3])
            img = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((1, 1), s, font=pil_font, fill=color + (255,))
            _text_cache[key] = pygame.image.frombuffer(img.tobytes(), img.size, "RGBA").convert_alpha()
    return _text_cache[key]


# Panel layout (window coordinates).
PX, PY, PAD, ROW = 12, 12, 8, 22
TRACK_X = PX + PAD + 96
TRACK_W, TRACK_H = 120, 8
VAL_X = TRACK_X + TRACK_W + 8
PANEL_W = 300
track_rects = {}
for i, (k, *_r) in enumerate(KNOBS):
    y = PY + PAD + i * ROW
    track_rects[k] = pygame.Rect(TRACK_X, y + 2, TRACK_W, TRACK_H)
tog_y0 = PY + PAD + len(KNOBS) * ROW + 6
TOGGLE_ORDER = ["fx", "charset", "palette", "scanlines", "invert", "audio"]
toggle_rects = {name: pygame.Rect(PX + PAD, tog_y0 + i * ROW, 150, 18)
                for i, name in enumerate(TOGGLE_ORDER)}
PANEL_H = tog_y0 + len(TOGGLE_ORDER) * ROW + PAD - PY


def draw_panel(screen, engine, mic):
    panel = pygame.Surface((PANEL_W, PANEL_H), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 150))
    screen.blit(panel, (PX, PY))
    for i, (k, label, lo, hi, is_int) in enumerate(KNOBS):
        y = PY + PAD + i * ROW
        screen.blit(text_surf(label), (PX + PAD, y))
        tr = track_rects[k]
        pygame.draw.rect(screen, (60, 60, 60), tr)
        frac = (engine.P[k] - lo) / (hi - lo) if hi > lo else 0
        pygame.draw.rect(screen, (150, 255, 170), (tr.x, tr.y, int(tr.w * frac), tr.h))
        pygame.draw.rect(screen, (230, 230, 230), (tr.x + int(tr.w * frac) - 2, tr.y - 2, 4, tr.h + 4))
        val = f"{int(engine.P[k])}" if is_int else f"{engine.P[k]:.2f}"
        screen.blit(text_surf(val), (VAL_X, y))
    if not mic.available:
        audio_label = "audio: unavailable"
    elif mic.running:
        audio_label = "audio: on  " + "|" * int(mic.level * 8 + 0.5)
    else:
        audio_label = "audio: off"
    labels = {
        "fx": f"effects: {'ON' if engine.fx else 'OFF (bypass)'}",
        "charset": f"charset: {CHARSETS[engine.charset][0]}",
        "palette": f"palette: {PALETTES[engine.palette]}",
        "scanlines": f"scanlines: {'on' if engine.scanlines else 'off'}",
        "invert": f"invert: {'on' if engine.invert else 'off'}",
        "audio": audio_label,
    }
    for name, rect in toggle_rects.items():
        if name == "fx":
            bg = (30, 75, 40) if engine.fx else (85, 30, 30)
        elif name == "audio" and mic.running:
            bg = (30, 75, 40)
        else:
            bg = (40, 45, 40)
        pygame.draw.rect(screen, bg, rect)
        pygame.draw.rect(screen, (90, 100, 90), rect, 1)
        screen.blit(text_surf(labels[name]), (rect.x + 5, rect.y + 3))
    screen.blit(text_surf("TAB hide · SPACE bypass · A audio · 1-5 presets · I stats · ESC quit", (140, 150, 140)),
                (PX + PAD, PY + PANEL_H - 14))


def set_knob_from_mouse(P, k, mx):
    lo, hi, is_int = next((a, b, c) for kk, _l, a, b, c in KNOBS if kk == k)
    frac = min(1.0, max(0.0, (mx - track_rects[k].x) / track_rects[k].w))
    v = lo + frac * (hi - lo)
    P[k] = round(v) if is_int else v


def _mean(d):
    return sum(d) / len(d) if d else 0.0


def draw_stats(screen, lines, ft_hist):
    w, graph_h = 224, 46
    h = len(lines) * 16 + graph_h + 20
    x, y = screen.get_width() - w - 12, 12
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 165))
    screen.blit(panel, (x, y))
    for i, ln in enumerate(lines):
        screen.blit(text_surf(ln, (170, 225, 180)), (x + 8, y + 6 + i * 16))
    gx, gw = x + 8, w - 16
    gy = y + h - graph_h - 6
    if ft_hist:
        scale = max(33.0, max(ft_hist))
        ref = gy + graph_h - int(33.0 / scale * graph_h)     # the 30fps / 33ms budget line
        pygame.draw.line(screen, (110, 110, 60), (gx, ref), (gx + gw, ref), 1)
        n = len(ft_hist)
        for i, ft in enumerate(ft_hist):
            bx = gx + (int(i / (n - 1) * gw) if n > 1 else 0)
            bh = int(min(ft, scale) / scale * graph_h)
            col = (120, 220, 120) if ft <= 33 else (220, 120, 120)
            pygame.draw.line(screen, col, (bx, gy + graph_h), (bx, gy + graph_h - bh), 1)


def run_studio():
    pygame.init()
    screen = pygame.display.set_mode((1000, 720), pygame.RESIZABLE)
    pygame.display.set_caption("braille glitch studio")
    clock = pygame.time.Clock()

    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not camera.isOpened():
        print("Could not open the webcam.")
        raise SystemExit
    cam_fps = camera.get(cv2.CAP_PROP_FPS)

    # mirror=True: the live studio shows a selfie view (video processing doesn't)
    engine = GlitchEngine(target_cols=target_cols, mirror=True)
    mic = MicLevel()

    panel_visible = True
    stats_visible = False
    dragging = None
    fullscreen = False
    windowed_size = (1000, 720)
    ft_hist = deque(maxlen=100)
    tcap, tproc, trend = deque(maxlen=30), deque(maxlen=30), deque(maxlen=30)
    running = True

    while running:
        frame_start = time.perf_counter()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.VIDEORESIZE and not fullscreen:
                windowed_size = (e.w, e.h)
                screen = pygame.display.set_mode(windowed_size, pygame.RESIZABLE)
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_TAB:
                    panel_visible = not panel_visible
                elif e.key == pygame.K_i:
                    stats_visible = not stats_visible
                elif e.key == pygame.K_c:
                    engine.palette = (engine.palette + 1) % len(PALETTES)
                elif e.key == pygame.K_v:
                    engine.charset = (engine.charset + 1) % len(CHARSETS)
                elif e.key == pygame.K_s:
                    engine.scanlines = not engine.scanlines
                elif e.key == pygame.K_a:
                    mic.stop() if mic.running else mic.start()
                elif e.key == pygame.K_SPACE:
                    engine.fx = not engine.fx
                elif pygame.K_1 <= e.key <= pygame.K_5:
                    engine.load_preset(e.key - pygame.K_1)
                elif e.key == pygame.K_f:
                    fullscreen = not fullscreen
                    screen = (pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                              if fullscreen else
                              pygame.display.set_mode(windowed_size, pygame.RESIZABLE))
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and panel_visible:
                mx, my = e.pos
                for k, tr in track_rects.items():
                    if tr.inflate(6, 6).collidepoint(mx, my):
                        dragging = k
                        set_knob_from_mouse(engine.P, k, mx)
                        break
                if toggle_rects["fx"].collidepoint(mx, my):
                    engine.fx = not engine.fx
                elif toggle_rects["charset"].collidepoint(mx, my):
                    engine.charset = (engine.charset + 1) % len(CHARSETS)
                elif toggle_rects["palette"].collidepoint(mx, my):
                    engine.palette = (engine.palette + 1) % len(PALETTES)
                elif toggle_rects["scanlines"].collidepoint(mx, my):
                    engine.scanlines = not engine.scanlines
                elif toggle_rects["invert"].collidepoint(mx, my):
                    engine.invert = not engine.invert
                elif toggle_rects["audio"].collidepoint(mx, my):
                    mic.stop() if mic.running else mic.start()
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                dragging = None
            elif e.type == pygame.MOUSEMOTION and dragging:
                set_knob_from_mouse(engine.P, dragging, e.pos[0])

        t_cap0 = time.perf_counter()
        ok, frame = camera.read()
        t_cap1 = time.perf_counter()
        if not ok:
            continue
        ih, iw = frame.shape[:2]

        drive = mic.level * engine.P["audio_gain"] if mic.running else 0.0
        output = engine.render(frame, drive)

        t_proc1 = time.perf_counter()
        surf = pygame.image.frombuffer(output.tobytes(), (engine.W, engine.H), "RGB")
        screen.blit(pygame.transform.scale(surf, screen.get_size()), (0, 0))
        if panel_visible:
            draw_panel(screen, engine, mic)
        if stats_visible:
            ww, wh = screen.get_size()
            draw_stats(screen, [
                f"FPS: {clock.get_fps():.0f}",
                f"frame: {_mean(tcap) + _mean(tproc) + _mean(trend):.1f} ms",
                f"  capture: {_mean(tcap):.1f} ms",
                f"  process: {_mean(tproc):.1f} ms",
                f"  render:  {_mean(trend):.1f} ms",
                f"camera in: {iw}x{ih}  req {cam_fps:.0f}fps",
                f"internal: {engine.cols}x{engine.char_rows}  ({engine.W}x{engine.H})",
                f"window: {ww}x{wh}",
                f"charset: {CHARSETS[engine.charset][0]}   palette: {PALETTES[engine.palette]}",
                f"fx: {'ON' if engine.fx else 'BYPASS'}   glitch: {engine.glitch:.2f}",
                f"audio: {mic.level:.2f}" if mic.running else "audio: off",
            ], ft_hist)
        pygame.display.flip()
        t_draw1 = time.perf_counter()
        tcap.append((t_cap1 - t_cap0) * 1000)
        tproc.append((t_proc1 - t_cap1) * 1000)
        trend.append((t_draw1 - t_proc1) * 1000)
        ft_hist.append((t_draw1 - frame_start) * 1000)
        clock.tick(60)

    mic.stop()
    camera.release()
    pygame.quit()
