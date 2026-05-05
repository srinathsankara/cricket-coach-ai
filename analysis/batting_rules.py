import numpy as np
from .pose_detector import calculate_angle, landmark_xy, landmark_visible


def analyze_batting(frame_data, handedness='right'):
    if not frame_data:
        return []
    return [
        _stance_width(frame_data),
        _knee_bend(frame_data, handedness),
        _backlift(frame_data),
        _follow_through(frame_data),
        _head_position(frame_data),
        _balance(frame_data),
    ]


# ── helpers ────────────────────────────────────────────────────────────────

def _checkpoint(name, status, emoji, message,
                what_wrong='', why_matters='', how_to_fix='', drill='',
                issue_frame_idx=0,
                problem=(), good=(),
                angle_joints=None,   # [joint_arm1, joint_vertex, joint_arm2] for arc drawing
                canvas_label=''):    # short text shown directly on the video frame
    return {
        'name': name,
        'status': status,
        'emoji': emoji,
        'message': message,
        'what_wrong': what_wrong,
        'why_matters': why_matters,
        'how_to_fix': how_to_fix,
        'drill': drill,
        'issue_frame_idx': issue_frame_idx,
        'problem_joints': list(problem),
        'good_joints': list(good),
        'angle_joints': list(angle_joints) if angle_joints else [],
        'canvas_label': canvas_label,
    }


def _unknown(name):
    return _checkpoint(name, 'unknown', '❓',
                       'Could not detect clearly — make sure your full body stays in frame.')


# ── individual checks ──────────────────────────────────────────────────────

def _stance_width(frames):
    ratios = []
    worst_idx = 0
    worst_deviation = -1.0
    for i, fd in enumerate(frames[:15]):
        lm = fd['landmarks']
        if lm is None:
            continue
        w, h = fd['w'], fd['h']
        try:
            ls = landmark_xy(lm, 'left_shoulder', w, h)
            rs = landmark_xy(lm, 'right_shoulder', w, h)
            la = landmark_xy(lm, 'left_ankle', w, h)
            ra = landmark_xy(lm, 'right_ankle', w, h)
            sw = abs(ls[0] - rs[0])
            fw = abs(la[0] - ra[0])
            if sw > 10:
                ratio = fw / sw
                ratios.append(ratio)
                # Worst frame = furthest from ideal range (0.9–1.4)
                deviation = max(0.9 - ratio, ratio - 1.4, 0)
                if deviation > worst_deviation:
                    worst_deviation = deviation
                    worst_idx = i
        except Exception:
            continue

    if not ratios:
        return _unknown('Stance Width')

    r = float(np.mean(ratios))

    if 0.9 <= r <= 1.4:
        return _checkpoint('Stance Width', 'good', '✅',
                           "Great stance! Feet in a perfect shoulder-width position.",
                           issue_frame_idx=worst_idx, good=('left_ankle', 'right_ankle'))
    if r < 0.9:
        return _checkpoint(
            'Stance Width', 'fix', '❌', "Feet too close together — widen your stance.",
            what_wrong=("Your feet are narrower than your shoulders. The AI detected your ankle gap "
                        "is less than 90% of your shoulder width, which makes you unstable."),
            why_matters=("A narrow stance makes it hard to shift weight, limits power in your shots, "
                         "and reduces balance when the ball is wide or full."),
            how_to_fix=("Stand with feet directly below your shoulders (or slightly wider). "
                        "Feel your weight balanced evenly — like you're ready to jump."),
            drill=("DRILL — The Tape Test: Put two strips of tape on the ground shoulder-width apart. "
                   "Practise standing with one foot on each strip. Do 20 shadow-bat swings daily."),
            issue_frame_idx=worst_idx, problem=('left_ankle', 'right_ankle'),
            canvas_label=f"Feet too NARROW — {int(r*100)}% of shoulder width (needs 90–140%)")
    return _checkpoint(
        'Stance Width', 'improve', '⚠️', "Feet a little too wide — bring them slightly closer.",
        what_wrong="Your feet are spread wider than 1.4× your shoulder width.",
        why_matters="An overly wide stance locks your hips and stops you from moving freely to the ball.",
        how_to_fix="Bring your feet in slightly — just at or a touch outside shoulder width.",
        drill=("DRILL — Step and Play: Practise taking one big forward step from your stance. "
               "If you feel cramped, your stance is too wide."),
        issue_frame_idx=worst_idx, problem=('left_ankle', 'right_ankle'),
        canvas_label=f"Feet too WIDE — {int(r*100)}% of shoulder width (needs 90–140%)")


