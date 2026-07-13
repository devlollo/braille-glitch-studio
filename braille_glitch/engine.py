"""Reusable braille/ASCII glitch renderer (no pygame dependency).

Shared by the live studio and the offline video processor. Given a BGR frame it
returns a rendered RGB image at an internal resolution; the caller upscales.
"""
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

# ---------------- Braille geometry ----------------
DOT_R, PITCH, GAP_X, GAP_Y = 1, 3, 1, 1
DOT_BITS = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]
WEIGHTS = np.array(DOT_BITS).reshape(1, 4, 1, 2)
BG = np.array((6, 8, 6), np.uint8)
_m = DOT_R + 1
cell_w = 2 * _m + PITCH + GAP_X
cell_h = 2 * _m + 3 * PITCH + GAP_Y
_xs = [_m, _m + PITCH]
_ysd = [_m + k * PITCH for k in range(4)]
_stamp = [(oy, ox) for oy in range(-DOT_R, DOT_R + 1) for ox in range(-DOT_R, DOT_R + 1)]

_pil_font = ImageFont.load_default()

# constant glitch settings
burst_prob = 0.03
flash_prob = 0.25
datamosh_prob = 0.3

PALETTES = ["color", "bw", "green", "amber"]
FLAT = {"bw": (230, 230, 230), "green": (150, 255, 170), "amber": (255, 190, 80)}

DEFAULT_P = {
    "contrast": 2.5, "black_lift": 0.25, "decay": 0.85, "motion_gain": 6.0,
    "glitch_floor": 0.02, "corrupt_max": 0.12, "max_tears": 6, "aberr_max": 8,
    "saturation": 1.7, "wobble": 0.0, "feedback": 0.0, "pixelsort": 0.0,
}

PRESET_NAMES = ["clean", "vhs", "datamosh", "tunnel", "chaos"]
PRESETS = [
    {"contrast": 2.0, "black_lift": 0.30, "decay": 0.40, "motion_gain": 3.0, "glitch_floor": 0.0,
     "corrupt_max": 0.03, "max_tears": 2, "aberr_max": 3, "saturation": 1.3,
     "wobble": 0.0, "feedback": 0.0, "pixelsort": 0.0},
    {"contrast": 2.4, "black_lift": 0.25, "decay": 0.70, "motion_gain": 5.0, "glitch_floor": 0.05,
     "corrupt_max": 0.06, "max_tears": 4, "aberr_max": 10, "saturation": 1.8,
     "wobble": 12.0, "feedback": 0.15, "pixelsort": 0.0},
    {"contrast": 2.8, "black_lift": 0.20, "decay": 0.85, "motion_gain": 8.0, "glitch_floor": 0.10,
     "corrupt_max": 0.28, "max_tears": 12, "aberr_max": 8, "saturation": 1.6,
     "wobble": 0.0, "feedback": 0.10, "pixelsort": 6.0},
    {"contrast": 2.5, "black_lift": 0.30, "decay": 0.92, "motion_gain": 5.0, "glitch_floor": 0.03,
     "corrupt_max": 0.05, "max_tears": 3, "aberr_max": 6, "saturation": 2.0,
     "wobble": 4.0, "feedback": 0.70, "pixelsort": 0.0},
    {"contrast": 3.2, "black_lift": 0.15, "decay": 0.90, "motion_gain": 12.0, "glitch_floor": 0.15,
     "corrupt_max": 0.35, "max_tears": 18, "aberr_max": 16, "saturation": 2.2,
     "wobble": 18.0, "feedback": 0.50, "pixelsort": 10.0},
]


