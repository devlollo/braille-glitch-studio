#!/bin/bash
# Build (or rebuild) the lightweight dev launcher: a double-clickable
# "Braille Glitch Studio.app" at the repo root that runs `python3 main.py`
# with the system's framework Python — no bundling, updates live with the code.
#
# Two macOS gotchas this script handles:
# - The camera permission prompt only appears for an app bundle whose
#   Info.plist carries NSCameraUsageDescription; without it the process is
#   killed *silently* at cv2.VideoCapture(0).
# - The repo lives in ~/Desktop, which is TCC-protected: the app also needs
#   the Desktop-folder permission just to READ the code, and it must be
#   signed for any of these grants to stick. Signing happens in /private/tmp
#   because iCloud sync keeps re-stamping xattrs that codesign rejects.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Braille Glitch Studio.app"
PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3

if [ ! -x "$PYTHON" ]; then
    echo "error: $PYTHON not found — update PYTHON in this script after a Python upgrade" >&2
    exit 1
fi

TMP=$(mktemp -d /private/tmp/bgs-dev.XXXXXX)
trap 'rm -rf "$TMP"' EXIT
APP="$TMP/$APP_NAME"
mkdir -p "$APP/Contents/MacOS"

# The launcher derives the repo root from its own location, so the .app keeps
# working if the repo folder moves (as long as the .app moves with it).
# Absolute interpreter path: LaunchServices gives a minimal PATH, no profile.
# Output goes to a log file (LaunchServices has no terminal); one launch kept.
cat > "$APP/Contents/MacOS/launcher" <<EOF
#!/bin/bash
exec > /private/tmp/bgs-launcher.log 2>&1
echo "=== launch \$(date) ==="
cd "\$(dirname "\$0")/../../.." || exit 1
exec $PYTHON main.py
EOF
chmod +x "$APP/Contents/MacOS/launcher"

cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleName</key>
    <string>Braille Glitch Studio</string>
    <key>CFBundleDisplayName</key>
    <string>Braille Glitch Studio</string>
    <key>CFBundleIdentifier</key>
    <string>com.egs.brailleglitchstudio.dev</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>NSCameraUsageDescription</key>
    <string>Braille Glitch Studio uses your webcam for the live glitch renderer.</string>
    <key>NSCameraUseContinuityCameraDeviceType</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>The audio-reactive mode drives the glitch with your microphone level.</string>
    <key>NSDesktopFolderUsageDescription</key>
    <string>The studio's code lives in a folder on your Desktop; the launcher needs to read it.</string>
    <key>NSDocumentsFolderUsageDescription</key>
    <string>Needed only if the project folder is moved into Documents.</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# Ad-hoc signature: on macOS 15.1+ TCC wants a code identity or the grants
# (camera, Desktop files) may not persist between launches.
codesign --force --deep --sign - "$APP"
codesign --verify --deep "$APP"

rm -rf "$REPO_DIR/$APP_NAME"
ditto "$APP" "$REPO_DIR/$APP_NAME"

echo "Built: $REPO_DIR/$APP_NAME"
echo "Double-click it in Finder. If permission prompts ever stop appearing:"
echo "  tccutil reset All com.egs.brailleglitchstudio.dev"
