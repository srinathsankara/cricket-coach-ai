import numpy as np
from .pose_detector import calculate_angle, landmark_xy, landmark_visible


def analyze_bowling(frame_data, handedness='right'):
    if not frame_data:
        return []
    return [
        _front_knee(frame_data, handedness),
        _bowling_arm_height(frame_data, handedness),
        _guide_arm(frame_data, handedness),
        _shoulder_turn(frame_data, handedness),
        _head_position(frame_data),
        _follow_through(frame_data),
    ]


def _checkpoint(name, status, emoji, message,
                what_wrong='', why_matters='', how_to_fix='', drill='',
                issue_frame_idx=0,
                problem=(), good=(),
                angle_joints=None,   # [joint_arm1, joint_vertex, joint_arm2] for arc
                canvas_label=''):    # short text shown directly on the video frame
    return {
        'name': name, 'status': status, 'emoji': emoji, 'message': message,
        'what_wrong': what_wrong, 'why_matters': why_matters,
        'how_to_fix': how_to_fix, 'drill': drill,
        'issue_frame_idx': issue_frame_idx,
        'problem_joints': list(problem), 'good_joints': list(good),
        'angle_joints': list(angle_joints) if angle_joints else [],
        'canvas_label': canvas_label,
    }


def _unknown(name):
    return _checkpoint(name, 'unknown', '❓',
                       'Could not detect clearly — make sure your full body stays in frame.')


def _front(handedness):
    return ('left_hip', 'left_knee', 'left_ankle') if handedness == 'right' \
        else ('right_hip', 'right_knee', 'right_ankle')


def _bowl_side(handedness):
    return ('right_shoulder', 'right_elbow', 'right_wrist') if handedness == 'right' \
        else ('left_shoulder', 'left_elbow', 'left_wrist')


def _guide_side(handedness):
    return ('left_shoulder', 'left_elbow', 'left_wrist') if handedness == 'right' \
        else ('right_shoulder', 'right_elbow', 'right_wrist')


def _front_knee(frames, handedness):
    hip_n, knee_n, ankle_n = _front(handedness)
    min_angle = 180.0
    min_frame_idx = 0
    for i, fd in enumerate(frames):
        lm = fd['landmarks']
        if lm is None:
            continue
        w, h = fd['w'], fd['h']
        try:
            angle = calculate_angle(
                landmark_xy(lm, hip_n, w, h),
                landmark_xy(lm, knee_n, w, h),
                landmark_xy(lm, ankle_n, w, h))
            if angle < min_angle:
                min_angle = angle
                min_frame_idx = i   # frame where knee is most bent (worst moment)
        except Exception:
            continue

    if min_angle == 180.0:
        return _unknown('Front Knee Brace')

    if min_angle >= 155:
        return _checkpoint('Front Knee Brace', 'good', '✅',
                           "Great front leg brace — nice and straight at landing!",
                           issue_frame_idx=min_frame_idx, good=(knee_n,))
    if min_angle >= 130:
        return _checkpoint(
            'Front Knee Brace', 'improve', '⚠️', "Front knee bending too much at landing.",
            what_wrong=f"Front knee bends to ≈{int(min_angle)}° at landing. Ideal is 155–175°.",
            why_matters="A bent front knee absorbs energy — power leaks out instead of going into the ball.",
            how_to_fix="As your front foot plants, drive your front knee toward straight. Heel plants first.",
            drill=("DRILL — The Stamp: Practise delivery stride in slow motion, focusing on planting your "
                   "heel hard and straightening the knee. 20 slow-motion strides per session."),
            issue_frame_idx=min_frame_idx, problem=(knee_n,),
            angle_joints=(hip_n, knee_n, ankle_n),
            canvas_label=f"Front knee: {int(min_angle)}° — too BENT at landing (needs 155–175°)")
    return _checkpoint(
        'Front Knee Brace', 'fix', '❌', "Front knee collapsing badly — major power loss.",
        what_wrong=f"Front knee bends sharply to ≈{int(min_angle)}° — far below the 155° minimum.",
        why_matters=("A collapsed front knee is the single biggest cause of slow, weak bowling. "
                     "Also puts serious stress on your back and knee joints."),
        how_to_fix=("Start with very slow deliveries — walking pace — concentrating entirely on landing "
                    "with a straight front leg. Say 'BRACE' out loud as your front foot hits the ground."),
        drill=("DRILL — Wall Brace: Stand side-on to a wall, front leg touching it. Go through delivery "
               "slowly — at landing your front knee should press gently into the wall. 15 reps per session."),
        issue_frame_idx=min_frame_idx, problem=(knee_n,),
        angle_joints=(hip_n, knee_n, ankle_n),
        canvas_label=f"Front knee: {int(min_angle)}° — COLLAPSING at landing (needs 155–175°)")


