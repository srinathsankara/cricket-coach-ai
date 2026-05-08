/* =========================================================
   Cricket Coach AI — Smart Coaching Viewer  (v5)

   UX flow when "Watch This" is clicked:
   1. A large red dot IMMEDIATELY starts tracking the problem joint
      across the whole video so the user always knows what to watch.
   2. Video plays from ~2.5 s before the issue (context run-up).
   3. At the exact issue moment the video AUTO-PAUSES.
   4. Canvas overlay shows angle arc + big label badge + focus ring.
   5. "▶ Continue in slow-mo" button resumes at 0.25×.
   6. Fading orange trail follows the joint through the motion.
   ========================================================= */

const video  = document.getElementById('coaching-video');
const canvas = document.getElementById('annotation-canvas');
const ctx    = canvas.getContext('2d');

// ── State ─────────────────────────────────────────────────────────────────
let currentSpeed         = 1;
let loopEnabled          = true;
let zoomLevel            = 1;
let zoomOriginX          = 50;
let zoomOriginY          = 50;
let animHandle           = null;
let activeIssueIdx       = -1;
let activeJointPositions = {};
let trailPositions       = [];
const TRAIL_MAX          = 18;
let autoPaused           = false;

// Watch-All state
let watchAllActive  = false;
let watchAllOrder   = [];   // TOP_ISSUES indices sorted by issue_start_sec
let watchAllCurrent = 0;    // pointer into watchAllOrder

// Pulse state for the tracking dot
let pulse = { r: 18, growing: true };

// ── Skeleton connections (mirrors Python's DRAW_CONNECTIONS) ─────────────
const SKELETON_CONNECTIONS = [
  ['left_shoulder',  'right_shoulder'],
  ['left_shoulder',  'left_elbow'],
  ['left_elbow',     'left_wrist'],
  ['right_shoulder', 'right_elbow'],
  ['right_elbow',    'right_wrist'],
  ['left_shoulder',  'left_hip'],
  ['right_shoulder', 'right_hip'],
  ['left_hip',       'right_hip'],
  ['left_hip',       'left_knee'],
  ['left_knee',      'left_ankle'],
  ['right_hip',      'right_knee'],
  ['right_knee',     'right_ankle'],
];

// Shot phase definitions for batting (proportion of clip)
const BATTING_PHASES = [
  { label: 'Stance',        start: 0.00, end: 0.25, col: 'rgba(50,180,50,0.75)'   },
  { label: 'Backlift',      start: 0.25, end: 0.55, col: 'rgba(240,195,0,0.75)'  },
  { label: 'Downswing',     start: 0.55, end: 0.76, col: 'rgba(255,120,0,0.75)'  },
  { label: 'Impact',        start: 0.76, end: 0.85, col: 'rgba(215,25,25,0.85)'  },
  { label: 'Follow-Through',start: 0.85, end: 1.00, col: 'rgba(50,120,255,0.75)' },
];

// ── Joint zones — fallback y-positions and labels ─────────────────────────
const JOINT_ZONE = {
  nose:           { y: 0.10, label: 'Head' },
  left_shoulder:  { y: 0.25, label: 'Shoulder' },
  right_shoulder: { y: 0.25, label: 'Shoulder' },
  left_elbow:     { y: 0.38, label: 'Elbow' },
  right_elbow:    { y: 0.38, label: 'Elbow' },
  left_wrist:     { y: 0.30, label: 'Wrist / Bat' },
  right_wrist:    { y: 0.30, label: 'Wrist / Bat' },
  left_hip:       { y: 0.55, label: 'Hip' },
  right_hip:      { y: 0.55, label: 'Hip' },
  left_knee:      { y: 0.68, label: 'Knee' },
  right_knee:     { y: 0.68, label: 'Knee' },
  left_ankle:     { y: 0.82, label: 'Ankle' },
  right_ankle:    { y: 0.82, label: 'Ankle' },
};

