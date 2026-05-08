import os
import uuid
import json
import sqlite3
import threading
import urllib.request
import webbrowser
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory
from analysis.video_processor import process_video
from analysis.claude_coaching  import enhance_with_claude

# ── MediaPipe model auto-download ─────────────────────────────────────────
MODELS = {
    'lite': {
        'path': 'pose_landmarker_lite.task',
        'url':  ('https://storage.googleapis.com/mediapipe-models/'
                 'pose_landmarker/pose_landmarker_lite/float16/1/'
                 'pose_landmarker_lite.task'),
    },
    'full': {
        'path': 'pose_landmarker_full.task',
        'url':  ('https://storage.googleapis.com/mediapipe-models/'
                 'pose_landmarker/pose_landmarker_full/float16/1/'
                 'pose_landmarker_full.task'),
    },
}


def _ensure_model(quality='lite'):
    cfg = MODELS.get(quality, MODELS['lite'])
    if os.path.exists(cfg['path']):
        return cfg['path']
    print(f'[Cricket Coach AI] Downloading pose model ({quality})...')
    try:
        urllib.request.urlretrieve(cfg['url'], cfg['path'])
        print('[Cricket Coach AI] Model downloaded.')
    except Exception as exc:
        print(f'[Cricket Coach AI] ERROR downloading model: {exc}')
    return cfg['path']


# ── Flask app ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['UPLOAD_FOLDER']      = 'uploads'
app.config['RESULTS_FOLDER']     = 'results'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024   # 500 MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)

jobs = {}   # {job_id: {status, progress, result?, message?}}

# ── SQLite session history ─────────────────────────────────────────────────
DB_PATH = 'sessions.db'


def _db_connect():
    return sqlite3.connect(DB_PATH)


def _init_db():
    con = _db_connect()
    con.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            job_id          TEXT PRIMARY KEY,
            created_at      TEXT,
            mode            TEXT,
            handedness      TEXT,
            age_group       TEXT,
            shot_type       TEXT,
            confidence      INTEGER,
            good_count      INTEGER,
            total_count     INTEGER,
            clip_duration   REAL,
            video_filename  TEXT,
            result_json     TEXT
        )
    ''')
    con.commit()
    con.close()


def _save_session(job_id, result):
    good  = sum(1 for c in result.get('checkpoints', []) if c['status'] == 'good')
    total = len(result.get('checkpoints', []))
    con   = _db_connect()
    con.execute(
        '''INSERT OR REPLACE INTO sessions
           (job_id, created_at, mode, handedness, age_group, shot_type,
            confidence, good_count, total_count, clip_duration, video_filename, result_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (
            job_id,
            datetime.now().strftime('%Y-%m-%d %H:%M'),
            result.get('mode', ''),
            result.get('handedness', ''),
            result.get('age_group', ''),
            result.get('shot_type', ''),
            result.get('confidence_score', 0),
            good, total,
            result.get('clip_duration', 0),
            result.get('video_filename', ''),
            json.dumps(result),
        ),
    )
    con.commit()
    con.close()


def _load_session(job_id):
    con = _db_connect()
    row = con.execute(
        'SELECT result_json FROM sessions WHERE job_id=?', (job_id,)
    ).fetchone()
    con.close()
    if row:
        return json.loads(row[0])
    return None


def _list_sessions(limit=50):
    con  = _db_connect()
    rows = con.execute(
        '''SELECT job_id, created_at, mode, handedness, age_group, shot_type,
                  confidence, good_count, total_count, clip_duration, video_filename
           FROM sessions ORDER BY created_at DESC LIMIT ?''',
        (limit,),
    ).fetchall()
    con.close()
    cols = ['job_id', 'created_at', 'mode', 'handedness', 'age_group', 'shot_type',
            'confidence', 'good_count', 'total_count', 'clip_duration', 'video_filename']
    return [dict(zip(cols, r)) for r in rows]


# ── Routes ────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/history')
def history():
    sessions = _list_sessions()
    return render_template('history.html', sessions=sessions)


@app.route('/upload', methods=['POST'])
def upload():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file attached'}), 400

    file = request.files['video']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.mp4', '.mov', '.avi', '.mkv'):
        return jsonify({'error': 'Unsupported format. Please use MP4, MOV, AVI or MKV.'}), 400

    mode       = request.form.get('mode',       'batting')
    handedness = request.form.get('handedness', 'right')
    age_group  = request.form.get('age_group',  'under10')
    quality    = request.form.get('quality',    'lite')     # 'lite' | 'full'
    trim_start = float(request.form.get('trim_start', 0))
    trim_end   = float(request.form.get('trim_end',   0))

    job_id     = str(uuid.uuid4())[:8]
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{job_id}{ext}')
    file.save(video_path)

    jobs[job_id] = {'status': 'processing', 'progress': 0}
    t = threading.Thread(
        target=_run_analysis,
        args=(job_id, video_path, mode, handedness, age_group,
              quality, trim_start, trim_end),
        daemon=True,
    )
    t.start()
    return jsonify({'job_id': job_id})


def _run_analysis(job_id, video_path, mode, handedness, age_group,
                  quality, trim_start, trim_end):
    def on_progress(p):
        jobs[job_id]['progress'] = p

    try:
        model_path = _ensure_model(quality)

        result = process_video(
            video_path, mode, handedness, age_group,
            model_path=model_path,
            trim_start=trim_start, trim_end=trim_end,
            progress_callback=on_progress,
        )

        # ── Claude AI coaching enhancement ────────────────────────────
        result['checkpoints'] = enhance_with_claude(
            result['checkpoints'], mode, handedness, age_group
        )
        # Rebuild top_issues after AI text update
        order      = {'fix': 0, 'improve': 1, 'good': 2, 'unknown': 3}
        sorted_cps = sorted(result['checkpoints'],
                            key=lambda c: order.get(c['status'], 3))
        result['top_issues'] = [c for c in sorted_cps
                                 if c['status'] in ('fix', 'improve')][:3]
        result['top_good']   = [c for c in sorted_cps
                                 if c['status'] == 'good'][:2]

        jobs[job_id] = {'status': 'done', 'result': result}
        _save_session(job_id, result)   # persist to SQLite

    except Exception as exc:
        jobs[job_id] = {'status': 'error', 'message': str(exc)}
        print(f'[Analysis error] {exc}')


@app.route('/status/<job_id>')
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify({k: v for k, v in job.items() if k != 'result'})


@app.route('/results/<job_id>')
def results(job_id):
    # Try in-memory first (just processed), then fall back to DB (after restart)
    job = jobs.get(job_id)
    if job and job['status'] == 'done':
        result = job['result']
    else:
        result = _load_session(job_id)
        if result is None:
            return 'Session not found', 404

    return render_template('results.html', result=result, job_id=job_id)


@app.route('/results/video/<filename>')
def result_video(filename):
    return send_from_directory('results', filename)


if __name__ == '__main__':
    _init_db()
    _ensure_model('lite')
    webbrowser.open('http://localhost:5000')
    app.run(debug=False, host='0.0.0.0', port=5000)