# ---------------- Character sets (glyph ink-mask atlases) ----------------
def _braille_masks():
    arr = np.zeros((256, cell_h, cell_w), bool)
    for b in range(256):
        for row in range(4):
            for col in range(2):
                if b & DOT_BITS[row][col]:
                    for oy, ox in _stamp:
                        arr[b, _ysd[row] + oy, _xs[col] + ox] = True
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
        bb = _pil_font.getbbox(ch) or (0, 0, 0, 0)
        gw, gh = bb[2] - bb[0], bb[3] - bb[1]
        if gw > 0 and gh > 0:
            img = Image.new("L", (cell_w, cell_h), 0)
            ImageDraw.Draw(img).text(((cell_w - gw) // 2 - bb[0], (cell_h - gh) // 2 - bb[1]),
                                     ch, font=_pil_font, fill=255)
            arr[i] = np.asarray(img) > 128
    return arr


CHARSETS = [
    ("braille", _braille_masks(), "bits"),
    ("blocks", _block_masks(5), "bright"),
    ("ascii", _ascii_masks(" .:-=+*#%@"), "bright"),
    ("dense", _ascii_masks(" .,:ilwW$@"), "bright"),
]
CHARSET_NAMES = [c[0] for c in CHARSETS]


class GlitchEngine:
    """Stateful renderer: feed it BGR frames in order, get RGB frames out."""

    def __init__(self, params=None, charset=0, palette=0, fx=True,
                 scanlines=True, invert=False, target_cols=90, mirror=False):
        self.P = dict(DEFAULT_P)
        if params:
            self.P.update(params)
        self.charset, self.palette = charset, palette
        self.fx, self.scanlines, self.invert = fx, scanlines, invert
        self.target_cols, self.mirror = target_cols, mirror
        self.rng = np.random.default_rng()
        self.accum = self.prev_small = self.prev_vals = self.prev_final = None
        self.cur_charset = None
        self.glitch = 0.0
        self.frame_i = 0
        self.cols = self.char_rows = self.H = self.W = 0

    def load_preset(self, i):
        self.P.update(PRESETS[i])
        self.fx = True

    def render(self, frame):
        P = self.P
        if self.mirror:
            frame = cv2.flip(frame, 1)
        ih, iw = frame.shape[:2]
        if self.cols == 0:
            self.cols = self.target_cols
            self.char_rows = max(1, int(self.cols * (ih / iw) * 0.5))
            self.H, self.W = self.char_rows * cell_h, self.cols * cell_w
        cols, char_rows, H, W = self.cols, self.char_rows, self.H, self.W
        w, h = cols * 2, char_rows * 4
        self.frame_i += 1

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = np.clip((cv2.resize(gray, (w, h)).astype(np.float32) - 128) * P["contrast"] + 128, 0, 255)
        small = np.maximum(small, P["black_lift"] * 120.0)

        motion = 0.0 if self.prev_small is None else float(np.mean(np.abs(small - self.prev_small))) / 255.0
        self.prev_small = small
        self.accum = (small.copy() if (self.accum is None or P["decay"] <= 0 or not self.fx)
                      else np.maximum(small, self.accum * P["decay"]))
        target = P["glitch_floor"] + motion * P["motion_gain"]
        if self.rng.random() < burst_prob:
            target = max(target, self.rng.uniform(0.5, 1.0))
        self.glitch = min(1.0, max(self.glitch * 0.85, target)) if self.fx else 0.0
        glitch = self.glitch

        name, gmasks, source = CHARSETS[self.charset]
        n = gmasks.shape[0]
        if name != self.cur_charset:
            self.cur_charset = name
            self.prev_vals = None

        flash = self.rng.random() < flash_prob * glitch
        if source == "bits":
            lit = np.asarray(Image.fromarray(self.accum.astype(np.uint8)).convert("1"), dtype=bool)
            if self.invert ^ flash:
                lit = ~lit
            vals = (lit.reshape(char_rows, 4, cols, 2) * WEIGHTS).sum(axis=(1, 3)).astype(np.uint16)
        else:
            cb = cv2.resize(self.accum, (cols, char_rows), interpolation=cv2.INTER_AREA)
            if self.invert ^ flash:
                cb = 255.0 - cb
            vals = np.clip(cb / 255.0 * (n - 1) + 0.5, 0, n - 1).astype(np.uint16)

        for _ in range(int(glitch * P["max_tears"])):
            r = int(self.rng.integers(0, char_rows))
            vals[r] = np.roll(vals[r], int(self.rng.integers(-cols, cols + 1)))
        frac = P["corrupt_max"] * glitch
        if frac > 0:
            mc = self.rng.random((char_rows, cols)) < frac
            noise = self.rng.integers(0, n, (char_rows, cols), dtype=np.uint16)
            vals = np.where(mc, noise, vals).astype(np.uint16)
        if self.prev_vals is not None and char_rows > 4 and cols > 4 and self.rng.random() < datamosh_prob * glitch:
            bh, bwd = int(self.rng.integers(2, char_rows // 3 + 1)), int(self.rng.integers(2, cols // 3 + 1))
            r0, c0 = int(self.rng.integers(0, char_rows - bh + 1)), int(self.rng.integers(0, cols - bwd + 1))
            vals[r0:r0 + bh, c0:c0 + bwd] = self.prev_vals[r0:r0 + bh, c0:c0 + bwd]
        self.prev_vals = vals.copy()

        mask = gmasks[vals].transpose(0, 2, 1, 3).reshape(H, W)

        pal = PALETTES[self.palette]
        if pal == "color":
            c = cv2.cvtColor(cv2.resize(frame, (cols, char_rows), interpolation=cv2.INTER_AREA),
                             cv2.COLOR_BGR2RGB).astype(np.float32)
            lum = c.mean(axis=2, keepdims=True)
            c = np.clip(lum + (c - lum) * P["saturation"], 0, 255)
            c = np.clip(c * 1.2 + 30, 0, 255).astype(np.uint8)
            cell_color = cv2.resize(c, (W, H), interpolation=cv2.INTER_NEAREST)
            output = np.where(mask[..., None], cell_color, BG).astype(np.uint8)
        else:
            output = np.where(mask[..., None], np.array(FLAT[pal], np.uint8), BG).astype(np.uint8)

        for _ in range(int(P["pixelsort"]) if self.fx else 0):
            r = int(self.rng.integers(0, H))
            row = output[r]
            output[r] = row[np.argsort(row.sum(axis=1))]

        if self.fx and P["aberr_max"] > 0:
            off = int(glitch * P["aberr_max"])
            if off > 0:
                output[..., 0] = np.roll(output[..., 0], off, axis=1)
                output[..., 2] = np.roll(output[..., 2], -off, axis=1)
        if self.fx and P["wobble"] > 0:
            rr = np.arange(H)[:, None]
            shift = (P["wobble"] * np.sin(rr * 0.15 + self.frame_i * 0.3)).astype(np.int32)
            cc = (np.arange(W)[None, :] - shift) % W
            output = output[rr, cc]
        if self.fx and P["feedback"] > 0 and self.prev_final is not None:
            M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, 1.0 + 0.04 * P["feedback"])
            warp = cv2.warpAffine(self.prev_final, M, (W, H))
            output = np.maximum(output, (warp.astype(np.float32) * (0.5 * P["feedback"])).astype(np.uint8))
        if self.scanlines:
            output[1::2] >>= 1
        self.prev_final = output.copy()
        return output
