#!/bin/bash
# Build (or rebuild) the lightweight dev launcher: a double-clickable
# "Braille Glitch Studio.app" at the repo root that runs `python3 main.py`
# with the system's framework Python — no bundling, updates live with the code.
#
# Why this needs to be an .app at all: macOS only shows the camera permission
# prompt to a real app bundle whose Info.plist carries NSCameraUsageDescription.
# Without that key the process is killed *silently* at cv2.VideoCapture(0).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP="$REPO_DIR/Braille Glitch Studio.app"
PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3

if [ ! -x "$PYTHON" ]; then
    echo "error: $PYTHON not found — update PYTHON in this script after a Python upgrade" >&2
    exit 1
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"

# The launcher derives the repo root from its own location, so the .app keeps
# working if the repo folder moves (as long as the .app moves with it).
# Absolute interpreter path: LaunchServices gives a minimal PATH, no profile.
cat > "$APP/Contents/MacOS/launcher" <<EOF
#!/bin/bash
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
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# Ad-hoc signature: on macOS 15.1+ TCC wants a code identity or the camera
# grant may not persist between launches.
codesign --force --deep --sign - "$APP"

echo "Built: $APP"
echo "Double-click it in Finder. If the camera prompt ever stops appearing:"
echo "  tccutil reset Camera com.egs.brailleglitchstudio.dev"