// ── Init ──────────────────────────────────────────────────────────────────
video.addEventListener('loadedmetadata', () => {
  resizeCanvas();
  video.loop = loopEnabled;
  setSpeed(0.25);   // slow-mo by default
});

video.addEventListener('ended', () => {
  if (loopEnabled) {
    autoPaused = false;          // reset so the pause fires again on next loop
    video.currentTime = 0;
    video.play();
  }
});

video.addEventListener('play', () => {
  document.getElementById('play-from-here').classList.add('hidden');
});

window.addEventListener('resize', resizeCanvas);

function resizeCanvas() {
  const rect    = video.getBoundingClientRect();
  canvas.width  = rect.width  || video.offsetWidth;
  canvas.height = rect.height || video.offsetHeight;
}

// ── Frame sync: update live joint positions + auto-pause logic ────────────
video.addEventListener('timeupdate', () => {
  const t = video.currentTime;

  // ── Auto-pause at issue moment ────────────────────────────────────────
  // This block runs regardless of whether landmarks are available so the
  // pause always fires even when pose detection had low confidence.
  if (activeIssueIdx >= 0 && !autoPaused && !video.paused) {
    const issue    = TOP_ISSUES[activeIssueIdx];
    const rawSec   = issue?.issue_start_sec ?? 0;
    const issueSec = Math.max(rawSec, 1.0);   // always play at least 1 s first
    if (t >= issueSec) {
      autoPaused = true;
      video.pause();

      const tipEl = document.getElementById('continue-tip');
      if (tipEl) tipEl.textContent = `⏸ ${issue.name} — this is the exact moment it goes wrong`;

      // In watch-all mode show "Next Issue →", otherwise "Continue in slow-mo"
      _updateContinueButton();
      document.getElementById('play-from-here').classList.remove('hidden');
      showCallout(issue.name, issue.how_to_fix || issue.message);
    }
  }

  // ── Landmark sync — needs FRAME_LANDMARKS ────────────────────────────
  if (activeIssueIdx < 0 || !FRAME_LANDMARKS || !FRAME_LANDMARKS.length) return;

  let best = FRAME_LANDMARKS[0], bestDiff = Math.abs(best.t - t);
  for (let i = 1; i < FRAME_LANDMARKS.length; i++) {
    const d = Math.abs(FRAME_LANDMARKS[i].t - t);
    if (d < bestDiff) { bestDiff = d; best = FRAME_LANDMARKS[i]; }
  }
  activeJointPositions = best ? (best.j || {}) : {};

  // Accumulate trail only while playing and past issue start
  if (!video.paused) {
    const issue    = TOP_ISSUES[activeIssueIdx];
    const issueSec = issue?.issue_start_sec ?? 0;
    if (t >= issueSec) {
      const jName = issue?.problem_joints?.[0];
      if (jName && activeJointPositions[jName]) {
        const cw = canvas.width || video.offsetWidth;
        const ch = canvas.height || video.offsetHeight;
        trailPositions.push({
          x: activeJointPositions[jName][0] * cw,
          y: activeJointPositions[jName][1] * ch,
        });
        if (trailPositions.length > TRAIL_MAX) trailPositions.shift();
      }
    }
  }
});

