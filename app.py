"""AI Summarizer - Flask backend.

Accepts pasted text, a PDF, or an image, and returns a summary in the
chosen length and tone. Every prompt is appended to prompts_log.md.
"""
import base64
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file
from pypdf import PdfReader
from pypdf.errors import PdfReadError

load_dotenv(override=True)

BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR / "prompts_log.md"
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()

MAX_UPLOAD_MB = 10
IMAGE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}

LENGTHS = {
    "short": "2-3 sentences",
    "medium": "one paragraph of about 5-7 sentences",
    "long": "a detailed summary of 3-4 short paragraphs",
    "bullets": "5-7 concise bullet points",
}
TONES = {
    "neutral": "neutral and objective",
    "formal": "formal and professional",
    "casual": "casual and friendly",
    "simple": "very simple, as if explaining to a 12-year-old",
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


def log_prompt(instruction, source, length, tone, text=None, filename=None):
    """Append one entry to prompts_log.md."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not LOG_FILE.exists():
        LOG_FILE.write_text("# Prompt Log\n\nEvery prompt sent to the AI is saved here.\n", encoding="utf-8")
    entry = [
        f"\n---\n\n## {stamp}\n",
        f"- **Input type:** {source}",
        f"- **Length:** {length}",
        f"- **Tone:** {tone}",
    ]
    if filename:
        entry.append(f"- **File:** {filename}")
    entry.append(f"\n**Instruction sent:**\n\n> {instruction}\n")
    if text:
        entry.append("**Pasted text:**\n\n```text\n" + text + "\n```\n")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write("\n".join(entry))


_WORKING_MODEL_CACHE = {"text": None, "vision": None}
_FAILED_MODELS = set()


def fetch_available_models():
    """Fetch all models currently available from Ollama."""
    headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}"} if OLLAMA_API_KEY else {}
    req = Request(f"{OLLAMA_HOST}/api/tags", headers=headers, method="GET")
    try:
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8")).get("models", [])
    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Cannot discover available Ollama models at {OLLAMA_HOST}."
        ) from exc


def get_candidate_models(image=False):
    """Return ordered list of models to try, prioritizing free and cached models."""
    cache_key = "vision" if image else "text"
    cached = _WORKING_MODEL_CACHE.get(cache_key)

    models_data = fetch_available_models()
    if not models_data:
        raise RuntimeError(f"No Ollama models found at {OLLAMA_HOST}.")

    model_names = [m.get("name") for m in models_data if m.get("name")]
    FREE_PRIORITY = ["beam", "beam:cloud"]
    candidates = []

    # Try cached working model first
    if cached and cached in model_names and cached not in _FAILED_MODELS:
        candidates.append(cached)

    if image:
        vision_names = [
            m["name"] for m in models_data
            if "vision" in m.get("capabilities", [])
            or any(k in m.get("name", "").lower() for k in ("vision", "llava", "gemma", "qwen", "minimax"))
        ]
        if not vision_names:
            raise RuntimeError("No vision-capable Ollama model is available for image uploads.")
        for name in vision_names:
            if name not in candidates and name not in _FAILED_MODELS:
                candidates.append(name)
        if not candidates:
            candidates = vision_names
    else:
        # For text, prioritize free models first
        for free_m in FREE_PRIORITY:
            for name in model_names:
                if (name == free_m or name.startswith(free_m)) and name not in candidates and name not in _FAILED_MODELS:
                    candidates.append(name)
        # Then all other available models
        for name in model_names:
            if name not in candidates and name not in _FAILED_MODELS:
                candidates.append(name)
        if not candidates:
            candidates = model_names

    return candidates


def get_available_model(image=False):
    """Return the currently selected model for text or vision."""
    candidates = get_candidate_models(image=image)
    return candidates[0] if candidates else None


def ask_ollama(instruction, text="", image=None):
    """Send a summarization request to local Ollama or Ollama Cloud, auto-selecting free models."""
    message = {"role": "user", "content": instruction}
    if text:
        message["content"] += f"\n\n<content>\n{text}\n</content>"
    if image:
        message["images"] = [image]

    is_image = bool(image)
    candidates = get_candidate_models(image=is_image)
    last_error = None
    last_status = None

    for model in candidates:
        payload = json.dumps({
            "model": model,
            "messages": [message],
            "stream": False,
            "options": {"num_predict": 1000},
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OLLAMA_API_KEY}",
        } if OLLAMA_API_KEY else {"Content-Type": "application/json"}

        req = Request(f"{OLLAMA_HOST}/api/chat", data=payload, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
                summary = result.get("message", {}).get("content", "").strip()
                if not summary:
                    continue
                # Clean any reasoning tags if present
                summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL).strip()
                _WORKING_MODEL_CACHE["vision" if is_image else "text"] = model
                return summary
        except HTTPError as exc:
            last_status = exc.code
            details = exc.read().decode("utf-8", errors="replace")
            try:
                details = json.loads(details).get("error", details)
            except json.JSONDecodeError:
                pass
            last_error = details
            _FAILED_MODELS.add(model)
            # Try next model if current model requires payment (402), is missing (404), or restricted (400, 403)
            if exc.code in (400, 402, 403, 404):
                continue
            raise RuntimeError(f"Ollama request failed: {details}") from exc
        except URLError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {OLLAMA_HOST}. Check your network connection or local Ollama server."
            ) from exc

    if is_image and last_status == 402:
        raise RuntimeError(
            "Ollama Cloud requires paid usage credits for image/vision models. "
            "Please paste text or upload a PDF instead to summarize for free using the auto-selected model, "
            "or add usage credits at https://ollama.com/plans."
        )
    if last_status == 402:
        raise RuntimeError(
            f"All available cloud models require usage credits: {last_error}. Visit https://ollama.com/plans to add credits."
        )
    raise RuntimeError(f"Ollama request failed: {last_error or 'No working model available.'}")


@app.route("/")
def index():
    return render_template("index.html", max_mb=MAX_UPLOAD_MB)


@app.route("/summarize", methods=["POST"])
def summarize():
    length = request.form.get("length", "medium")
    tone = request.form.get("tone", "neutral")
    text = (request.form.get("text") or "").strip()
    upload = request.files.get("file")

    if length not in LENGTHS or tone not in TONES:
        return jsonify(error="Choose a valid length and tone."), 400

    instruction = (
        f"Summarize the content below in {LENGTHS[length]}. "
        f"Use a {TONES[tone]} tone. "
        "Keep the key facts, names, numbers and decisions. "
        "Reply with the summary only, with no preamble."
    )

    source, filename = "text", None
    image = None
    content_text = text

    if upload and upload.filename:
        filename = upload.filename
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "pdf":
            source = "pdf"
            try:
                reader = PdfReader(upload)
                content_text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
            except (PdfReadError, OSError, ValueError) as exc:
                return jsonify(error=f"Could not read the PDF: {exc}"), 400
            if not content_text:
                return jsonify(error="This PDF has no extractable text. Upload an image or paste the text instead."), 400
        elif ext in IMAGE_TYPES:
            source = "image"
            image = base64.standard_b64encode(upload.read()).decode("utf-8")
            instruction = instruction.replace(
                "the content below", "the image below (read any text in it and describe what it shows)")
        else:
            return jsonify(error="Upload a PDF or an image (PNG, JPG, GIF, WebP)."), 400
    elif not text:
        return jsonify(error="Paste some text or upload a file first."), 400

    log_prompt(instruction, source, length, tone,
               text=content_text if source in ("text", "pdf") else None, filename=filename)

    try:
        summary = ask_ollama(instruction, content_text, image)
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 502

    return jsonify(summary=summary, source=source)


@app.route("/prompts")
def prompts():
    """Download the prompt log."""
    if not LOG_FILE.exists():
        LOG_FILE.write_text("# Prompt Log\n\nNo prompts yet.\n", encoding="utf-8")
    return send_file(LOG_FILE, mimetype="text/markdown", as_attachment=True,
                     download_name="prompts_log.md")


@app.errorhandler(413)
def too_large(_):
    return jsonify(error=f"File is too large. Maximum size is {MAX_UPLOAD_MB} MB."), 413


if __name__ == "__main__":
    app.run(debug=True)
