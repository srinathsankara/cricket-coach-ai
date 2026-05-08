import os
import cv2
import numpy as np
from .pose_detector import (LANDMARKS, create_image_landmarker,
                             detect_landmarks, draw_skeleton_neutral)
from .batting_rules import analyze_batting, detect_shot_type
from .bowling_rules import analyze_bowling

SAMPLE_EVERY = 3   # analyse 1-in-N frames for speed


def process_video(video_path, mode='batting', handedness='right',
                  age_group='under10', model_path='pose_landmarker_lite.task',
                  trim_start=0.0, trim_end=0.0,
                  progress_callback=None):

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Could not open the video file. Please check the format.")

    fps          = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video_dur    = total_frames / fps

    # Resolve trim range (trim_end=0 means full video)
    t_start = max(0.0, trim_start)
    t_end   = trim_end if trim_end > t_start else video_dur
    t_end   = min(t_end, video_dur)

    start_frame = int(t_start * fps)
    end_frame   = int(t_end   * fps)
    clip_frames = max(1, end_frame - start_frame)

    # ── Pass 1: pose detection on trimmed clip ────────────────────────────
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frame_data      = []
    frame_landmarks = []   # [{t: float, j: {name: [x, y]}}] for canvas sync
    landmarker      = create_image_landmarker(model_path)

    rel_idx = 0   # frame index relative to trim start
    while True:
        ret, frame = cap.read()
        if not ret or (start_frame + rel_idx) >= end_frame:
            break
        if rel_idx % SAMPLE_EVERY == 0:
            lm = detect_landmarks(landmarker, frame)
            frame_data.append({
                'frame_idx': rel_idx,
                'landmarks': lm,
                'w': width,
                'h': height,
            })
            # Store normalised joint positions for JS canvas animation
            if lm is not None:
                joints = {}
                for name, idx in LANDMARKS.items():
                    lm_pt = lm[idx]
                    vis = getattr(lm_pt, 'visibility', 1.0)
                    if vis >= 0.4:
                        joints[name] = [round(lm_pt.x, 4), round(lm_pt.y, 4)]
                frame_landmarks.append({
                    't': round(rel_idx / fps, 3),
                    'j': joints,
                })
        rel_idx += 1
        if progress_callback and rel_idx % 15 == 0:
            progress_callback(int(rel_idx / clip_frames * 55))

    cap.release()
    landmarker.close()

    # ── Temporal smoothing of frame_landmarks ────────────────────────────
    frame_landmarks = _smooth_frame_landmarks(frame_landmarks, window=5)

    if progress_callback:
        progress_callback(58)

    # ── Biomechanical analysis ────────────────────────────────────────────
    checkpoints = (analyze_batting(frame_data, handedness)
                   if mode == 'batting'
                   else analyze_bowling(frame_data, handedness))

    # ── Shot / delivery type classification ──────────────────────────────
    shot_type = (detect_shot_type(frame_data, handedness)
                 if mode == 'batting' else 'bowling')

    # ── Compute issue_start_sec: when does the issue first appear? ────────
    for cp in checkpoints:
        fidx = min(cp.get('issue_frame_idx', 0), max(len(frame_data) - 1, 0))
        cp['issue_start_sec'] = round(
            frame_data[fidx]['frame_idx'] / fps, 3) if frame_data else 0.0

    if progress_callback:
        progress_callback(65)

    # ── Average normalised landmark positions (for frontend zoom) ─────────
    landmark_positions = _avg_landmark_positions(frame_data)

    # ── Pass 2: write CROPPED neutral-skeleton video ──────────────────────
    job_id   = os.path.splitext(os.path.basename(video_path))[0]
    out_path = os.path.join('results', f'{job_id}_annotated.mp4')

    _write_annotated_video(
        video_path, out_path, frame_data,
        fps, width, height,
        start_frame, end_frame,
        progress_callback,
    )

    if progress_callback:
        progress_callback(98)

    # ── Sort feedback ─────────────────────────────────────────────────────
    order      = {'fix': 0, 'improve': 1, 'good': 2, 'unknown': 3}
    sorted_cps = sorted(checkpoints, key=lambda c: order.get(c['status'], 3))
    top_issues = [c for c in sorted_cps if c['status'] in ('fix', 'improve')][:3]
    top_good   = [c for c in sorted_cps if c['status'] == 'good'][:2]

    detected   = sum(1 for fd in frame_data if fd['landmarks'] is not None)
    confidence = int(detected / max(len(frame_data), 1) * 100)

    if progress_callback:
        progress_callback(100)

    return {
        'mode': mode,
        'handedness': handedness,
        'age_group': age_group,
        'shot_type': shot_type,
        'checkpoints': checkpoints,
        'top_issues': top_issues,
        'top_good': top_good,
        'video_filename': os.path.basename(out_path),
        'confidence_score': confidence,
        'fps': fps,
        'clip_duration': round(t_end - t_start, 2),
        'landmark_positions': landmark_positions,
        'frame_landmarks': frame_landmarks,   # per-frame joint positions for canvas
    }