// ── PUBLIC: called by "Watch This" buttons ────────────────────────────────
function watchIssue(idx, fromWatchAll = false) {
  const issue = TOP_ISSUES[idx];
  if (!issue) return;

  // If called from a card button directly, cancel any watch-all flow
  if (!fromWatchAll) {
    watchAllActive  = false;
    watchAllOrder   = [];
    watchAllCurrent = 0;
  }

  activeIssueIdx = idx;
  autoPaused     = false;
  trailPositions = [];
  pulse          = { r: 18, growing: true };

  document.querySelectorAll('.watch-btn').forEach((b, i) => {
    b.classList.toggle('watch-btn-active', i === idx);
  });

  applyZoomToJoint(issue.problem_joints?.[0] || null);

  document.getElementById('play-from-here').classList.add('hidden');
  hideCallout();

  document.getElementById('now-watching').classList.remove('hidden');
  document.getElementById('nw-label').textContent = issue.name;

  // Always start from the very beginning so the user sees the full action.
  // The red dot will track the joint from frame 0, then the video
  // auto-pauses the moment the issue frame is reached.
  video.currentTime = 0;
  setSpeed(0.25);   // slow-mo so every detail is visible
  video.play();

  stopPulse();
  drawLoop();

  document.getElementById('viewer-wrap').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── "▶ Continue / Next Issue" button handler ─────────────────────────────
function playFromIssue() {
  trailPositions = [];
  document.getElementById('play-from-here').classList.add('hidden');
  hideCallout();

  if (watchAllActive) {
    _advanceWatchAll();
  } else {
    setSpeed(0.25);
    video.play();
  }
}

// ── Watch-All: play through every issue in video order ────────────────────
function watchAll() {
  if (!TOP_ISSUES || !TOP_ISSUES.length) return;

  // Sort issue indices by issue_start_sec (chronological order)
  watchAllOrder = TOP_ISSUES
    .map((issue, idx) => ({ idx, sec: issue.issue_start_sec ?? 0 }))
    .sort((a, b) => a.sec - b.sec)
    .map(item => item.idx);

  watchAllActive  = true;
  watchAllCurrent = 0;
  watchIssue(watchAllOrder[0], true);
}

function _advanceWatchAll() {
  watchAllCurrent++;
  if (watchAllCurrent >= watchAllOrder.length) {
    // All done — reset watch-all state and let video play free
    watchAllActive = false;
    watchAllOrder  = [];
    const tipEl = document.getElementById('continue-tip');
    if (tipEl) tipEl.textContent = '✅ All issues reviewed! Great work.';
    setSpeed(0.25);
    video.play();
    return;
  }
  watchIssue(watchAllOrder[watchAllCurrent], true);
}

// Update the continue button label based on current mode
function _updateContinueButton() {
  const btn = document.getElementById('continue-btn');
  if (!btn) return;
  if (watchAllActive) {
    const remaining = watchAllOrder.length - watchAllCurrent - 1;
    btn.textContent = remaining > 0
      ? `▶ Next Issue (${watchAllCurrent + 1}/${watchAllOrder.length})`
      : '▶ Finish Review';
  } else {
    btn.textContent = '▶ Continue in slow-mo';
  }
}

// ── Main rAF draw loop ────────────────────────────────────────────────────
function drawLoop() {
  if (activeIssueIdx < 0) { animHandle = null; return; }
  animHandle = requestAnimationFrame(drawLoop);

  resizeCanvas();
  const cw = canvas.width, ch = canvas.height;
  ctx.clearRect(0, 0, cw, ch);

  const issue = TOP_ISSUES[activeIssueIdx];
  if (!issue) return;

  if (video.paused) {
    // Frozen frame: full overlay with arc + big label + focus ring
    _drawFrozen(issue, cw, ch);
  } else {
    // 1. Skeleton with highlighted limbs relevant to this issue
    _drawSkeletonCanvas(activeJointPositions, cw, ch, issue);

    // 2. Pulsing red tracking dot on the problem joint
    _drawTrackingDot(issue, cw, ch);

    // 3. After the issue starts: trail + live angle + arc + label
    const startSec = issue.issue_start_sec ?? 0;
    if (video.currentTime >= startSec) {
      _drawTrail(cw, ch);
      _drawLiveAngle(issue, activeJointPositions, cw, ch);

      if (issue.angle_joints && issue.angle_joints.length === 3) {
        const p1 = _getJointPx(issue.angle_joints[0], activeJointPositions, cw, ch);
        const vp = _getJointPx(issue.angle_joints[1], activeJointPositions, cw, ch);
        const p2 = _getJointPx(issue.angle_joints[2], activeJointPositions, cw, ch);
        if (p1 && vp && p2) _drawAngleArc(p1, vp, p2, Math.min(cw, ch) * 0.07);
      }

      if (issue.canvas_label) _drawCanvasLabel(issue.canvas_label, cw, ch, 0.85);
    }

    // 4. Phase bar always visible at bottom
    _drawPhaseBar(cw, ch);
  }
}

// ── Tracking dot — shown throughout the whole video ───────────────────────
// Big, pulsing red dot that always sits on the problem joint so the user
// knows exactly what to watch even during the run-up.
function _drawTrackingDot(issue, cw, ch) {
  const jName = issue?.problem_joints?.[0];
  if (!jName) return;
  const pos = _getJointPx(jName, activeJointPositions, cw, ch);
  if (!pos) return;

  // Pulsing outer glow
  pulse.r += pulse.growing ? 0.5 : -0.5;
  if (pulse.r > 32) pulse.growing = false;
  if (pulse.r < 18) pulse.growing = true;

  // Glow halo
  ctx.beginPath();
  ctx.arc(pos.x, pos.y, pulse.r + 10, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(255, 30, 30, 0.20)';
  ctx.lineWidth   = 14;
  ctx.stroke();

  // Outer ring
  ctx.beginPath();
  ctx.arc(pos.x, pos.y, pulse.r, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(255, 30, 30, 0.85)';
  ctx.lineWidth   = 3.5;
  ctx.stroke();

  // Solid centre dot
  ctx.beginPath();
  ctx.arc(pos.x, pos.y, 11, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(255, 20, 20, 0.97)';
  ctx.fill();

  // White inner spot for contrast
  ctx.beginPath();
  ctx.arc(pos.x, pos.y, 4, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  ctx.fill();

  // Label pill
  const label = JOINT_ZONE[jName]?.label || jName.replace(/_/g, ' ');
  _drawLabelPill(pos.x, pos.y, label, cw, ch);
}

// ── FROZEN overlay — shown when video is paused at issue moment ───────────
function _drawFrozen(issue, cw, ch) {
  const positions    = _getFramePositionsAt(issue.issue_start_sec ?? 0);
  const primaryJoint = issue.problem_joints?.[0];
  if (!primaryJoint) return;

  const pos = _getJointPx(primaryJoint, positions, cw, ch);

  // 0. Skeleton with highlighted limbs
  _drawSkeletonCanvas(positions, cw, ch, issue);

  // 1. Angle arc
  if (issue.angle_joints && issue.angle_joints.length === 3) {
    const p1 = _getJointPx(issue.angle_joints[0], positions, cw, ch);
    const vp = _getJointPx(issue.angle_joints[1], positions, cw, ch);
    const p2 = _getJointPx(issue.angle_joints[2], positions, cw, ch);
    if (p1 && vp && p2) _drawAngleArc(p1, vp, p2, Math.min(cw, ch) * 0.10);
  }

  // 2. Big label badge at top
  if (issue.canvas_label) _drawCanvasLabel(issue.canvas_label, cw, ch, 1.0);

  // 3. Large focus circle
  if (pos) {
    // Wide glow halo
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, 46, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 30, 30, 0.20)';
    ctx.lineWidth   = 20;
    ctx.stroke();

    // Outer ring
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, 38, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 30, 30, 0.90)';
    ctx.lineWidth   = 4;
    ctx.stroke();

    // Inner ring
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, 28, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 80, 80, 0.60)';
    ctx.lineWidth   = 2;
    ctx.stroke();

    // Centre dot
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, 12, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255, 20, 20, 0.97)';
    ctx.fill();

    // White inner spot
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, 5, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255,255,255,0.95)';
    ctx.fill();

    // Label pill
    const label = JOINT_ZONE[primaryJoint]?.label || primaryJoint.replace(/_/g, ' ');
    _drawLabelPill(pos.x, pos.y, label, cw, ch);
  }

  // 4. Phase bar at bottom
  _drawPhaseBar(cw, ch);
}