def _bowling_arm_height(frames, handedness):
    _, _, wrist_n = _bowl_side(handedness)
    sh_n = 'right_shoulder' if handedness == 'right' else 'left_shoulder'
    best = -999.0
    best_frame_idx = 0
    for i, fd in enumerate(frames):
        lm = fd['landmarks']
        if lm is None:
            continue
        w, h = fd['w'], fd['h']
        try:
            nose  = landmark_xy(lm, 'nose', w, h)
            wrist = landmark_xy(lm, wrist_n, w, h)
            sh    = landmark_xy(lm, sh_n, w, h)
            arm_len = abs(sh[1] - wrist[1]) or 1
            ratio = (nose[1] - wrist[1]) / arm_len
            if ratio > best:
                best = ratio
                best_frame_idx = i   # frame of highest arm
        except Exception:
            continue

    if best == -999.0:
        return _unknown('Bowling Arm Height')

    if best >= 0.3:
        return _checkpoint('Bowling Arm Height', 'good', '✅',
                           "Excellent arm height — bowling arm gets nice and high!",
                           issue_frame_idx=best_frame_idx, good=(wrist_n,))
    if best >= 0.0:
        return _checkpoint(
            'Bowling Arm Height', 'improve', '⚠️', "Bowling arm not quite high enough.",
            what_wrong="Your bowling arm reaches head height but not clearly above the head at the peak.",
            why_matters="A lower arm release means less pace and flatter trajectory — less bounce from pitch.",
            how_to_fix="At front foot landing, drive the bowling arm upward. 'Reach for the sky' at release.",
            drill=("DRILL — Target on Wall: Tape paper high on a wall. Practise arm action touching the paper "
                   "with your wrist at the top. Move the paper higher over weeks. 20 reps per session."),
            issue_frame_idx=best_frame_idx, problem=(wrist_n,),
            canvas_label="Bowling arm reaching head height — needs to go HIGHER!")
    return _checkpoint(
        'Bowling Arm Height', 'fix', '❌', "Bowling arm too low — staying below head level.",
        what_wrong="The bowling arm doesn't get above head height. Round-arm or slingy action detected.",
        why_matters=("A low arm removes natural advantages: bounce, seam movement, pace. Also increases "
                     "risk of being called for illegal action at higher levels."),
        how_to_fix=("Start from scratch with arm circles — large vertical circles like a windmill. "
                    "Arm must go directly above your head. Add footwork only once arm circle is naturally vertical."),
        drill=("DRILL — Windmill Warmup: 30 large arm circles per session, focusing on full overhead reach. "
               "Then bowl 10 balls from 2m (very short run-up), concentrating only on arm height."),
        issue_frame_idx=best_frame_idx, problem=(wrist_n,),
        canvas_label="Bowling arm BELOW head level — round-arm action!")