# ── helpers ───────────────────────────────────────────────────────────────

def _avg_landmark_positions(frame_data):
    """Return {joint_name: {x: float, y: float}} averaged over all detected frames."""
    sums = {name: [0.0, 0.0, 0] for name in LANDMARKS}
    for fd in frame_data:
        if fd['landmarks'] is None:
            continue
        for name, idx in LANDMARKS.items():
            lm = fd['landmarks'][idx]
            vis = getattr(lm, 'visibility', 1.0)
            if vis >= 0.4:
                sums[name][0] += lm.x
                sums[name][1] += lm.y
                sums[name][2] += 1
    out = {}
    for name, (sx, sy, cnt) in sums.items():
        if cnt > 0:
            out[name] = {'x': round(sx / cnt, 4), 'y': round(sy / cnt, 4)}
    return out


def _write_annotated_video(src_path, dst_path, frame_data,
                            fps, width, height,
                            start_frame, end_frame,
                            progress_callback):
    """Write a neutral grey-skeleton video — canvas handles all coloured dot logic."""
    lm_map      = {fd['frame_idx']: fd['landmarks'] for fd in frame_data}
    sorted_keys = sorted(lm_map)

    cap = cv2.VideoCapture(src_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    fourcc = cv2.VideoWriter_fourcc(*'avc1')
    out    = cv2.VideoWriter(dst_path, fourcc, fps, (width, height))
    if not out.isOpened():
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out    = cv2.VideoWriter(dst_path, fourcc, fps, (width, height))

    rel_idx    = 0
    clip_total = max(end_frame - start_frame, 1)

    while True:
        ret, frame = cap.read()
        if not ret or (start_frame + rel_idx) >= end_frame:
            break
        lm        = _nearest_landmarks(lm_map, sorted_keys, rel_idx)
        annotated = draw_skeleton_neutral(frame, lm)
        out.write(annotated)
        rel_idx += 1
        if progress_callback and rel_idx % 20 == 0:
            progress_callback(min(65 + int(rel_idx / clip_total * 30), 95))

    cap.release()
    out.release()


def _nearest_landmarks(lm_map, sorted_keys, target_idx):
    if not sorted_keys:
        return None
    closest = min(sorted_keys, key=lambda k: abs(k - target_idx))
    return lm_map[closest] if abs(closest - target_idx) <= SAMPLE_EVERY + 1 else None


def _smooth_frame_landmarks(frame_landmarks, window=5):
    """
    Apply a temporal box-filter to joint positions to remove MediaPipe jitter.
    Each frame's joint position is replaced by the average of the surrounding
    `window` frames — making the skeleton visibly smoother during playback.
    """
    n = len(frame_landmarks)
    if n < 3:
        return frame_landmarks

    half = window // 2
    out  = []

    for i, fl in enumerate(frame_landmarks):
        start  = max(0, i - half)
        end    = min(n, i + half + 1)
        bucket = frame_landmarks[start:end]

        # Collect all joint names visible in this window
        all_names = set()
        for bf in bucket:
            all_names.update(bf['j'].keys())

        joints = {}
        for jname in all_names:
            xs = [bf['j'][jname][0] for bf in bucket if jname in bf['j']]
            ys = [bf['j'][jname][1] for bf in bucket if jname in bf['j']]
            if xs:
                joints[jname] = [
                    round(sum(xs) / len(xs), 4),
                    round(sum(ys) / len(ys), 4),
                ]

        out.append({'t': fl['t'], 'j': joints})

    return out