// ── Skeleton on canvas — highlights issue limbs in orange, rest in green ──
function _drawSkeletonCanvas(positions, cw, ch, issue) {
  if (!positions || !Object.keys(positions).length) return;

  const problemSet   = new Set(issue?.problem_joints || []);
  const angleSet     = new Set(issue?.angle_joints   || []);
  const allHighlight = new Set([...problemSet, ...angleSet]);

  // Limb connections
  for (const [a, b] of SKELETON_CONNECTIONS) {
    const pa = _getJointPx(a, positions, cw, ch);
    const pb = _getJointPx(b, positions, cw, ch);
    if (!pa || !pb) continue;
    const isHighlight = allHighlight.has(a) || allHighlight.has(b);
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    ctx.lineTo(pb.x, pb.y);
    ctx.strokeStyle = isHighlight
      ? 'rgba(255, 140, 0, 0.82)'
      : 'rgba(100, 210, 100, 0.30)';
    ctx.lineWidth   = isHighlight ? 4 : 1.5;
    ctx.lineCap     = 'round';
    ctx.stroke();
  }

  // Joint dots
  const allJoints = [...new Set(SKELETON_CONNECTIONS.flat())];
  for (const name of allJoints) {
    const pos = _getJointPx(name, positions, cw, ch);
    if (!pos) continue;
    const isProb = problemSet.has(name) || angleSet.has(name);
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, isProb ? 7 : 4, 0, Math.PI * 2);
    ctx.fillStyle = isProb ? 'rgba(255, 100, 0, 0.90)' : 'rgba(80, 200, 80, 0.45)';
    ctx.fill();
  }
}

