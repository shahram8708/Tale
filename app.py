from flask import Flask, jsonify, render_template, request
from ai import AIServiceError, UnsafeRequestError, generate_tale_code
from tale_engine import analyze_tale_code, run_tale_code

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/learn")
def learn():
    return render_template("learn.html")


@app.route("/run", methods=["POST"])
def run_code():
    payload = request.get_json(force=True, silent=True) or {}
    code = payload.get("code", "")
    inputs = payload.get("inputs", [])
    if not code.strip():
        return jsonify({"ok": False, "error": "No code provided."}), 400

    result = run_tale_code(code, inputs)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@app.route("/analyze", methods=["POST"])
def analyze_code():
    payload = request.get_json(force=True, silent=True) or {}
    code = payload.get("code", "")
    analysis = analyze_tale_code(code)
    status = 200 if analysis.get("ok") else 400
    return jsonify(analysis), status


@app.route("/ai_generate", methods=["POST"])
def ai_generate():
    payload = request.get_json(force=True, silent=True) or {}
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"ok": False, "error": "Prompt is required."}), 400

    try:
        code = generate_tale_code(prompt)
        return jsonify({"ok": True, "code": code}), 200
    except UnsafeRequestError as exc:
        print(f"[AI DEBUG] unsafe: {exc}", flush=True)
        return jsonify({"ok": False, "error": "Unsafe request"}), 400
    except AIServiceError as exc:
        detail = str(exc) or "AI unavailable"
        print(f"[AI DEBUG] AIServiceError: {detail}", flush=True)
        return jsonify({"ok": False, "error": detail}), 503
    except Exception as exc:  # noqa: BLE001
        print(f"[AI DEBUG] Unexpected error: {type(exc).__name__}: {exc}", flush=True)
        import traceback

        print(traceback.format_exc(), flush=True)
        return jsonify({"ok": False, "error": "AI unavailable", "detail": str(exc)}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
