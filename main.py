"""Braille Glitch Studio — entry point.

Run the live studio:

    python3 main.py

(or double-click "Braille Glitch Studio.app"). To process a video file
instead, see video_glitch.py.
"""
import os

import pygame

# cv2 and pygame each bundle their own SDL2; whichever loads second makes macOS
# print a wall of harmless objc "duplicate class" warnings. pygame is imported
# above so its SDL2 loads first, and stderr is muted just while cv2 imports —
# this is the first cv2 import in the process, so every later `import cv2`
# reuses it silently (real import errors still raise).
_saved_fd = os.dup(2)
_null_fd = os.open(os.devnull, os.O_WRONLY)
os.dup2(_null_fd, 2)
try:
    import cv2
finally:
    os.dup2(_saved_fd, 2)
    os.close(_null_fd)
    os.close(_saved_fd)

from braille_glitch.studio import run_studio

if __name__ == "__main__":
    run_studio()