// ── Live angle badge — shown while video is playing (not just on pause) ───
function _drawLiveAngle(issue, positions, cw, ch) {
  if (!issue?.angle_joints || issue.angle_joints.length !== 3) return;
  const p1 = _getJointPx(issue.angle_joints[0], positions, cw, ch);
  const vp = _getJointPx(issue.angle_joints[1], positions, cw, ch);
  const p2 = _getJointPx(issue.angle_joints[2], positions, cw, ch);
  if (!p1 || !vp || !p2) return;

  const angle = Math.round(_computeAngle(p1, vp, p2));
  const text  = `${angle}°`;

  ctx.font = 'bold 21px system-ui, sans-serif';
  const tw = ctx.measureText(text).width;
  const bw = tw + 20, bh = 34;
  const bx = Math.max(2, Math.min(cw - bw - 2, vp.x + 20));
  const by = Math.max(2, Math.min(ch - bh - 2, vp.y - bh - 10));

  // Shadow
  ctx.fillStyle = 'rgba(0,0,0,0.72)';
  _roundRect(ctx, bx - 2, by - 2, bw + 4, bh + 4, 8); ctx.fill();
  // Badge
  ctx.fillStyle = 'rgba(200, 90, 0, 0.96)';
  _roundRect(ctx, bx, by, bw, bh, 6); ctx.fill();
  // Text
  ctx.fillStyle = '#fff';
  ctx.fillText(text, bx + 10, by + bh * 0.74);
}