def _knee_bend(frames, handedness='right'):
    front_hip   = 'left_hip'   if handedness == 'right' else 'right_hip'
    front_knee  = 'left_knee'  if handedness == 'right' else 'right_knee'
    front_ankle = 'left_ankle' if handedness == 'right' else 'right_ankle'
    angles = []
    worst_idx = 0
    worst_deviation = -1.0
    for i, fd in enumerate(frames[:15]):
        lm = fd['landmarks']
        if lm is None:
            continue
        w, h = fd['w'], fd['h']
        try:
            lh = landmark_xy(lm, 'left_hip', w, h)
            lk = landmark_xy(lm, 'left_knee', w, h)
            la = landmark_xy(lm, 'left_ankle', w, h)
            rh = landmark_xy(lm, 'right_hip', w, h)
            rk = landmark_xy(lm, 'right_knee', w, h)
            ra = landmark_xy(lm, 'right_ankle', w, h)
            angle = (calculate_angle(lh, lk, la) + calculate_angle(rh, rk, ra)) / 2
            angles.append(angle)
            # Worst = furthest from ideal (140–165)
            deviation = max(140 - angle, angle - 165, 0)
            if deviation > worst_deviation:
                worst_deviation = deviation
                worst_idx = i
        except Exception:
            continue

    if not angles:
        return _unknown('Knee Bend')

    a = float(np.mean(angles))

    if 140 <= a <= 165:
        return _checkpoint('Knee Bend', 'good', '✅',
                           "Perfect knee bend — relaxed, athletic and ready to move!",
                           issue_frame_idx=worst_idx, good=('left_knee', 'right_knee'))
    if a > 165:
        return _checkpoint(
            'Knee Bend', 'fix', '❌', "Knees too straight — bend them more.",
            what_wrong=f"Your knee angle is approximately {int(a)}°. A good stance needs ~150–165°.",
            why_matters="Straight legs make you slow to react and stiff through the shot.",
            how_to_fix="Imagine sitting on a tall stool — let the knees flex gently. Weight on balls of feet.",
            drill=("DRILL — The Bounce Test: Have someone push your shoulder gently. If you wobble a lot, "
                   "your knees are too straight. Bend until a push barely moves you."),
            issue_frame_idx=worst_idx, problem=('left_knee', 'right_knee'),
            angle_joints=(front_hip, front_knee, front_ankle),
            canvas_label=f"Knee: {int(a)}° — too STRAIGHT (needs 150–165°)")
    return _checkpoint(
        'Knee Bend', 'improve', '⚠️', "Crouching too low — straighten up just a little.",
        what_wrong=f"Your knee angle is around {int(a)}°, bending too deeply. Ideal is 150–165°.",
        why_matters="Too much knee bend restricts hip rotation and shortens your reach.",
        how_to_fix="Rise up slightly. Think 'tall but relaxed'. Spine fairly upright, knees just gently bent.",
        drill="DRILL — Mirror Check: Stand in front of a mirror. Adjust until your knee bend looks natural.",
        issue_frame_idx=worst_idx, problem=('left_knee', 'right_knee'),
        angle_joints=(front_hip, front_knee, front_ankle),
        canvas_label=f"Knee: {int(a)}° — too BENT (needs 150–165°)")


