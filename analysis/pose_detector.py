import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

MODEL_PATH = 'pose_landmarker_lite.task'

# Named landmark indices (same 33-point set as always)
LANDMARKS = {
    'nose': 0,
    'left_shoulder': 11,
    'right_shoulder': 12,
    'left_elbow': 13,
    'right_elbow': 14,
    'left_wrist': 15,
    'right_wrist': 16,
    'left_hip': 23,
    'right_hip': 24,
    'left_knee': 25,
    'right_knee': 26,
    'left_ankle': 27,
    'right_ankle': 28,
}

# Skeleton lines to draw (by name pairs)
DRAW_CONNECTIONS = [
    ('left_shoulder', 'right_shoulder'),
    ('left_shoulder', 'left_elbow'),
    ('left_elbow', 'left_wrist'),
    ('right_shoulder', 'right_elbow'),
    ('right_elbow', 'right_wrist'),
    ('left_shoulder', 'left_hip'),
    ('right_shoulder', 'right_hip'),
    ('left_hip', 'right_hip'),
    ('left_hip', 'left_knee'),
    ('left_knee', 'left_ankle'),
    ('right_hip', 'right_knee'),
    ('right_knee', 'right_ankle'),
]


def calculate_angle(a, b, c):
    """Angle (degrees) at vertex b formed by rays b→a and b→c."""
    a, b, c = np.array(a, float), np.array(b, float), np.array(c, float)
    ba, bc = a - b, c - b
    cos_a = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-9)
    return float(np.degrees(np.arccos(np.clip(cos_a, -1.0, 1.0))))


def landmark_xy(lm_list, name, w, h):
    """Return (x_px, y_px) for a named landmark from a Tasks API landmark list."""
    lm = lm_list[LANDMARKS[name]]
    return [lm.x * w, lm.y * h]


def landmark_visible(lm_list, name, threshold=0.4):
    lm = lm_list[LANDMARKS[name]]
    return getattr(lm, 'visibility', 1.0) >= threshold


def create_image_landmarker():
    """Return a PoseLandmarker configured for single-image (frame) detection."""
    options = mp_vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=mp_vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.45,
        min_pose_presence_confidence=0.45,
    )
    return mp_vision.PoseLandmarker.create_from_options(options)


def detect_landmarks(landmarker, bgr_frame):
    """Detect pose in one BGR frame. Returns landmark list or None."""
    rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect(mp_img)
    if result.pose_landmarks:
        return result.pose_landmarks[0]
    return None


def draw_skeleton(frame, lm_list, problem_joints=(), good_joints=()):
    """Draw colour-coded skeleton overlay. Returns annotated copy."""
    if lm_list is None:
        return frame
    out = frame.copy()
    h, w = frame.shape[:2]

    for (a_name, b_name) in DRAW_CONNECTIONS:
        if not (landmark_visible(lm_list, a_name) and landmark_visible(lm_list, b_name)):
            continue
        pa = tuple(int(v) for v in landmark_xy(lm_list, a_name, w, h))
        pb = tuple(int(v) for v in landmark_xy(lm_list, b_name, w, h))
        cv2.line(out, pa, pb, (180, 180, 180), 2, cv2.LINE_AA)

    for name in LANDMARKS:
        if not landmark_visible(lm_list, name):
            continue
        pt = tuple(int(v) for v in landmark_xy(lm_list, name, w, h))
        if name in problem_joints:
            cv2.circle(out, pt, 9, (0, 0, 220), -1, cv2.LINE_AA)
        elif name in good_joints:
            cv2.circle(out, pt, 9, (0, 200, 60), -1, cv2.LINE_AA)
        else:
            cv2.circle(out, pt, 6, (0, 140, 255), -1, cv2.LINE_AA)

    return out


def draw_skeleton_neutral(frame, lm_list):
    """Draw skeleton lines only — no joint dots at all.
    The canvas overlay in the browser handles all coloured dot logic,
    so the video stays clean and uncluttered."""
    if lm_list is None:
        return frame
    out = frame.copy()
    h, w = frame.shape[:2]

    for (a_name, b_name) in DRAW_CONNECTIONS:
        if not (landmark_visible(lm_list, a_name) and landmark_visible(lm_list, b_name)):
            continue
        pa = tuple(int(v) for v in landmark_xy(lm_list, a_name, w, h))
        pb = tuple(int(v) for v in landmark_xy(lm_list, b_name, w, h))
        cv2.line(out, pa, pb, (160, 160, 160), 2, cv2.LINE_AA)

    return out