// ── Phase timeline bar — always shown at bottom of canvas ─────────────────
function _drawPhaseBar(cw, ch) {
  if (!CLIP_DURATION || CLIP_DURATION <= 0) return;

  const barH = 22;
  const barY = ch - barH - 5;
  const barW = cw - 20;
  const barX = 10;

  // Background
  ctx.fillStyle = 'rgba(0,0,0,0.50)';
  _roundRect(ctx, barX - 2, barY - 2, barW + 4, barH + 4, 5); ctx.fill();

  for (const p of BATTING_PHASES) {
    const x = barX + p.start * barW;
    const w = (p.end   - p.start) * barW;
    ctx.fillStyle = p.col;
    ctx.fillRect(x, barY, w, barH);
    // Segment divider
    ctx.strokeStyle = 'rgba(0,0,0,0.55)';
    ctx.lineWidth   = 1;
    ctx.beginPath();
    ctx.moveTo(x + w, barY); ctx.lineTo(x + w, barY + barH);
    ctx.stroke();
    // Label
    if (w > 52) {
      ctx.font      = 'bold 10px system-ui, sans-serif';
      ctx.fillStyle = 'rgba(255,255,255,0.95)';
      ctx.fillText(p.label, x + 5, barY + 14);
    }
  }

  // Playhead marker
  const progress = Math.min(video.currentTime / CLIP_DURATION, 1.0);
  const px = barX + progress * barW;
  ctx.fillStyle   = 'rgba(255,255,255,0.97)';
  ctx.strokeStyle = 'rgba(0,0,0,0.80)';
  ctx.lineWidth   = 1;
  _roundRect(ctx, px - 2, barY - 4, 4, barH + 8, 2);
  ctx.fill(); ctx.stroke();
}

// ── Angle arc ─────────────────────────────────────────────────────────────
function _drawAngleArc(p1, vp, p2, arcRadius) {
  const a1  = Math.atan2(p1.y - vp.y, p1.x - vp.x);
  const a2  = Math.atan2(p2.y - vp.y, p2.x - vp.x);
  const r   = arcRadius;
  const arm = r * 1.6;

  ctx.strokeStyle = 'rgba(255, 160, 0, 0.95)';
  ctx.lineWidth   = 3;
  ctx.beginPath(); ctx.moveTo(vp.x, vp.y);
  ctx.lineTo(vp.x + Math.cos(a1) * arm, vp.y + Math.sin(a1) * arm); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(vp.x, vp.y);
  ctx.lineTo(vp.x + Math.cos(a2) * arm, vp.y + Math.sin(a2) * arm); ctx.stroke();

  let diff = a2 - a1;
  while (diff < -Math.PI) diff += 2 * Math.PI;
  while (diff >  Math.PI) diff -= 2 * Math.PI;

  ctx.beginPath();
  ctx.arc(vp.x, vp.y, r, a1, a1 + diff);
  ctx.strokeStyle = 'rgba(255, 210, 0, 0.95)';
  ctx.lineWidth   = 3.5;
  ctx.stroke();

  // Degree badge near arc midpoint
  const midA     = a1 + diff / 2;
  const badgeX   = vp.x + Math.cos(midA) * (r + 28);
  const badgeY   = vp.y + Math.sin(midA) * (r + 28);
  const angleDeg = Math.round(_computeAngle(p1, vp, p2));

  ctx.font = 'bold 18px system-ui, sans-serif';
  const tw  = ctx.measureText(angleDeg + '°').width;
  const bw  = tw + 18, bh = 30;
  const bx  = Math.max(2, Math.min(canvas.width  - bw - 2, badgeX - bw / 2));
  const by  = Math.max(2, Math.min(canvas.height - bh - 2, badgeY - bh / 2));

  ctx.fillStyle = 'rgba(180, 80, 0, 0.95)';
  _roundRect(ctx, bx, by, bw, bh, 7); ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.fillText(angleDeg + '°', bx + 9, by + bh * 0.73);
}

