#!/bin/bash
echo ""
echo " ============================================"
echo "  Cricket Coach AI — First Time Setup"
echo " ============================================"
echo ""

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo " ERROR: Python 3 is not installed!"
    echo ""
    echo " Download it from: https://www.python.org/downloads/"
    exit 1
fi

echo " Python found. Installing libraries..."
echo " (This may take a few minutes on first run)"
echo ""

pip3 install flask mediapipe opencv-python numpy reportlab

echo ""
echo " ============================================"
echo "  Setup complete!"
echo "  Run ./start.sh to launch the app."
echo " ============================================"
echo ""
