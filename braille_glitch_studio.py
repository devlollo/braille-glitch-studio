import os
import time
from collections import deque

import pygame
import numpy as np
# cv2 and pygame each bundle their own SDL2; whichever loads second makes macOS
# print a wall of harmless objc "duplicate class" warnings. Mute stderr just
# while cv2 imports so the launch is clean (real import errors still raise).
_saved_fd = os.dup(2)
_null_fd = os.open(os.devnull, os.O_WRONLY)
os.dup2(_null_fd, 2)
try:
    import cv2
finally:
    os.dup2(_saved_fd, 2)
    os.close(_null_fd)
    os.close(_saved_fd)
from PIL import Image, ImageDraw, ImageFont

# ---------------- Parameters (driven by the on-screen panel) ----------------
P = {
    "contrast": 2.5, "black_lift": 0.25, "decay": 0.85, "motion_gain": 6.0, "glitch_floor": 0.02,
    "corrupt_max": 0.12, "max_tears": 6, "aberr_max": 8, "saturation": 1.7,
    "wobble": 0.0, "feedback": 0.0, "pixelsort": 0.0,
}
# key, label, min, max, integer?
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
]
PALETTES = ["color", "bw", "green", "amber"]
FLAT = {"bw": (230, 230, 230), "green": (150, 255, 170), "amber": (255, 190, 80)}
T = {"fx": True, "charset": 0, "palette": 0, "scanlines": True, "invert": False}

# Presets loaded with number keys 1-5 (each overrides the knob values).
PRESETS = [
    # 1 - clean
    {"contrast": 2.0, "black_lift": 0.30, "decay": 0.40, "motion_gain": 3.0, "glitch_floor": 0.0,
     "corrupt_max": 0.03, "max_tears": 2, "aberr_max": 3, "saturation": 1.3,
     "wobble": 0.0, "feedback": 0.0, "pixelsort": 0.0},
    # 2 - VHS
    {"contrast": 2.4, "black_lift": 0.25, "decay": 0.70, "motion_gain": 5.0, "glitch_floor": 0.05,
     "corrupt_max": 0.06, "max_tears": 4, "aberr_max": 10, "saturation": 1.8,
     "wobble": 12.0, "feedback": 0.15, "pixelsort": 0.0},
    # 3 - datamosh
    {"contrast": 2.8, "black_lift": 0.20, "decay": 0.85, "motion_gain": 8.0, "glitch_floor": 0.10,
     "corrupt_max": 0.28, "max_tears": 12, "aberr_max": 8, "saturation": 1.6,
     "wobble": 0.0, "feedback": 0.10, "pixelsort": 6.0},
    # 4 - feedback tunnel
    {"contrast": 2.5, "black_lift": 0.30, "decay": 0.92, "motion_gain": 5.0, "glitch_floor": 0.03,
     "corrupt_max": 0.05, "max_tears": 3, "aberr_max": 6, "saturation": 2.0,
     "wobble": 4.0, "feedback": 0.70, "pixelsort": 0.0},
    # 5 - full chaos
    {"contrast": 3.2, "black_lift": 0.15, "decay": 0.90, "motion_gain": 12.0, "glitch_floor": 0.15,
     "corrupt_max": 0.35, "max_tears": 18, "aberr_max": 16, "saturation": 2.2,
     "wobble": 18.0, "feedback": 0.50, "pixelsort": 10.0},
]

# constant glitch settings
burst_prob = 0.03
flash_prob = 0.25
datamosh_prob = 0.3
target_cols = 90      # internal resolution, scaled up to the window

# ---------------- Braille geometry ----------------
DOT_R, PITCH, GAP_X, GAP_Y = 1, 3, 1, 1
DOT_BITS = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]
WEIGHTS = np.array(DOT_BITS).reshape(1, 4, 1, 2)
BG = np.array((6, 8, 6), np.uint8)
m = DOT_R + 1
cell_w = 2 * m + PITCH + GAP_X
cell_h = 2 * m + 3 * PITCH + GAP_Y
xs = [m, m + PITCH]
ysd = [m + k * PITCH for k in range(4)]
stamp = [(oy, ox) for oy in range(-DOT_R, DOT_R + 1) for ox in range(-DOT_R, DOT_R + 1)]

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