// ── Canvas label badge — big, readable banner at top of video ─────────────
function _drawCanvasLabel(text, cw, ch, alpha = 1.0) {
  ctx.font = 'bold 20px system-ui, sans-serif';   // was 13px — now much bigger
  const tw    = ctx.measureText(text).width;
  const padX  = 22;
  const pillW = Math.min(tw + padX * 2, cw - 16);
  const pillH = 44;                                // was 30
  const pillX = (cw - pillW) / 2;
  const pillY = 14;

  // Dark shadow
  ctx.fillStyle = `rgba(0,0,0,${0.6 * alpha})`;
  _roundRect(ctx, pillX - 4, pillY - 4, pillW + 8, pillH + 8, 13);
  ctx.fill();

  // Red pill
  ctx.fillStyle = `rgba(210, 20, 20, ${0.95 * alpha})`;
  _roundRect(ctx, pillX, pillY, pillW, pillH, 10);
  ctx.fill();

  // Text
  ctx.fillStyle = `rgba(255,255,255,${alpha})`;
  ctx.save();
  ctx.beginPath();
  ctx.rect(pillX + 6, pillY, pillW - 12, pillH);
  ctx.clip();
  ctx.fillText(text, pillX + padX, pillY + pillH * 0.70);
  ctx.restore();
}

// ── Label pill beside joint ───────────────────────────────────────────────
function _drawLabelPill(dotX, dotY, label, cw, ch) {
  const text = '● ' + label.toUpperCase();
  ctx.font   = 'bold 13px system-ui, sans-serif';
  const tw   = ctx.measureText(text).width;
  const pw = tw + 16, ph = 24;
  const px = Math.min(dotX + 46, cw - pw - 4);
  const py = dotY - ph / 2;

  ctx.beginPath();
  ctx.moveTo(dotX + 14, dotY);
  ctx.lineTo(px, py + ph * 0.6);
  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  ctx.fillStyle = 'rgba(180, 20, 20, 0.95)';
  _roundRect(ctx, px, py, pw, ph, 6); ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.fillText(text, px + 8, py + ph * 0.72);
}

