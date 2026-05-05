# 🏏 Cricket Coach AI

An AI-powered cricket coaching tool that analyzes batting and bowling technique from video using pose estimation. Upload a video, get instant frame-by-frame feedback on what to fix and why.

## Features

- 🎯 **Auto-detects technique issues** — head position, knee bend, bowling arm height, shoulder turn, follow-through, and more
- 📐 **Angle arc overlays** — draws measured joint angles directly on the video frame (e.g. "Knee: 142° — too BENT")
- ⏸ **Smart auto-pause** — video plays to the exact issue moment, pauses automatically with coaching overlay
- 🟠 **Fading movement trail** — tracks the problem joint through the motion in slow-mo
- 🎳 **Bowling & batting modes** — separate rule sets for bowlers and batters
- 👶👦🧑 **Age group aware** — Under 10, Under 15, Under 18, Adult thresholds
- ↔️ **Left/right handed** — correct joint analysis for both handednesses

## How It Works

1. Upload an MP4/MOV/AVI video of a cricket shot or bowl
2. Select mode (batting/bowling), handedness, and age group
3. AI runs MediaPipe pose estimation on every frame
4. Rules engine evaluates joint angles against cricket coaching standards
5. Top 3 issues are surfaced with:
   - Explanation of what's wrong
   - Why it matters
   - How to fix it
   - A drill to practice

## Tech Stack

- **Backend**: Python, Flask
- **Pose Estimation**: Google MediaPipe Pose Landmarker
- **Video Processing**: OpenCV
- **Frontend**: HTML, Tailwind CSS, Vanilla JS (Canvas API)

## Setup

```bash
pip install -r requirements.txt
python app.py
```

The MediaPipe model (~5 MB) is downloaded automatically on first run.

Then open http://localhost:5000

## Requirements

- Python 3.9+
- Webcam or video file (MP4, MOV, AVI, MKV)
- See `requirements.txt` for Python dependencies