def _backlift(frames):
    best = -999.0
    best_frame_idx = 0
    for i, fd in enumerate(frames):
        lm = fd['landmarks']
        if lm is None:
            continue
        w, h = fd['w'], fd['h']
        try:
            ls = landmark_xy(lm, 'left_shoulder', w, h)
            lhip = landmark_xy(lm, 'left_hip', w, h)
            lw = landmark_xy(lm, 'left_wrist', w, h)
            rw = landmark_xy(lm, 'right_wrist', w, h)
            sh_y = (ls[1] + lhip[1]) / 2
            torso = abs(ls[1] - lhip[1]) or 1
            top_wrist_y = min(lw[1], rw[1])
            ratio = (sh_y - top_wrist_y) / torso
            if ratio > best:
                best = ratio
                best_frame_idx = i   # frame of peak backlift
        except Exception:
            continue

    if best == -999.0:
        return _unknown('Backlift')

    if best >= 0.5:
        return _checkpoint('Backlift', 'good', '✅',
                           "Excellent backlift! Bat gets up nice and high — great power position.",
                           issue_frame_idx=best_frame_idx, good=('left_wrist', 'right_wrist'))
    if best >= 0.15:
        return _checkpoint(
            'Backlift', 'improve', '⚠️', "Backlift a bit low — hands need to go higher.",
            what_wrong="Your hands and bat are not reaching high enough in the backlift.",
            why_matters="A short backlift means less momentum — shots will lack power.",
            how_to_fix=("As the bowler runs in, lift your hands so the bat handle goes past your shoulder. "
                        "Don't rush the lift — smooth and early."),
            drill=("DRILL — Wall Tap: Stand arm's length from a wall. In your backlift, tap the wall "
                   "with the back of the bat above your head. Do 30 slow-motion reps per session."),
            issue_frame_idx=best_frame_idx, problem=('left_wrist', 'right_wrist'),
            canvas_label="Bat not reaching shoulder height — lift higher!")
    return _checkpoint(
        'Backlift', 'fix', '❌', "Backlift too low — bat barely leaving the ground.",
        what_wrong="The bat stays very low during the backlift — barely rising above waist height.",
        why_matters="With almost no backlift there is almost no power. Even a slow bowler will get you out easily.",
        how_to_fix=("Think of the backlift as a key that unlocks your power. Before every delivery, "
                    "LIFT your hands up toward your right ear. The bat face should point to the sky at the top."),
        drill=("DRILL — Slow Motion Swings: 20 very slow swings per day. Pause at the top each time "
               "and check your hands are above shoulder height. Say 'UP... DOWN' to build rhythm."),
        issue_frame_idx=best_frame_idx, problem=('left_wrist', 'right_wrist'),
        canvas_label="Bat barely leaving the ground — no backlift!")