// ── Fading movement trail ─────────────────────────────────────────────────
function _drawTrail(cw, ch) {
  if (trailPositions.length < 2) return;
  const n = trailPositions.length;

  ctx.beginPath();
  ctx.moveTo(trailPositions[0].x, trailPositions[0].y);
  for (let i = 1; i < n; i++) ctx.lineTo(trailPositions[i].x, trailPositions[i].y);
  ctx.strokeStyle = 'rgba(255, 140, 0, 0.35)';
  ctx.lineWidth   = 3;
  ctx.lineJoin    = 'round';
  ctx.stroke();

  for (let i = 0; i < n; i++) {
    const t = (i + 1) / n;
    const p = trailPositions[i];
    ctx.beginPath();
    ctx.arc(p.x, p.y, 5 * t, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255, 100, 0, ${t * 0.7})`;
    ctx.fill();
  }
}

// ── Joint position helpers ────────────────────────────────────────────────
function _getFramePositionsAt(targetSec) {
  if (!FRAME_LANDMARKS || !FRAME_LANDMARKS.length) return {};
  let best = FRAME_LANDMARKS[0], bestDiff = Math.abs(best.t - targetSec);
  for (let i = 1; i < FRAME_LANDMARKS.length; i++) {
    const d = Math.abs(FRAME_LANDMARKS[i].t - targetSec);
    if (d < bestDiff) { bestDiff = d; best = FRAME_LANDMARKS[i]; }
  }
  return best ? (best.j || {}) : {};
}

function _getJointPx(name, positions, cw, ch) {
  if (positions && positions[name])
    return { x: positions[name][0] * cw, y: positions[name][1] * ch };
  if (LANDMARK_POSITIONS[name])
    return { x: LANDMARK_POSITIONS[name].x * cw, y: LANDMARK_POSITIONS[name].y * ch };
  if (JOINT_ZONE[name])
    return { x: cw * 0.5, y: JOINT_ZONE[name].y * ch };
  return null;
}

// ── Stop animation ────────────────────────────────────────────────────────
function stopPulse() {
  if (animHandle) { cancelAnimationFrame(animHandle); animHandle = null; }
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  activeJointPositions = {};
  trailPositions = [];
}

// ── Zoom ──────────────────────────────────────────────────────────────────
function applyZoomToJoint(jointName) {
  let ox = 50, oy = 50, scale = 2.2;
  if (jointName && LANDMARK_POSITIONS[jointName]) {
    ox = LANDMARK_POSITIONS[jointName].x * 100;
    oy = LANDMARK_POSITIONS[jointName].y * 100;
    scale = 2.5;
  } else if (jointName && JOINT_ZONE[jointName]) {
    oy = JOINT_ZONE[jointName].y * 100;
    scale = 2.2;
  }
  zoomLevel = scale; zoomOriginX = ox; zoomOriginY = oy;
  applyTransform();
}

function applyTransform() {
  video.style.transformOrigin = `${zoomOriginX}% ${zoomOriginY}%`;
  video.style.transform       = `scale(${zoomLevel})`;
  // Show/hide floating zoom-out button
  const zBtn = document.getElementById('zoom-out-overlay');
  if (zBtn) zBtn.classList.toggle('hidden', zoomLevel <= 1);
  setTimeout(resizeCanvas, 480);
}

function zoomStep(dir) {
  zoomLevel = Math.max(1, Math.min(4, zoomLevel + dir * 0.4));
  applyTransform();
}

function resetZoom() {
  zoomLevel = 1; zoomOriginX = 50; zoomOriginY = 50;
  video.style.transform       = 'scale(1)';
  video.style.transformOrigin = '50% 50%';
  const zBtn = document.getElementById('zoom-out-overlay');
  if (zBtn) zBtn.classList.add('hidden');
  setTimeout(resizeCanvas, 480);
}

function resetViewer() {
  stopPulse();
  autoPaused = false;
  resetZoom();
  setSpeed(0.25);   // always return to slow-mo on reset
  document.getElementById('now-watching').classList.add('hidden');
  document.getElementById('play-from-here').classList.add('hidden');
  hideCallout();
  activeIssueIdx = -1;
  document.querySelectorAll('.watch-btn').forEach(b => b.classList.remove('watch-btn-active'));
  video.currentTime = 0;
  video.play();
}

// ── Speed ─────────────────────────────────────────────────────────────────
function setSpeed(s) {
  currentSpeed = s;
  video.playbackRate = s;
  document.getElementById('speed-025')?.classList.toggle('vbtn-active', s === 0.25);
  document.getElementById('speed-05') ?.classList.toggle('vbtn-active', s === 0.5);
  document.getElementById('speed-1')  ?.classList.toggle('vbtn-active', s === 1);
}

// ── Loop ──────────────────────────────────────────────────────────────────
function toggleLoop() {
  loopEnabled = !loopEnabled;
  video.loop  = loopEnabled;
  const btn   = document.getElementById('loop-btn');
  btn.textContent = loopEnabled ? '↺ ON' : '↺ OFF';
  btn.classList.toggle('vbtn-active', loopEnabled);
}

// ── Callout ───────────────────────────────────────────────────────────────
function showCallout(title, body) {
  document.getElementById('callout-title').textContent = title;
  document.getElementById('callout-body').textContent  = body || '';
  const box = document.getElementById('callout-box');
  box.classList.remove('hidden');
  box.classList.add('callout-enter');
}

function hideCallout() {
  document.getElementById('callout-box').classList.add('hidden');
}

// ── Maths helpers ─────────────────────────────────────────────────────────
function _computeAngle(p1, vp, p2) {
  const v1x = p1.x - vp.x, v1y = p1.y - vp.y;
  const v2x = p2.x - vp.x, v2y = p2.y - vp.y;
  const dot  = v1x * v2x + v1y * v2y;
  const mag1 = Math.sqrt(v1x * v1x + v1y * v1y);
  const mag2 = Math.sqrt(v2x * v2x + v2y * v2y);
  return Math.acos(Math.max(-1, Math.min(1, dot / (mag1 * mag2 + 1e-9)))) * 180 / Math.PI;
}

function _roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function roundRect(c, x, y, w, h, r) { _roundRect(c, x, y, w, h, r); }
