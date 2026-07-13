#!/bin/bash
# Build the self-contained "Braille Glitch Studio.app" with PyInstaller.
# Output: dist/Braille Glitch Studio.app — bundles Python + all deps; drag it
# to /Applications and launch from Finder (Finder launch is what makes macOS
# attribute the camera permission prompt to the app).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
VENV=.venv-build

if [ ! -x "$PYTHON" ]; then
    echo "error: $PYTHON not found — update PYTHON in this script after a Python upgrade" >&2
    exit 1
fi

if [ ! -d "$VENV" ]; then
    "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q --upgrade pip
pip install -q 'pyinstaller>=6.20' -r requirements.txt

pyinstaller --noconfirm --distpath dist --workpath build packaging/BrailleGlitchStudio.spec

# Sign in a non-synced temp dir. This repo lives on the iCloud-synced Desktop,
# where fileproviderd keeps re-stamping FinderInfo xattrs on the bundle —
# codesign then aborts with "detritus not allowed" no matter how often you
# xattr-strip in place. /private/tmp is not synced, so: copy clean, sign
# there, verify, move back. (Also covers pyinstaller#8029, which can leave
# the top-level executable unsigned — an unsigned app never gets the camera
# prompt on macOS 15.1+.)
APP="dist/Braille Glitch Studio.app"
TMP=$(mktemp -d /private/tmp/bgs-sign.XXXXXX)
trap 'rm -rf "$TMP"' EXIT
ditto --norsrc --noextattr --noqtn "$APP" "$TMP/Braille Glitch Studio.app"
codesign --force --deep --sign - --timestamp=none "$TMP/Braille Glitch Studio.app"
codesign --verify --deep --strict "$TMP/Braille Glitch Studio.app"
rm -rf "$APP"
ditto "$TMP/Braille Glitch Studio.app" "$APP"
# non-strict verify: iCloud may have re-stamped harmless xattrs already
codesign --verify --deep "$APP"

echo
echo "Built: dist/Braille Glitch Studio.app"
echo "If the camera prompt ever stops appearing after a rebuild:"
echo "  tccutil reset Camera com.egs.brailleglitchstudio"
