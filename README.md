# AI Summarizer

Paste text, or upload a PDF or photo, and get a summary in the length and tone you choose.
Every prompt is saved to `prompts_log.md`.

## Setup

1. Install Python 3.9+ and create an Ollama Cloud API key at https://ollama.com/settings/keys
2. In this folder:

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Open `.env` and set your `OLLAMA_API_KEY` (or leave default for local Ollama).
Models are automatically detected from your available Ollama models (no model configuration needed in `.env`).

5. Run the app:

```bash
python app.py
```

6. Open http://127.0.0.1:5000

## Project structure

```
app.py              Flask backend (summarize, prompt logging)
templates/index.html  Page
static/style.css      Styling
static/script.js      Tabs, upload preview, API calls
prompts_log.md        Auto-created log of every prompt
```

## Notes

- Text and PDFs are summarized by the auto-selected free Ollama model. PDFs are text-extracted locally.
- Upload limit is 10 MB (change `MAX_UPLOAD_MB` in `app.py`).
- Ollama Cloud requires the API key in `.env`; it is never sent to the browser.
- You can change `OLLAMA_HOST` in `.env` if using a local or custom instance.
- Don't share `prompts_log.md` if you paste private emails, since it stores the pasted text.
