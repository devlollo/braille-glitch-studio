# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the self-contained macOS app.
# Build with packaging/build_app.sh (needs the .venv-build it creates).
#
# Notes that matter:
# - onedir + windowed: onefile .apps unpack everything on every launch (slow,
#   re-triggers Gatekeeper) and are explicitly discouraged for windowed apps.
# - argv_emulation must stay False: the bootloader's Apple-event processing
#   corrupts pygame/SDL startup.
# - The camera keys in info_plist are load-bearing: without
#   NSCameraUsageDescription, macOS kills the app *silently* at
#   cv2.VideoCapture(0) — no prompt, no traceback.
import os

a = Analysis(
    [os.path.join(SPECPATH, '..', 'main.py')],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Braille Glitch Studio',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch='arm64',
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='BrailleGlitchStudio')
app = BUNDLE(
    coll,
    name='Braille Glitch Studio.app',
    icon=None,
    bundle_identifier='com.egs.brailleglitchstudio',
    version='1.0.0',
    info_plist={
        'NSCameraUsageDescription':
            'Braille Glitch Studio uses your webcam for the live glitch renderer.',
        'NSCameraUseContinuityCameraDeviceType': True,
        'NSHighResolutionCapable': True,
    },
)
