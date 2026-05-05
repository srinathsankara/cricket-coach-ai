/* Cricket Coach AI — upload page logic */

let selectedMode = 'batting';
let selectedHand = 'right';
let selectedFile = null;
let videoDuration = 0;   // seconds
let trimStart = 0;       // seconds
let trimEnd   = 0;       // seconds

// ── Mode / hand toggles ────────────────────────────────────────────────────

function selectMode(mode) {
  selectedMode = mode;
  applyToggle('btn-batting', mode === 'batting');
  applyToggle('btn-bowling', mode === 'bowling');
}

function selectHand(hand) {
  selectedHand = hand;
  applyToggle('btn-right', hand === 'right');
  applyToggle('btn-left',  hand === 'left');
}

function applyToggle(id, active) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('active-toggle', active);
}

// ── Drag-and-drop ──────────────────────────────────────────────────────────

function handleDragOver(e) {
  e.preventDefault();
  document.getElementById('upload-area').classList.add('drag-over');
}

function handleDragLeave() {
  document.getElementById('upload-area').classList.remove('drag-over');
}

function handleDrop(e) {
  e.preventDefault();
  document.getElementById('upload-area').classList.remove('drag-over');
  if (e.dataTransfer.files.length > 0) setFile(e.dataTransfer.files[0]);
}

function handleFileSelect(e) {
  if (e.target.files.length > 0) setFile(e.target.files[0]);
}

// ── File validation + UI ───────────────────────────────────────────────────

function setFile(file) {
  const ext = ('.' + file.name.split('.').pop()).toLowerCase();
  if (!['.mp4', '.mov', '.avi', '.mkv'].includes(ext)) {
    showError('Please upload a video file (MP4, MOV, or AVI).');
    return;
  }
  if (file.size > 500 * 1024 * 1024) {
    showError('File is too large (max 500 MB). Try trimming the video first.');
    return;
  }

  selectedFile = file;
  document.getElementById('file-name').textContent = file.name;
  document.getElementById('file-size').textContent = fmtSize(file.size);
  document.getElementById('file-info').classList.remove('hidden');

  // Load video preview to get duration and show trim UI
  const url = URL.createObjectURL(file);
  const vid  = document.getElementById('preview-video');
  vid.src = url;
  vid.onloadedmetadata = () => {
    videoDuration = vid.duration;
    initTrimSliders(videoDuration);
    document.getElementById('trim-section').classList.remove('hidden');
    enableAnalyseBtn();
  };
}

function clearFile() {
  selectedFile = null;
  videoDuration = 0;
  trimStart = 0;
  trimEnd   = 0;

  const vid = document.getElementById('preview-video');
  if (vid.src) URL.revokeObjectURL(vid.src);
  vid.src = '';

  document.getElementById('file-input').value = '';
  document.getElementById('file-info').classList.add('hidden');
  document.getElementById('trim-section').classList.add('hidden');
  disableAnalyseBtn();
}

function enableAnalyseBtn() {
  const btn = document.getElementById('analyse-btn');
  btn.disabled = false;
  btn.className = 'mt-6 w-full py-4 px-8 rounded-xl font-bold text-lg transition-all ' +
    'bg-green-900 text-white cursor-pointer hover:bg-green-800';
}

function disableAnalyseBtn() {
  const btn = document.getElementById('analyse-btn');
  btn.disabled = true;
  btn.className = 'mt-6 w-full py-4 px-8 rounded-xl font-bold text-lg transition-all ' +
    'bg-gray-200 text-gray-400 cursor-not-allowed';
}

// ── Trim sliders ───────────────────────────────────────────────────────────

function initTrimSliders(duration) {
  const startSlider = document.getElementById('start-slider');
  const endSlider   = document.getElementById('end-slider');

  // Set sliders to use real seconds as values
  startSlider.min  = 0;
  startSlider.max  = duration;
  startSlider.step = Math.max(0.1, duration / 1000);
  startSlider.value = 0;

  endSlider.min   = 0;
  endSlider.max   = duration;
  endSlider.step  = Math.max(0.1, duration / 1000);
  endSlider.value = duration;

  trimStart = 0;
  trimEnd   = duration;

  document.getElementById('tl-label-end').textContent = fmtTime(duration);
  updateTrimUI();
}

function onTrimChange() {
  const startSlider = document.getElementById('start-slider');
  const endSlider   = document.getElementById('end-slider');

  let s = parseFloat(startSlider.value);
  let e = parseFloat(endSlider.value);

  // Enforce minimum 1-second selection and prevent crossover
  const MIN_CLIP = 1.0;
  if (s >= e - MIN_CLIP) {
    if (document.activeElement === startSlider) {
      s = e - MIN_CLIP;
      startSlider.value = s;
    } else {
      e = s + MIN_CLIP;
      endSlider.value = e;
    }
  }

  trimStart = s;
  trimEnd   = e;
  updateTrimUI();
}

