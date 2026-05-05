/* =========================================================
   Cricket Coach AI — Smart Coaching Viewer  (v4)
   results.js

   UX flow when "Watch This" is clicked:
   1. Video plays from ~2.5 s before the issue (context run-up).
   2. At the exact issue moment the video AUTO-PAUSES.
   3. Canvas overlay shows:
        • Angle arc with measured value at the problem joint
        • Red label badge with coaching measurement
        • Large focus circle on the problem joint
   4. Recommendation callout appears below with the fix advice.
   5. "▶ Continue" button lets the user resume at 0.25× slow-mo.
   6. Fading trail + live arc follow the joint during slow-mo.
   ========================================================= */

const video  = document.getElementById('coaching-video');
const canvas = document.getElementById('annotation-canvas');
const ctx    = canvas.getContext('2d');

// ── State ─────────────────────────────────────────────────────────────────
let currentSpeed       = 1;
let loopEnabled        = true;
let zoomLevel          = 1;
let zoomOriginX        = 50;
let zoomOriginY        = 50;
let animHandle         = null;
let activeIssueIdx     = -1;
let activeJointPositions = {};   // live per-frame joint positions
let trailPositions     = [];     // [{x,y}] fading movement trail
const TRAIL_MAX        = 18;     // how many trail positions to keep
let autoPaused         = false;  // true once we've auto-paused at the issue moment

// Pulse state for the focus ring while playing
let pulse = { r: 10, growing: true };

// ── Joint zones — fallback positions and human-readable labels ─────────────
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
  setSpeed(1);
});

video.addEventListener('ended', () => {
  if (loopEnabled) { video.currentTime = 0; video.play(); }
});

video.addEventListener('play', () => {
  // Hide the play button once video actually starts
  document.getElementById('play-from-here').classList.add('hidden');
});

window.addEventListener('resize', resizeCanvas);

function resizeCanvas() {
  const rect    = video.getBoundingClientRect();
  canvas.width  = rect.width  || video.offsetWidth;
  canvas.height = rect.height || video.offsetHeight;
}