# ---------------- Character sets (cycle with V) ----------------
# Each set is an atlas of glyph ink-masks, shape (n, cell_h, cell_w) of bool.
# "bits"   -> cell value is an 8-bit braille dot pattern (0..255)
# "bright" -> cell value is a brightness bucket (0..n-1)
def _braille_masks():
    arr = np.zeros((256, cell_h, cell_w), bool)
    for b in range(256):
        for row in range(4):
            for col in range(2):
                if b & DOT_BITS[row][col]:
                    for oy, ox in stamp:
                        arr[b, ysd[row] + oy, xs[col] + ox] = True
    return arr


def _block_masks(levels=5):
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6],
                      [3, 11, 1, 9], [15, 7, 13, 5]], float) / 16.0
    yy, xx = np.indices((cell_h, cell_w))
    thr = bayer[yy % 4, xx % 4]
    return np.stack([thr < (i / (levels - 1)) for i in range(levels)])


def _ascii_masks(ramp):
    arr = np.zeros((len(ramp), cell_h, cell_w), bool)
    for i, ch in enumerate(ramp):
        bb = pil_font.getbbox(ch) or (0, 0, 0, 0)
        gw, gh = bb[2] - bb[0], bb[3] - bb[1]
        if gw > 0 and gh > 0:
            img = Image.new("L", (cell_w, cell_h), 0)
            ImageDraw.Draw(img).text(((cell_w - gw) // 2 - bb[0], (cell_h - gh) // 2 - bb[1]),
                                     ch, font=pil_font, fill=255)
            arr[i] = np.asarray(img) > 128
    return arr


CHARSETS = [
    ("braille", _braille_masks(), "bits"),
    ("blocks", _block_masks(5), "bright"),
    ("ascii", _ascii_masks(" .:-=+*#%@"), "bright"),
    ("dense", _ascii_masks(" .,:ilwW$@"), "bright"),
]


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
TOGGLE_ORDER = ["fx", "charset", "palette", "scanlines", "invert"]
toggle_rects = {name: pygame.Rect(PX + PAD, tog_y0 + i * ROW, 150, 18)
                for i, name in enumerate(TOGGLE_ORDER)}
PANEL_H = tog_y0 + len(TOGGLE_ORDER) * ROW + PAD - PY


def draw_panel(screen):
    panel = pygame.Surface((PANEL_W, PANEL_H), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 150))
    screen.blit(panel, (PX, PY))
    for i, (k, label, lo, hi, is_int) in enumerate(KNOBS):
        y = PY + PAD + i * ROW
        screen.blit(text_surf(label), (PX + PAD, y))
        tr = track_rects[k]
        pygame.draw.rect(screen, (60, 60, 60), tr)
        frac = (P[k] - lo) / (hi - lo) if hi > lo else 0
        pygame.draw.rect(screen, (150, 255, 170), (tr.x, tr.y, int(tr.w * frac), tr.h))
        pygame.draw.rect(screen, (230, 230, 230), (tr.x + int(tr.w * frac) - 2, tr.y - 2, 4, tr.h + 4))
        val = f"{int(P[k])}" if is_int else f"{P[k]:.2f}"
        screen.blit(text_surf(val), (VAL_X, y))
    labels = {
        "fx": f"effects: {'ON' if T['fx'] else 'OFF (bypass)'}",
        "charset": f"charset: {CHARSETS[T['charset']][0]}",
        "palette": f"palette: {PALETTES[T['palette']]}",
        "scanlines": f"scanlines: {'on' if T['scanlines'] else 'off'}",
        "invert": f"invert: {'on' if T['invert'] else 'off'}",
    }
    for name, rect in toggle_rects.items():
        if name == "fx":
            bg = (30, 75, 40) if T["fx"] else (85, 30, 30)
        else:
            bg = (40, 45, 40)
        pygame.draw.rect(screen, bg, rect)
        pygame.draw.rect(screen, (90, 100, 90), rect, 1)
        screen.blit(text_surf(labels[name]), (rect.x + 5, rect.y + 3))
    screen.blit(text_surf("TAB hide · SPACE bypass · 1-5 presets · I stats · ESC quit", (140, 150, 140)),
                (PX + PAD, PY + PANEL_H - 14))


def set_knob_from_mouse(k, mx):
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


# ---------------- Setup ----------------
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