def _follow_through(frames):
    tail_start_idx = max(0, int(len(frames) * 0.65))
    tail = frames[tail_start_idx:]
    best = -999.0
    best_frame_idx = tail_start_idx   # follow-through starts at 65% of clip
    for i, fd in enumerate(tail):
        lm = fd['landmarks']
        if lm is None:
            continue
        w, h = fd['w'], fd['h']
        try:
            ls = landmark_xy(lm, 'left_shoulder', w, h)
            lhip = landmark_xy(lm, 'left_hip', w, h)
            lw = landmark_xy(lm, 'left_wrist', w, h)
            rw = landmark_xy(lm, 'right_wrist', w, h)
            torso = abs(ls[1] - lhip[1]) or 1
            top_wrist_y = min(lw[1], rw[1])
            ratio = (ls[1] - top_wrist_y) / torso
            if ratio > best:
                best = ratio
        except Exception:
            continue

    if best == -999.0:
        return _unknown('Follow-Through')

    if best >= 0.5:
        return _checkpoint('Follow-Through', 'good', '✅',
                           "Beautiful follow-through — bat swings all the way through like a pro!",
                           issue_frame_idx=tail_start_idx, good=('left_wrist', 'right_wrist'))
    if best >= 0.1:
        return _checkpoint(
            'Follow-Through', 'improve', '⚠️', "Follow-through stopping too early.",
            what_wrong="The bat stops just after contact instead of continuing upward past shoulder height.",
            why_matters="Stopping the bat early means you decelerate before impact — costs power and control.",
            how_to_fix=("After hitting, keep your arms going — bat finishes above your front shoulder. "
                        "Think 'hit to the sky' not 'hit to the ground'."),
            drill=("DRILL — High Finish Challenge: Mark a spot above your shoulder on a wall. "
                   "Every swing must end with the bat touching or passing that mark. 25 swings daily."),
            issue_frame_idx=tail_start_idx, problem=('left_wrist', 'right_wrist'),
            canvas_label="Bat stopping too early — follow through higher!")
    return _checkpoint(
        'Follow-Through', 'fix', '❌', "No follow-through — bat stopping dead at contact.",
        what_wrong="The bat comes to a near-complete stop at or immediately after the point of contact.",
        why_matters=("This is one of the biggest power leaks in batting. Stopping the bat slows it BEFORE impact. "
                     "The result is weak, mistimed shots."),
        how_to_fix=("Imagine the ball is NOT the target — pretend there's a second ball 30 cm behind the "
                    "first one, and you're trying to hit THAT one. Bat finishes pointing at the sky."),
        drill=("DRILL — The Pendulum: Hang a ball in a sock from a string. Hit it softly and focus ONLY "
               "on where the bat ends up after contact — it must finish high. 30 swings daily."),
        issue_frame_idx=tail_start_idx, problem=('left_wrist', 'right_wrist'),
        canvas_label="Bat stopping dead at contact — no follow-through!")


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
            ls = landmark_xy(lm, 'left_shoulder', w, h)
            rs = landmark_xy(lm, 'right_shoulder', w, h)
            mid = [(ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2]
            dy = mid[1] - nose[1]
            if dy > 10:
                tilt = np.degrees(np.arctan2(abs(nose[0] - mid[0]), dy))
                tilts.append(tilt)
                # Record first frame where head tilt exceeds threshold
                if not found_issue and tilt > 12:
                    first_issue_idx = i
                    found_issue = True
        except Exception:
            continue

    if not tilts:
        return _unknown('Head Position')

    t = float(np.mean(tilts))

    if t <= 12:
        return _checkpoint('Head Position', 'good', '✅',
                           "Head still and level — eyes perfectly focused on the ball!",
                           issue_frame_idx=0, good=('nose',))
    if t <= 22:
        return _checkpoint(
            'Head Position', 'improve', '⚠️', "Head tilting slightly — keep it steadier.",
            what_wrong=f"Your head tilts approximately {int(t)}° to the side on average. Ideal is under 12°.",
            why_matters=("When your head tilts, your eyes are no longer level. This distorts depth perception "
                         "and causes mistimed shots and edges."),
            how_to_fix=("Keep your chin pointing at your front shoulder as you watch the ball. "
                        "Eyes should stay level — like a camera on a tripod."),
            drill=("DRILL — Book Balance: Place a small flat book on your head in your batting stance. "
                   "Shadow-bat slowly without the book falling. Any tilt drops it immediately. 5 minutes daily."),
            issue_frame_idx=first_issue_idx, problem=('nose',),
            canvas_label=f"Head tilt: {int(t)}° (keep under 12°) — eyes not level!")
    return _checkpoint(
        'Head Position', 'fix', '❌', "Head moving too much — keep it still and eyes level.",
        what_wrong=f"Your head tilts significantly (≈{int(t)}° average). This strongly affects ball tracking.",
        why_matters=("The head is the heaviest part of the body. When it moves, the whole body follows. "
                     "Leads to missed shots, thick edges, and being bowled far more often."),
        how_to_fix=("Pick a spot to focus on (the bowler's hand). Track the ball with your eyes ONLY — "
                    "your head should barely move. Think: fixed CCTV camera, only the lens moves."),
        drill=("DRILL — Eyes Only Tracking: Someone rolls a ball slowly toward you. Track with eyes ONLY — "
               "hold your head still with both hands lightly at your temples to feel any movement. 10 reps per session."),
        issue_frame_idx=first_issue_idx, problem=('nose',),
        canvas_label=f"Head tilt: {int(t)}° (keep under 12°) — head moving too much!")


def _balance(frames):
    tail_start_idx = max(0, int(len(frames) * 0.65))
    tail = frames[tail_start_idx:]
    tilts = []
    first_issue_idx = tail_start_idx
    found_issue = False
    for i, fd in enumerate(tail):
        lm = fd['landmarks']
        if lm is None:
            continue
        w, h = fd['w'], fd['h']
        try:
            ls = landmark_xy(lm, 'left_shoulder', w, h)
            rs = landmark_xy(lm, 'right_shoulder', w, h)
            lhip = landmark_xy(lm, 'left_hip', w, h)
            rhip = landmark_xy(lm, 'right_hip', w, h)
            mid_sh = [(ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2]
            mid_hp = [(lhip[0] + rhip[0]) / 2, (lhip[1] + rhip[1]) / 2]
            dy = mid_hp[1] - mid_sh[1]
            if dy > 10:
                tilt = np.degrees(np.arctan2(abs(mid_sh[0] - mid_hp[0]), dy))
                tilts.append(tilt)
                if not found_issue and tilt > 12:
                    first_issue_idx = tail_start_idx + i
                    found_issue = True
        except Exception:
            continue

    if not tilts:
        return _unknown('Balance')

    t = float(np.mean(tilts))

    if t <= 12:
        return _checkpoint('Balance', 'good', '✅',
                           "Great balance — staying upright and controlled through the shot!",
                           issue_frame_idx=tail_start_idx, good=('left_hip', 'right_hip'))
    if t <= 22:
        return _checkpoint(
            'Balance', 'improve', '⚠️', "Leaning to the side a bit — stay more upright.",
            what_wrong=f"Your spine tilts approximately {int(t)}° laterally during and after the shot.",
            why_matters="When you lean sideways, your weight shifts to the wrong foot — reduces power.",
            how_to_fix=("Imagine a vertical pole through the top of your head to the ground. "
                        "During every shot, keep your spine along that pole."),
            drill=("DRILL — Wall Spine Drill: Stand with your back lightly against a wall. "
                   "Your head and upper back should stay near the wall throughout the swing."),
            issue_frame_idx=first_issue_idx, problem=('left_hip', 'right_hip'),
            canvas_label=f"Body lean: {int(t)}° sideways (keep under 12°) — stay upright!")
    return _checkpoint(
        'Balance', 'fix', '❌', "Falling sideways significantly — losing balance on the shot.",
        what_wrong=f"The spine tilts approximately {int(t)}°. Upper body clearly collapsing sideways.",
        why_matters=("All your power goes sideways instead of into the ball. Also highly vulnerable "
                     "to being caught at square leg or bowled around your legs."),
        how_to_fix=("Keep your head over the ball. Keep your front leg firm as an anchor. "
                    "Think: 'Head over ball, weight on front foot.'"),
        drill=("DRILL — One-Legged Finish: After every shot, freeze and try to balance on your front leg "
               "for 3 seconds. If you topple, you lost balance. Practice until you hold it 10 times in a row."),
        issue_frame_idx=first_issue_idx,
        problem=('left_hip', 'right_hip', 'left_shoulder', 'right_shoulder'),
        canvas_label=f"Body lean: {int(t)}° sideways (keep under 12°) — falling over!")