// ── Frame sync: update live joint positions from FRAME_LANDMARKS ──────────
video.addEventListener('timeupdate', () => {
  if (activeIssueIdx < 0 || !FRAME_LANDMARKS || !FRAME_LANDMARKS.length) return;

  const t = video.currentTime;
  let best = FRAME_LANDMARKS[0], bestDiff = Math.abs(best.t - t);
  for (let i = 1; i < FRAME_LANDMARKS.length; i++) {
    const d = Math.abs(FRAME_LANDMARKS[i].t - t);
    if (d < bestDiff) { bestDiff = d; best = FRAME_LANDMARKS[i]; }
  }
  activeJointPositions = best ? (best.j || {}) : {};

  // ── Auto-pause at issue moment (first time only per watchIssue call) ──────
  if (!autoPaused && !video.paused) {
    const issue    = TOP_ISSUES[activeIssueIdx];
    const issueSec = issue?.issue_start_sec ?? 0;
    if (t >= issueSec) {
      autoPaused = true;
      video.pause();

      // Update the tip strip with the issue name
      const tipEl = document.getElementById('continue-tip');
      if (tipEl) tipEl.textContent = `⏸ ${issue.name} — see overlay & tip below`;

      // Show the "▶ Continue" button overlay
      document.getElementById('play-from-here').classList.remove('hidden');

      // Show coaching recommendation prominently below the video
      showCallout(issue.name, issue.how_to_fix || issue.message);
    }
  }

  // Accumulate trail for primary problem joint while playing
  if (!video.paused) {
    const issue = TOP_ISSUES[activeIssueIdx];
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
});

// ── PUBLIC: called by each "Watch This" button ────────────────────────────
function watchIssue(idx) {
  const issue = TOP_ISSUES[idx];
  if (!issue) return;

  activeIssueIdx = idx;
  autoPaused     = false;   // reset so we auto-pause again at issue moment
  trailPositions = [];
  pulse = { r: 10, growing: true };

  // Highlight the correct card button
  document.querySelectorAll('.watch-btn').forEach((b, i) => {
    b.classList.toggle('watch-btn-active', i === idx);
  });

  // Zoom to primary problem joint
  applyZoomToJoint(issue.problem_joints?.[0] || null);

  // Hide Continue button until auto-pause fires
  document.getElementById('play-from-here').classList.add('hidden');

  // Hide callout — it will reappear on auto-pause
  hideCallout();

  // "Now Watching" badge
  document.getElementById('now-watching').classList.remove('hidden');
  document.getElementById('nw-label').textContent = issue.name;

  // Seek to a couple of seconds BEFORE the issue for context, then play
  const issueSec  = issue.issue_start_sec ?? 0;
  const runUpSec  = Math.max(0, issueSec - 2.5);
  video.currentTime = runUpSec;
  setSpeed(1);      // normal speed for the run-up
  video.play();

  // Start rAF draw loop
  stopPulse();
  drawLoop();

  document.getElementById('viewer-wrap').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Called by "▶ Continue" button (after auto-pause at issue moment) ──────
function playFromIssue() {
  trailPositions = [];
  setSpeed(0.25);   // slow-mo so user can clearly see the issue
  video.play();
  // play event handler hides the button
  // autoPaused stays true so we don't re-pause at the same spot
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
    // ── FROZEN: show detailed static overlay at issue moment ─────────────
    _drawFrozen(issue, cw, ch);
  } else {
    // ── PLAYING: show trail + live arc (after issue starts) ─────────────
    const startSec = issue.issue_start_sec ?? 0;
    if (video.currentTime >= startSec) {
      _drawPlaying(issue, cw, ch);
    }
  }
}

// ── FROZEN overlay ────────────────────────────────────────────────────────
// Shown when video is paused at the issue moment.
// Draws: angle arc + value, canvas label, large focus circle.

function _drawFrozen(issue, cw, ch) {
  // Get joint positions at the issue frame
  const positions = _getFramePositionsAt(issue.issue_start_sec ?? 0);
  const primaryJoint = issue.problem_joints?.[0];
  if (!primaryJoint) return;

  const pos = _getJointPx(primaryJoint, positions, cw, ch);

  // 1. Angle arc (if 3 joints are defined)
  if (issue.angle_joints && issue.angle_joints.length === 3) {
    const p1 = _getJointPx(issue.angle_joints[0], positions, cw, ch);
    const vp = _getJointPx(issue.angle_joints[1], positions, cw, ch);
    const p2 = _getJointPx(issue.angle_joints[2], positions, cw, ch);
    if (p1 && vp && p2) {
      _drawAngleArc(p1, vp, p2, Math.min(cw, ch) * 0.08);
    }
  }

  // 2. Canvas label badge — "Knee: 142° — too BENT (needs 150–165°)"
  if (issue.canvas_label) {
    _drawCanvasLabel(issue.canvas_label, cw, ch);
  }

  // 3. Large focus circle at primary joint
  if (pos) {
    // Outer glow ring
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, 22, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 50, 50, 0.35)';
    ctx.lineWidth = 12;
    ctx.stroke();

    // Solid ring
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, 18, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 30, 30, 0.92)';
    ctx.lineWidth = 3;
    ctx.stroke();

    // Centre dot
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, 7, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255, 28, 28, 0.97)';
    ctx.fill();

    // Joint label pill to the right
    const label = JOINT_ZONE[primaryJoint]?.label || primaryJoint.replace(/_/g, ' ');
    _drawLabelPill(pos.x, pos.y, label, cw, ch);
  }
}

// ── PLAYING overlay ───────────────────────────────────────────────────────
// Shown while the video is playing after the issue moment.
// Draws: fading trail, pulsing dot, live angle arc, label.