function updateTrimUI() {
  const dur = videoDuration || 1;
  const startPct = (trimStart / dur) * 100;
  const endPct   = (trimEnd   / dur) * 100;
  const midWidth = endPct - startPct;

  document.getElementById('tl-left').style.width        = startPct + '%';
  document.getElementById('tl-mid').style.left          = startPct + '%';
  document.getElementById('tl-mid').style.width         = midWidth + '%';
  document.getElementById('tl-right').style.width       = (100 - endPct) + '%';
  document.getElementById('tl-start-handle').style.left = startPct + '%';
  document.getElementById('tl-end-handle').style.left   = endPct + '%';

  document.getElementById('start-time-label').textContent = fmtTime(trimStart);
  document.getElementById('end-time-label').textContent   = fmtTime(trimEnd);
  document.getElementById('tl-label-start').textContent   = fmtTime(trimStart);
  document.getElementById('tl-label-end').textContent     = fmtTime(trimEnd);

  const clipSec = trimEnd - trimStart;
  const isFullVideo = trimStart < 0.5 && trimEnd > videoDuration - 0.5;

  document.getElementById('trim-duration-badge').textContent =
    isFullVideo ? 'Full video' : `${fmtTime(clipSec)} selected`;

  document.getElementById('trim-info').textContent =
    isFullVideo
      ? 'Entire video will be analysed. Use sliders above to select a smaller section.'
      : `Analysing from ${fmtTime(trimStart)} to ${fmtTime(trimEnd)} — ${fmtTime(clipSec)} of footage.`;
}

function previewSelection() {
  const vid = document.getElementById('preview-video');
  vid.currentTime = trimStart;
  vid.play();

  // Auto-pause at end of selection
  const checkEnd = setInterval(() => {
    if (vid.currentTime >= trimEnd) {
      vid.pause();
      clearInterval(checkEnd);
    }
  }, 100);
}

// ── Upload + polling ───────────────────────────────────────────────────────

async function startAnalysis() {
  if (!selectedFile) return;

  const form = new FormData();
  form.append('video',       selectedFile);
  form.append('mode',        selectedMode);
  form.append('handedness',  selectedHand);
  form.append('age_group',   document.getElementById('age-group').value);
  form.append('trim_start',  trimStart.toFixed(3));
  form.append('trim_end',    trimEnd.toFixed(3));

  showProcessing(true);
  updateProgress(5, 'Uploading video…');

  try {
    const res = await fetch('/upload', { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showProcessing(false);
      showError(err.error || 'Upload failed. Please try again.');
      return;
    }
    const { job_id } = await res.json();
    updateProgress(12, 'Video uploaded! Starting analysis…');
    pollStatus(job_id);
  } catch {
    showProcessing(false);
    showError('Connection error. Make sure the app is running and try again.');
  }
}

function pollStatus(jobId) {
  const MESSAGES = {
    0:  'Detecting body position…',
    20: 'Tracking movements…',
    40: 'Calculating joint angles…',
    55: 'Applying cricket rules…',
    65: 'Creating annotated video…',
    85: 'Finishing up…',
    95: 'Almost done…',
  };

  const iv = setInterval(async () => {
    try {
      const res  = await fetch(`/status/${jobId}`);
      const data = await res.json();

      if (data.status === 'processing') {
        const pct = data.progress || 0;
        const msg = Object.entries(MESSAGES)
          .filter(([k]) => pct >= Number(k))
          .pop()?.[1] ?? 'Working on it…';
        updateProgress(pct, msg);

      } else if (data.status === 'done') {
        clearInterval(iv);
        updateProgress(100, 'Done! Loading results…');
        setTimeout(() => { window.location.href = `/results/${jobId}`; }, 600);

      } else if (data.status === 'error') {
        clearInterval(iv);
        showProcessing(false);
        showError('Analysis failed: ' + (data.message || 'Unknown error. Check the video and try again.'));
      }
    } catch {
      clearInterval(iv);
      showProcessing(false);
      showError('Lost connection. Please try again.');
    }
  }, 2000);
}

// ── Helpers ────────────────────────────────────────────────────────────────

function showProcessing(visible) {
  document.getElementById('processing-screen').classList.toggle('hidden', !visible);
}

function updateProgress(pct, msg) {
  document.getElementById('prog-bar').style.width   = pct + '%';
  document.getElementById('prog-pct').textContent   = pct + '%';
  document.getElementById('proc-status').textContent = msg;
}

function fmtSize(bytes) {
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/** Format seconds → M:SS  e.g. 75.3 → "1:15" */
function fmtTime(sec) {
  sec = Math.max(0, sec);
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function showError(msg) {
  alert('⚠️ ' + msg);
}
