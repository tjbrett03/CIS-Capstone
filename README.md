# CIS Capstone

A Flask web application that interviews nonprofit staff to surface powerful stories from their program work. Staff select a content goal (event promo, funder report, donor appeal, etc.) and a target audience, then answer a short guided interview. The app extracts five story elements — person, moment, tension, change, and outcome — and passes them to Claude to generate a finished, audience-ready narrative.

The interview is conducted by a local LLM running through [Ollama](https://ollama.com). Extracted story data is sent to the Claude API for narrative generation.

---

## Prerequisites

**Local (no Docker):**
- Python 3.12+
- [Ollama](https://ollama.com) installed and running locally

**Docker:**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with WSL2 backend enabled
- NVIDIA drivers (if using GPU passthrough)

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
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key. Used to generate the final narrative via Claude. |
| `FLASK_DEBUG` | No | Set to `true` during development for auto-reload. Default: `false`. |
| `DEBUG_CONTEXT` | No | Set to `true` to show a debug panel with token usage and message history in the interview UI. Default: `false`. |
| `OLLAMA_URL` | No | URL of your Ollama instance. Default: `http://localhost:11434` for local dev. When running via Docker Compose this is automatically overridden to `http://ollama:11434`. |
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

Docker runs both the app and Ollama as containers — no local Ollama install required.

### 1. Start the stack

```bash
docker compose up --build -d
```

### 2. Pull the model into the Ollama container

On first run, you need to pull the model into the Ollama container. This only needs to be done once — the model is stored in a named Docker volume and persists across restarts.

```bash
docker compose exec ollama ollama pull llama3.1:8b
```

### 3. Open the app

Visit `http://localhost:5000` in your browser.

### GPU passthrough

GPU passthrough is enabled by default in `docker-compose.yml` for NVIDIA GPUs.

**Windows (Docker Desktop):** Requires the WSL2 backend and NVIDIA drivers. No additional toolkit install needed.

**Linux:** Requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) in addition to NVIDIA drivers:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

**CPU-only (no GPU):** Comment out or remove the `deploy` block in `docker-compose.yml`, otherwise Docker will error if it can't find an NVIDIA runtime.

To verify the GPU is accessible before starting the stack:

```bash
docker run --rm --gpus all nvidia/cuda:12.3.1-base-ubuntu22.04 nvidia-smi
```

---

## How it works

1. Select a **content goal** (e.g. "Tell a Program Story") and a **target audience** (e.g. "Funders") on the home screen.
2. The app conducts a structured five-question interview via the local LLM, asking about the person, moment, tension, change, and outcome at the center of the story.
3. Once all five elements are collected, the local model extracts them into a JSON object and saves it to the `interviews/` directory.
4. The extracted story is sent to Claude, which generates a finished, audience-ready narrative based on the selected goal and audience.
5. The narrative is displayed in the UI, ready to copy and paste.

The interview automatically locks after the narrative is generated. Use **Start Over** to begin a new interview with the same goal and audience.

---

## Upcoming

- **PII detection and removal** — strip names, locations, and other identifying details from extracted story data before it is sent to the Claude API
- **Flesch readability score** — calculate and display a readability score for the generated narrative
- **UI cleanup** — general interface improvements and polish

---

## GPU Memory Notes

Context window size (`LLM_NUM_CTX`) significantly affects VRAM usage. The default of `16384` is tuned for `llama3.1:8b` on a 12GB GPU. If you have less VRAM or are using a larger model, lower this value. A typical interview uses well under 2,000 tokens, so even `4096` is more than sufficient.

To check what's loaded and how much memory it's using:

```bash
ollama ps
```