def _guide_arm(frames, handedness):
    _, elbow_n, wrist_n = _guide_side(handedness)
    sh_n = 'left_shoulder' if handedness == 'right' else 'right_shoulder'
    best = 0.0
    best_frame_idx = 0
    for i, fd in enumerate(frames):
        lm = fd['landmarks']
        if lm is None:
            continue
        w, h = fd['w'], fd['h']
        try:
            angle = calculate_angle(
                landmark_xy(lm, sh_n, w, h),
                landmark_xy(lm, elbow_n, w, h),
                landmark_xy(lm, wrist_n, w, h))
            if angle > best:
                best = angle
                best_frame_idx = i
        except Exception:
            continue

    if best == 0.0:
        return _unknown('Guide Arm')

    if best >= 150:
        return _checkpoint('Guide Arm', 'good', '✅',
                           "Excellent guide arm — pointing at the target perfectly!",
                           issue_frame_idx=best_frame_idx, good=(wrist_n,))
    if best >= 120:
        return _checkpoint(
            'Guide Arm', 'improve', '⚠️', "Guide arm not fully extended — stretch it out more.",
            what_wrong=f"Your non-bowling arm reaches ≈{int(best)}° at its straightest. Should be 160°+.",
            why_matters="The guide arm is your aiming device. Without it fully extended, deliveries are inconsistent.",
            how_to_fix=("Raise your non-bowling arm and point it straight at the batter — like pointing a finger. "
                        "Keep it up until the bowling arm comes over, then pull it sharply down into your hip."),
            drill=("DRILL — Point and Pull: Mark a spot on a wall at batter height. Practise your delivery "
                   "slowly, fully extending guide arm toward the spot, then pulling down fast. 20 reps."),
            issue_frame_idx=best_frame_idx, problem=(wrist_n,),
            angle_joints=(sh_n, elbow_n, wrist_n),
            canvas_label=f"Guide arm: {int(best)}° — not extended enough (needs 160°+)")
    return _checkpoint(
        'Guide Arm', 'fix', '❌', "Guide arm barely used — major accuracy problem.",
        what_wrong="Non-bowling arm staying close to the body and barely extending at all.",
        why_matters=("No guide arm means no aiming reference. Also causes extra back stress. "
                     "Results in wild, inconsistent deliveries."),
        how_to_fix=("For one week, bowl from standing start only. Focus only on: 1) Point guide arm at batter, "
                    "2) Bowling arm comes over, 3) Pull guide arm sharply into hip. Build the 3-step rhythm."),
        drill=("DRILL — Chest Pass Drill: Chest-pass a ball to a partner using both hands, "
               "then quickly point your non-dominant arm at them. 20 times, then apply to bowling."),
        issue_frame_idx=best_frame_idx, problem=(wrist_n,),
        angle_joints=(sh_n, elbow_n, wrist_n),
        canvas_label=f"Guide arm: {int(best)}° — barely extended (needs 160°+)")


def _shoulder_turn(frames, handedness):
    best = 0.0
    best_frame_idx = 0
    for i, fd in enumerate(frames):
        lm = fd['landmarks']
        if lm is None:
            continue
        w, h = fd['w'], fd['h']
        try:
            ls = landmark_xy(lm, 'left_shoulder', w, h)
            rs = landmark_xy(lm, 'right_shoulder', w, h)
            dx = abs(ls[0] - rs[0])
            dy = abs(ls[1] - rs[1])
            ratio = dy / (dx + 1)
            if ratio > best:
                best = ratio
                best_frame_idx = i
        except Exception:
            continue

    if best == 0.0:
        return _unknown('Shoulder Turn')

    if best >= 0.5:
        return _checkpoint('Shoulder Turn', 'good', '✅',
                           "Excellent shoulder turn — great side-on position!",
                           issue_frame_idx=best_frame_idx, good=('left_shoulder', 'right_shoulder'))
    if best >= 0.2:
        return _checkpoint(
            'Shoulder Turn', 'improve', '⚠️', "Shoulders not quite side-on enough — turn more.",
            what_wrong="Shoulders partially turned but not reaching ideal side-on position before delivery.",
            why_matters="Not fully side-on reduces rotation available — costs pace and strains the lower back.",
            how_to_fix="At the top of your bound, think 'show your back to the batter'. Lead shoulder points down pitch.",
            drill=("DRILL — The Side-On Check: Mark a spot on a wall where your lead shoulder should point. "
                   "Practise your bound and check the shoulder reaches the mark. 15 jumps per session."),
            issue_frame_idx=best_frame_idx, problem=('left_shoulder', 'right_shoulder'),
            canvas_label="Not fully side-on — shoulders need to turn more!")
    return _checkpoint(
        'Shoulder Turn', 'fix', '❌', "Chest-on action — barely turning sideways at all.",
        what_wrong="Shoulders remaining almost square-on (facing the batter) throughout delivery.",
        why_matters=("Chest-on action is a leading cause of back injury. Spine is forced to twist under load. "
                     "Also severely limits pace, swing, and seam movement."),
        how_to_fix=("Go back to basics: slow-walk through your action and exaggerate the shoulder turn — "
                    "so much it almost feels like you're facing the wrong way at the top."),
        drill=("DRILL — Sideways Walk-Through: Walk through delivery 10 times per session. At the top, stop "
               "completely and have someone check your lead shoulder points at the batter. Say 'SIDEWAYS' out loud."),
        issue_frame_idx=best_frame_idx, problem=('left_shoulder', 'right_shoulder'),
        canvas_label="CHEST-ON action — barely side-on at all! Causes back injury.")