function _drawPlaying(issue, cw, ch) {
  const positions    = activeJointPositions;
  const primaryJoint = issue.problem_joints?.[0];

  // 1. Fading trail
  _drawTrail(cw, ch);

  // 2. Live angle arc
  if (issue.angle_joints && issue.angle_joints.length === 3) {
    const p1 = _getJointPx(issue.angle_joints[0], positions, cw, ch);
    const vp = _getJointPx(issue.angle_joints[1], positions, cw, ch);
    const p2 = _getJointPx(issue.angle_joints[2], positions, cw, ch);
    if (p1 && vp && p2) {
      _drawAngleArc(p1, vp, p2, Math.min(cw, ch) * 0.07);
    }
  }

  // 3. Pulsing dot at current position
  if (primaryJoint) {
    const pos = _getJointPx(primaryJoint, positions, cw, ch);
    if (pos) {
      pulse.r += pulse.growing ? 0.45 : -0.45;
      if (pulse.r > 20) pulse.growing = false;
      if (pulse.r < 7)  pulse.growing = true;

      ctx.beginPath();
      ctx.arc(pos.x, pos.y, pulse.r, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255, 50, 50, 0.7)';
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(pos.x, pos.y, 5, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255, 28, 28, 0.95)';
      ctx.fill();
    }
  }

  // 4. Persistent canvas label (smaller, semi-transparent while playing)
  if (issue.canvas_label) {
    _drawCanvasLabel(issue.canvas_label, cw, ch, 0.78);
  }
}

// ── Angle arc drawing ─────────────────────────────────────────────────────
// Draws the arc at vertex (vp) between arms p1 and p2,
// shows the computed angle value near the arc midpoint.

function _drawAngleArc(p1, vp, p2, arcRadius) {
  const a1  = Math.atan2(p1.y - vp.y, p1.x - vp.x);
  const a2  = Math.atan2(p2.y - vp.y, p2.x - vp.x);
  const r   = arcRadius;

  // Short arm lines
  const arm  = r * 1.6;
  ctx.strokeStyle = 'rgba(255, 160, 0, 0.92)';
  ctx.lineWidth   = 2.5;

  ctx.beginPath();
  ctx.moveTo(vp.x, vp.y);
  ctx.lineTo(vp.x + Math.cos(a1) * arm, vp.y + Math.sin(a1) * arm);
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(vp.x, vp.y);
  ctx.lineTo(vp.x + Math.cos(a2) * arm, vp.y + Math.sin(a2) * arm);
  ctx.stroke();

  // Arc — always draw the smaller of the two possible arcs
  let diff = a2 - a1;
  while (diff < -Math.PI) diff += 2 * Math.PI;
  while (diff >  Math.PI) diff -= 2 * Math.PI;

  ctx.beginPath();
  ctx.arc(vp.x, vp.y, r, a1, a1 + diff);
  ctx.strokeStyle = 'rgba(255, 200, 0, 0.9)';
  ctx.lineWidth   = 3;
  ctx.stroke();

  // Angle value badge near arc midpoint
  const midA   = a1 + diff / 2;
  const badgeX = vp.x + Math.cos(midA) * (r + 20);
  const badgeY = vp.y + Math.sin(midA) * (r + 20);
  const angleDeg = Math.round(_computeAngle(p1, vp, p2));

  ctx.font      = 'bold 15px system-ui, sans-serif';
  const tw      = ctx.measureText(angleDeg + '°').width;
  const bw = tw + 14, bh = 24;
  const bx = Math.max(2, Math.min(canvas.width - bw - 2, badgeX - bw / 2));
  const by = Math.max(2, Math.min(canvas.height - bh - 2, badgeY - bh / 2));

  ctx.fillStyle = 'rgba(200, 100, 0, 0.92)';
  _roundRect(ctx, bx, by, bw, bh, 6);
  ctx.fill();

  ctx.fillStyle = '#fff';
  ctx.fillText(angleDeg + '°', bx + 7, by + bh * 0.72);
}

// ── Canvas label badge ────────────────────────────────────────────────────
// Full-width banner at the top of the video: e.g. "Knee: 142° — too BENT (needs 150–165°)"

