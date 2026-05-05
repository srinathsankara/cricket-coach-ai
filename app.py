import os
import uuid
import threading
import urllib.request
import webbrowser
from flask import Flask, render_template, request, jsonify, send_from_directory
from analysis.video_processor import process_video

# ── MediaPipe model auto-download ─────────────────────────────────────────
MODEL_PATH = 'pose_landmarker_lite.task'
MODEL_URL  = (
    'https://storage.googleapis.com/mediapipe-models/'
    'pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task'
)

def _ensure_model():
    if os.path.exists(MODEL_PATH):
        return
    print('[Cricket Coach AI] Downloading pose model (~5 MB)...')
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print('[Cricket Coach AI] Model downloaded.')
    except Exception as exc:
        print(f'[Cricket Coach AI] ERROR downloading model: {exc}')
        print(f'  Download manually from: {MODEL_URL}')
        print(f'  Place it at: {os.path.abspath(MODEL_PATH)}')

# ── Flask app ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['UPLOAD_FOLDER']      = 'uploads'
app.config['RESULTS_FOLDER']     = 'results'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)

jobs = {}   # {job_id: {status, progress, result?, message?}}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file attached'}), 400

    file = request.files['video']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.mp4', '.mov', '.avi', '.mkv'):
        return jsonify({'error': 'Unsupported format. Please use MP4, MOV, or AVI.'}), 400

    mode        = request.form.get('mode',       'batting')
    handedness  = request.form.get('handedness', 'right')
    age_group   = request.form.get('age_group',  'under10')
    trim_start  = float(request.form.get('trim_start', 0))
    trim_end    = float(request.form.get('trim_end',   0))   # 0 = full video

    job_id      = str(uuid.uuid4())[:8]
    video_path  = os.path.join(app.config['UPLOAD_FOLDER'], f'{job_id}{ext}')
    file.save(video_path)

    jobs[job_id] = {'status': 'processing', 'progress': 0}
    t = threading.Thread(
        target=_run_analysis,
        args=(job_id, video_path, mode, handedness, age_group, trim_start, trim_end),
        daemon=True,
    )
    t.start()
    return jsonify({'job_id': job_id})


def _run_analysis(job_id, video_path, mode, handedness, age_group,
                  trim_start, trim_end):
    def on_progress(p):
        jobs[job_id]['progress'] = p
    try:
        result = process_video(
            video_path, mode, handedness, age_group,
            trim_start=trim_start, trim_end=trim_end,
            progress_callback=on_progress,
        )
        jobs[job_id] = {'status': 'done', 'result': result}
    except Exception as exc:
        jobs[job_id] = {'status': 'error', 'message': str(exc)}


@app.route('/status/<job_id>')
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


@app.route('/results/<job_id>')
def results(job_id):
    job = jobs.get(job_id)
    if not job:
        return 'Job not found', 404
    if job['status'] != 'done':
        return 'Analysis not complete yet', 400
    return render_template('results.html', result=job['result'], job_id=job_id)


@app.route('/results/video/<filename>')
def result_video(filename):
    return send_from_directory('results', filename)


if __name__ == '__main__':
    _ensure_model()
    webbrowser.open('http://localhost:5000')
    app.run(debug=False, host='0.0.0.0', port=5000)