rng = np.random.default_rng()
accum = prev_small = prev_vals = prev_final = None
cur_charset = None
glitch = 0.0
cols = char_rows = H = W = 0
frame_i = 0
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
                T["palette"] = (T["palette"] + 1) % len(PALETTES)
            elif e.key == pygame.K_v:
                T["charset"] = (T["charset"] + 1) % len(CHARSETS)
            elif e.key == pygame.K_s:
                T["scanlines"] = not T["scanlines"]
            elif e.key == pygame.K_SPACE:
                T["fx"] = not T["fx"]
            elif pygame.K_1 <= e.key <= pygame.K_5:
                P.update(PRESETS[e.key - pygame.K_1])
                T["fx"] = True
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
                    set_knob_from_mouse(k, mx)
                    break
            if toggle_rects["fx"].collidepoint(mx, my):
                T["fx"] = not T["fx"]
            elif toggle_rects["charset"].collidepoint(mx, my):
                T["charset"] = (T["charset"] + 1) % len(CHARSETS)
            elif toggle_rects["palette"].collidepoint(mx, my):
                T["palette"] = (T["palette"] + 1) % len(PALETTES)
            elif toggle_rects["scanlines"].collidepoint(mx, my):
                T["scanlines"] = not T["scanlines"]
            elif toggle_rects["invert"].collidepoint(mx, my):
                T["invert"] = not T["invert"]
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            dragging = None
        elif e.type == pygame.MOUSEMOTION and dragging:
            set_knob_from_mouse(dragging, e.pos[0])

    t_cap0 = time.perf_counter()
    ok, frame = camera.read()
    t_cap1 = time.perf_counter()
    if not ok:
        continue
    frame = cv2.flip(frame, 1)
    ih, iw = frame.shape[:2]
    if cols == 0:
        cols = target_cols
        char_rows = max(1, int(cols * (ih / iw) * 0.5))
        H, W = char_rows * cell_h, cols * cell_w
    w, h = cols * 2, char_rows * 4
    frame_i += 1

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = np.clip((cv2.resize(gray, (w, h)).astype(np.float32) - 128) * P["contrast"] + 128, 0, 255)
    small = np.maximum(small, P["black_lift"] * 120.0)   # lift crushed blacks -> sparse dots in shadows

    motion = 0.0 if prev_small is None else float(np.mean(np.abs(small - prev_small))) / 255.0
    prev_small = small
    accum = small.copy() if (accum is None or P["decay"] <= 0 or not T["fx"]) else np.maximum(small, accum * P["decay"])
    target = P["glitch_floor"] + motion * P["motion_gain"]
    if rng.random() < burst_prob:
        target = max(target, rng.uniform(0.5, 1.0))
    glitch = min(1.0, max(glitch * 0.85, target)) if T["fx"] else 0.0

    name, gmasks, source = CHARSETS[T["charset"]]
    n = gmasks.shape[0]
    if name != cur_charset:                 # mode changed -> drop stale cell grid
        cur_charset = name
        prev_vals = None

    # Per-cell value grid: braille dot bytes, or brightness buckets.
    flash = rng.random() < flash_prob * glitch
    if source == "bits":
        lit = np.asarray(Image.fromarray(accum.astype(np.uint8)).convert("1"), dtype=bool)
        if T["invert"] ^ flash:
            lit = ~lit
        vals = (lit.reshape(char_rows, 4, cols, 2) * WEIGHTS).sum(axis=(1, 3)).astype(np.uint16)
    else:
        cb = cv2.resize(accum, (cols, char_rows), interpolation=cv2.INTER_AREA)
        if T["invert"] ^ flash:
            cb = 255.0 - cb
        vals = np.clip(cb / 255.0 * (n - 1) + 0.5, 0, n - 1).astype(np.uint16)

    # Glitch the cell grid: tearing, corruption, datamosh.
    for _ in range(int(glitch * P["max_tears"])):
        r = int(rng.integers(0, char_rows))
        vals[r] = np.roll(vals[r], int(rng.integers(-cols, cols + 1)))
    frac = P["corrupt_max"] * glitch
    if frac > 0:
        mask_c = rng.random((char_rows, cols)) < frac
        noise = rng.integers(0, n, (char_rows, cols), dtype=np.uint16)
        vals = np.where(mask_c, noise, vals).astype(np.uint16)
    if prev_vals is not None and char_rows > 4 and cols > 4 and rng.random() < datamosh_prob * glitch:
        bh, bwd = int(rng.integers(2, char_rows // 3 + 1)), int(rng.integers(2, cols // 3 + 1))
        r0, c0 = int(rng.integers(0, char_rows - bh + 1)), int(rng.integers(0, cols - bwd + 1))
        vals[r0:r0 + bh, c0:c0 + bwd] = prev_vals[r0:r0 + bh, c0:c0 + bwd]
    prev_vals = vals.copy()

    # Expand the cell grid into an ink mask via the glyph atlas (one gather).
    mask = gmasks[vals].transpose(0, 2, 1, 3).reshape(H, W)

    palette = PALETTES[T["palette"]]
    if palette == "color":
        c = cv2.cvtColor(cv2.resize(frame, (cols, char_rows), interpolation=cv2.INTER_AREA),
                         cv2.COLOR_BGR2RGB).astype(np.float32)
        lum = c.mean(axis=2, keepdims=True)
        c = np.clip(lum + (c - lum) * P["saturation"], 0, 255)
        c = np.clip(c * 1.2 + 30, 0, 255).astype(np.uint8)
        cell_color = cv2.resize(c, (W, H), interpolation=cv2.INTER_NEAREST)
        output = np.where(mask[..., None], cell_color, BG).astype(np.uint8)
    else:
        output = np.where(mask[..., None], np.array(FLAT[palette], np.uint8), BG).astype(np.uint8)

    # Pixel sort: sort a few rows by brightness.
    for _ in range(int(P["pixelsort"]) if T["fx"] else 0):
        r = int(rng.integers(0, H))
        row = output[r]
        output[r] = row[np.argsort(row.sum(axis=1))]

    # Chromatic aberration.
    if T["fx"] and P["aberr_max"] > 0:
        off = int(glitch * P["aberr_max"])
        if off > 0:
            output[..., 0] = np.roll(output[..., 0], off, axis=1)
            output[..., 2] = np.roll(output[..., 2], -off, axis=1)

    # VHS vertical wobble: shift each row horizontally by a travelling sine.
    if T["fx"] and P["wobble"] > 0:
        rr = np.arange(H)[:, None]
        shift = (P["wobble"] * np.sin(rr * 0.15 + frame_i * 0.3)).astype(np.int32)
        cc = (np.arange(W)[None, :] - shift) % W
        output = output[rr, cc]

    # Feedback zoom: blend a slightly zoomed copy of the last frame.
    if T["fx"] and P["feedback"] > 0 and prev_final is not None:
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, 1.0 + 0.04 * P["feedback"])
        warp = cv2.warpAffine(prev_final, M, (W, H))
        output = np.maximum(output, (warp.astype(np.float32) * (0.5 * P["feedback"])).astype(np.uint8))

    if T["scanlines"]:
        output[1::2] >>= 1
    prev_final = output.copy()

    t_proc1 = time.perf_counter()
    surf = pygame.image.frombuffer(output.tobytes(), (W, H), "RGB")
    screen.blit(pygame.transform.scale(surf, screen.get_size()), (0, 0))
    if panel_visible:
        draw_panel(screen)
    if stats_visible:
        ww, wh = screen.get_size()
        draw_stats(screen, [
            f"FPS: {clock.get_fps():.0f}",
            f"frame: {_mean(tcap) + _mean(tproc) + _mean(trend):.1f} ms",
            f"  capture: {_mean(tcap):.1f} ms",
            f"  process: {_mean(tproc):.1f} ms",
            f"  render:  {_mean(trend):.1f} ms",
            f"camera in: {iw}x{ih}  req {cam_fps:.0f}fps",
            f"internal: {cols}x{char_rows}  ({W}x{H})",
            f"window: {ww}x{wh}",
            f"charset: {name}   palette: {PALETTES[T['palette']]}",
            f"fx: {'ON' if T['fx'] else 'BYPASS'}   glitch: {glitch:.2f}",
        ], ft_hist)
    pygame.display.flip()
    t_draw1 = time.perf_counter()
    tcap.append((t_cap1 - t_cap0) * 1000)
    tproc.append((t_proc1 - t_cap1) * 1000)
    trend.append((t_draw1 - t_proc1) * 1000)
    ft_hist.append((t_draw1 - frame_start) * 1000)
    clock.tick(60)

camera.release()
pygame.quit()
