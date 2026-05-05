#!/bin/bash
echo ""
echo " ============================================"
echo "  Cricket Coach AI — Starting..."
echo " ============================================"
echo ""
echo " Opening browser at http://localhost:5000"
echo " Keep this terminal open while using the app."
echo " Press Ctrl+C to stop."
echo ""

# Open browser after a short delay
(sleep 2 && open "http://localhost:5000" 2>/dev/null || xdg-open "http://localhost:5000" 2>/dev/null) &

python3 app.py