def _head_position(frames):
    tilts = []
    first_issue_idx = 0
    found_issue = False
    for i, fd in enumerate(frames):
        lm = fd['landmarks']
        if lm is None:
            continue
        w, h = fd['w'], fd['h']
        try:
            nose = landmark_xy(lm, 'nose', w, h)
            ls   = landmark_xy(lm, 'left_shoulder', w, h)
            rs   = landmark_xy(lm, 'right_shoulder', w, h)
            mid  = [(ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2]
            dy   = mid[1] - nose[1]
            if dy > 10:
                tilt = np.degrees(np.arctan2(abs(nose[0] - mid[0]), dy))
                tilts.append(tilt)
                if not found_issue and tilt > 15:
                    first_issue_idx = i
                    found_issue = True
        except Exception:
            continue

    if not tilts:
        return _unknown('Head Position')

    t = float(np.mean(tilts))

    if t <= 15:
        return _checkpoint('Head Position', 'good', '✅',
                           "Head upright and looking straight at the batter — perfect!",
                           issue_frame_idx=0, good=('nose',))
    return _checkpoint(
        'Head Position', 'fix', '❌', "Head tilting away during delivery — keep it upright.",
        what_wrong=f"Head tilting ≈{int(t)}° from vertical during delivery. Should stay upright.",
        why_matters=("A tilting head causes the entire body to go off-line. Hips follow the head, "
                     "pulling delivery direction sideways — common cause of wide deliveries."),
        how_to_fix=("Fix a spot — the top of the far stumps — and keep your eyes on it throughout "
                    "run-up and delivery. Head stays upright until AFTER ball is released."),
        drill=("DRILL — Stump Stare: Put a coloured sticker on the top of far stumps. Keep eyes fixed on it "
               "from start of run-up until follow-through. Someone watches if your head tilts. 15 deliveries per session."),
        issue_frame_idx=first_issue_idx, problem=('nose',),
        canvas_label=f"Head tilt: {int(t)}° (keep under 15°) — causing wides!")


def _follow_through(frames):
    tail_start_idx = max(0, int(len(frames) * 0.6))
    tail = frames[tail_start_idx:]
    positions = []
    for fd in tail:
        lm = fd['landmarks']
        if lm is None:
            continue
        w, h = fd['w'], fd['h']
        try:
            lhip = landmark_xy(lm, 'left_hip', w, h)
            rhip = landmark_xy(lm, 'right_hip', w, h)
            positions.append((lhip[0] + rhip[0]) / 2)
        except Exception:
            continue

    if len(positions) < 3:
        return _unknown('Follow-Through')

    frame_w  = frames[0]['w'] if frames else 1
    movement = abs(positions[-1] - positions[0]) / frame_w

    if movement >= 0.05:
        return _checkpoint('Follow-Through', 'good', '✅',
                           "Excellent follow-through — running through properly after delivery!",
                           issue_frame_idx=tail_start_idx, good=('left_hip', 'right_hip'))
    return _checkpoint(
        'Follow-Through', 'fix', '❌', "Stopping after bowling — must run through.",
        what_wrong="Body stops or barely moves forward after the ball is released.",
        why_matters=("Stopping suddenly puts enormous stress on the lower back, knees and ankles — "
                     "the leading cause of fast bowling injuries. Also reduces final pace."),
        how_to_fix=("After you release, keep running! Bowling arm sweeps down and across. "
                    "Take at least 3 full strides down the pitch after delivery."),
        drill=("DRILL — Cone Run-Through: Place a cone 4 metres past the crease. Goal every delivery: "
               "run PAST the cone before slowing down. If you stop before it, that delivery doesn't count."),
        issue_frame_idx=tail_start_idx, problem=('left_hip', 'right_hip'),
        canvas_label="Stopping dead after bowling — run through the crease!")
