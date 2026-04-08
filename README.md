# CIS Capstone

A Flask web application that interviews nonprofit staff to surface powerful stories from their program work. Staff select a content goal (event promo, funder report, donor appeal, etc.) and a target audience, then answer a short guided interview. The app extracts five story elements — person, moment, tension, change, and outcome — and outputs them as structured JSON ready for content drafting.

The interview is conducted entirely by a local LLM running through [Ollama](https://ollama.com). No data leaves your machine.

---

## Prerequisites

- Python 3.12+
- [Ollama](https://ollama.com) installed and running locally

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/tjbrett03/CIS-Capstone.git
cd CIS-Capstone
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure your environment

```bash
cp .env.example .env
```

Open `.env` and set the following values:

| Variable | Required | Description |
|---|---|---|
| `FLASK_SECRET_KEY` | Yes | Any long random string. Used to sign session cookies. |
| `FLASK_DEBUG` | No | Set to `true` during development for auto-reload. Default: `false`. |
| `DEBUG_CONTEXT` | No | Set to `true` to show a debug panel with token usage and message history in the interview UI. Default: `false`. |
| `OLLAMA_URL` | No | URL of your Ollama instance. Default: `http://localhost:11434`. |
| `LLM_MODEL` | Yes | The Ollama model to use (e.g. `llama3.1:8b`). Must be pulled before running. |
| `LLM_NUM_CTX` | No | Context window size in tokens. Default: `16384`. Adjust based on your GPU VRAM. |
| `LLM_TEMPERATURE` | No | Sampling temperature. Lower = more focused. Default: `0.2`. |

To generate a secure secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Pull a model

The app requires a model to be available in Ollama before starting. We recommend `llama3.1:8b` for a good balance of quality and speed on consumer hardware:

```bash
ollama pull llama3.1:8b
```

Any chat model supported by Ollama will work. Set `LLM_MODEL` in your `.env` to match the model you pulled. To see what models are available locally:

```bash
ollama list
```

### 6. Make sure Ollama is running

Ollama runs as a background service. On Windows it starts automatically with the system tray app. You can verify it's running with:

```bash
ollama ps
```

---

## Running the App

```bash
python run.py
```

Visit `http://localhost:5000` in your browser.

---

## Running with Docker

```bash
docker compose up --build
```

Visit `http://localhost:5000` in your browser.

> **Note:** To reach Ollama running on your host machine from inside the container, set `OLLAMA_URL=http://host.docker.internal:11434` in your `.env`. This works on Mac, Windows, and Linux (the compose file adds the `host.docker.internal` alias automatically on Linux).

---

## How it works

1. Select a **content goal** (e.g. "Tell a Program Story") and a **target audience** (e.g. "Funders") on the home screen.
2. The app conducts a structured five-question interview via the local LLM, asking about the person, moment, tension, change, and outcome at the center of the story.
3. Once all five elements are collected, the model outputs a JSON object with the extracted story elements and raw quotes.
4. The JSON is saved to the `interviews/` directory and displayed in the UI.

The interview automatically locks after the extraction is complete. Use **Start Over** to begin a new interview with the same goal and audience.

---

## GPU Memory Notes

Context window size (`LLM_NUM_CTX`) significantly affects VRAM usage. The default of `16384` is tuned for `llama3.1:8b` on a 12GB GPU. If you have less VRAM or are using a larger model, lower this value. A typical interview uses well under 2,000 tokens, so even `4096` is more than sufficient.

To check what's loaded and how much memory it's using:

```bash
ollama ps
```
