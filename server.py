from flask import Flask, jsonify, request, send_from_directory
import os
import platform
import subprocess
import threading
import uuid
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(__file__))
from focus_stack_engine import process_batch, group_images_by_sequence, ALL_EXTS

app = Flask(__name__, static_folder='static')
tasks = {}
tasks_lock = threading.Lock()
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
os.makedirs(STATIC_DIR, exist_ok=True)


def _json_body():
    return request.get_json(silent=True) or {}


def _integer_option(data, name, default, minimum, maximum):
    try:
        value = int(data.get(name, default))
    except (TypeError, ValueError):
        raise ValueError(f"{name} 必须是整数")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} 必须在 {minimum} 到 {maximum} 之间")
    return value


@app.after_request
def local_security_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')


@app.route('/api/libs')
def get_libs():
    try:
        import rawpy; has_rawpy = True
    except ImportError:
        has_rawpy = False
    try:
        import lensfunpy; has_lensfun = True
    except ImportError:
        has_lensfun = False
    return jsonify({"has_rawpy": has_rawpy, "has_lensfun": has_lensfun})


@app.route('/api/scan', methods=['POST'])
def scan_folder():
    data = _json_body()
    folder = data.get('folder', '').strip()
    try:
        group_size = _integer_option(data, 'group_size', 10, 1, 100)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not folder or not os.path.isdir(folder):
        return jsonify({"error": f"文件夹不存在: {folder}"}), 400
    image_files = [str(f) for f in Path(folder).iterdir() if f.suffix.lower() in ALL_EXTS]
    if not image_files:
        return jsonify({"error": "文件夹中没有图像文件（支持 RAF/JPG/PNG/TIF）"}), 400
    groups = group_images_by_sequence(sorted(image_files), group_size)
    preview = [{
        "group_id": i+1, "count": len(g),
        "files": [os.path.basename(f) for f in g],
        "first_file": os.path.basename(g[0]) if g else ""
    } for i, g in enumerate(groups)]
    return jsonify({"total_images": len(image_files), "total_groups": len(groups), "groups": preview})


@app.route('/api/process', methods=['POST'])
def start_processing():
    data = _json_body()
    input_folder  = data.get('input_folder', '').strip()
    output_folder = data.get('output_folder', '').strip()
    output_format = data.get('output_format', 'jpg').lower()
    try:
        group_size = _integer_option(data, 'group_size', 10, 1, 100)
        quality = _integer_option(data, 'quality', 95, 60, 100)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if output_format not in {'jpg', 'png', 'tif'}:
        return jsonify({"error": "输出格式只支持 JPG、PNG 或 TIF"}), 400
    lens_correction = bool(data.get('lens_correction', True))
    ca_correction   = bool(data.get('ca_correction', True))
    camera_name   = data.get('camera_name', '').strip() or None
    lens_name     = data.get('lens_name', '').strip() or None

    if not input_folder or not os.path.isdir(input_folder):
        return jsonify({"error": f"输入文件夹不存在: {input_folder}"}), 400
    if not output_folder:
        output_folder = os.path.join(input_folder, '输出')

    task_id = str(uuid.uuid4())[:8]
    with tasks_lock:
        tasks[task_id] = {"status": "running", "stage": "starting",
                          "message": "准备开始...", "progress": 0,
                          "result": None, "output_folder": output_folder}

    def run_task():
        def cb(stage, message, pct):
            with tasks_lock:
                tasks[task_id].update({"stage": stage, "message": message, "progress": pct})
        try:
            result = process_batch(
                input_folder=input_folder, output_folder=output_folder,
                group_size=group_size, output_format=output_format, quality=quality,
                lens_correction=lens_correction, ca_correction=ca_correction,
                camera_name=camera_name, lens_name=lens_name,
                progress_callback=cb
            )
            with tasks_lock:
                tasks[task_id].update({"status": "done", "progress": 100, "result": result})
        except Exception as e:
            with tasks_lock:
                tasks[task_id].update({"status": "error", "message": str(e)})

    t = threading.Thread(target=run_task)
    t.daemon = True
    t.start()
    return jsonify({"task_id": task_id, "output_folder": output_folder})


@app.route('/api/status/<task_id>')
def get_status(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
        if task is None:
            return jsonify({"error": "任务不存在"}), 404
        return jsonify(task.copy())


@app.route('/api/open_folder', methods=['POST'])
def open_folder():
    data = _json_body()
    folder = data.get('folder', '')
    if os.path.isdir(folder):
        system = platform.system()
        if system == 'Darwin':   subprocess.Popen(['open', folder])
        elif system == 'Windows': subprocess.Popen(['explorer', folder])
        else:                    subprocess.Popen(['xdg-open', folder])
        return jsonify({"ok": True})
    return jsonify({"error": "文件夹不存在"}), 400


if __name__ == '__main__':
    print("=" * 50)
    print("  焦点堆叠批量处理工具 v4")
    print("  请在浏览器中访问: http://127.0.0.1:5050")
    print("=" * 50)
    app.run(host='127.0.0.1', port=5050, debug=False)