function _drawCanvasLabel(text, cw, ch, alpha = 1.0) {
  ctx.font = 'bold 13px system-ui, sans-serif';
  const tw    = ctx.measureText(text).width;
  const padX  = 18, padY = 7;
  const pillW = Math.min(tw + padX * 2, cw - 12);
  const pillH = 30;
  const pillX = (cw - pillW) / 2;
  const pillY = 12;

  // Dark shadow for legibility
  ctx.fillStyle = `rgba(0,0,0,${0.55 * alpha})`;
  _roundRect(ctx, pillX - 3, pillY - 3, pillW + 6, pillH + 6, 11);
  ctx.fill();

  // Red pill
  ctx.fillStyle = `rgba(200, 28, 28, ${0.93 * alpha})`;
  _roundRect(ctx, pillX, pillY, pillW, pillH, 8);
  ctx.fill();

  // Text (truncate if needed)
  ctx.fillStyle = `rgba(255,255,255,${alpha})`;
  ctx.save();
  ctx.beginPath();
  ctx.rect(pillX + 6, pillY, pillW - 12, pillH);
  ctx.clip();
  ctx.fillText(text, pillX + padX, pillY + pillH * 0.68);
  ctx.restore();
}

// ── Label pill beside joint ───────────────────────────────────────────────
function _drawLabelPill(dotX, dotY, label, cw, ch) {
  const text  = '📍 ' + label.toUpperCase();
  ctx.font    = 'bold 11px system-ui, sans-serif';
  const tw    = ctx.measureText(text).width;
  const pw = tw + 14, ph = 20;
  const px = Math.min(dotX + 28, cw - pw - 4);
  const py = dotY - ph / 2;

  ctx.beginPath();
  ctx.moveTo(dotX + 8, dotY);
  ctx.lineTo(px, py + ph * 0.6);
  ctx.strokeStyle = 'rgba(255,255,255,0.7)';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  ctx.fillStyle = 'rgba(200, 28, 28, 0.93)';
  _roundRect(ctx, px, py, pw, ph, 5);
  ctx.fill();

  ctx.fillStyle = '#fff';
  ctx.fillText(text, px + 7, py + ph * 0.72);
}

// ── Fading trail ──────────────────────────────────────────────────────────
function _drawTrail(cw, ch) {
  if (trailPositions.length < 2) return;
  const n = trailPositions.length;

  // Connecting line (faded)
  ctx.beginPath();
  ctx.moveTo(trailPositions[0].x, trailPositions[0].y);
  for (let i = 1; i < n; i++) ctx.lineTo(trailPositions[i].x, trailPositions[i].y);
  ctx.strokeStyle = 'rgba(255, 140, 0, 0.30)';
  ctx.lineWidth = 2.5;
  ctx.lineJoin  = 'round';
  ctx.stroke();

  // Fading dots
  for (let i = 0; i < n; i++) {
    const t   = (i + 1) / n;            // 0→1, newest = 1
    const p   = trailPositions[i];
    ctx.beginPath();
    ctx.arc(p.x, p.y, 3.5 * t, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255, 100, 0, ${t * 0.65})`;
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
  if (positions && positions[name]) {
    return { x: positions[name][0] * cw, y: positions[name][1] * ch };
  }
  if (LANDMARK_POSITIONS[name]) {
    return { x: LANDMARK_POSITIONS[name].x * cw, y: LANDMARK_POSITIONS[name].y * ch };
  }
  if (JOINT_ZONE[name]) {
    return { x: cw * 0.5, y: JOINT_ZONE[name].y * ch };
  }
  return null;
}

// ── Stop animation and clear canvas ──────────────────────────────────────
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
  setTimeout(resizeCanvas, 480);
}

function zoomStep(dir) {
  zoomLevel = Math.max(1, Math.min(4, zoomLevel + dir * 0.4));
  applyTransform();
}

function resetViewer() {
  stopPulse();
  autoPaused = false;
  zoomLevel = 1; zoomOriginX = 50; zoomOriginY = 50;
  video.style.transform       = 'scale(1)';
  video.style.transformOrigin = '50% 50%';
  setSpeed(1);
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
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

// Alias kept for any external callers
function roundRect(c, x, y, w, h, r) { _roundRect(c, x, y, w, h, r); }
