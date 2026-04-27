# CIS Capstone

A Flask web application that interviews nonprofit staff to surface powerful stories from their program work. Staff select a content goal and a target audience, then answer a short guided interview. The app extracts five story elements — person, moment, tension, change, and outcome — and passes them to Claude to generate a finished, audience-ready narrative.

The interview is conducted by a local LLM running through [Ollama](https://ollama.com). Extracted story data is sent to the Claude API for narrative generation. The finished narrative is scanned for PII and scored for readability before it is shown to the user.

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

### 4. Download the spaCy language model

Required for PII scanning. This only needs to be done once.

```bash
python -m spacy download en_core_web_lg
```

### 5. Configure your environment

```bash
cp .env.example .env
```

Open `.env` and set the following values:

| Variable | Required | Description |
|---|---|---|
| `FLASK_SECRET_KEY` | Yes | Any long random string. Used to sign session cookies. |
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key. Used to generate the final narrative via Claude. |
| `APP_PASSWORD` | Yes | Password required to access the application. |
| `LLM_MODEL` | Yes | The Ollama model to use (e.g. `llama3.1:8b`). Must be pulled before running. |
| `FLASK_DEBUG` | No | Set to `true` during development for auto-reload. Default: `false`. |
| `DEBUG_CONTEXT` | No | Set to `true` to show a debug panel with token usage and message history in the interview UI. Default: `false`. |
| `OLLAMA_URL` | No | URL of your Ollama instance. Default: `http://localhost:11434` for local dev. When running via Docker Compose this is automatically overridden to `http://ollama:11434`. |
| `LLM_NUM_CTX` | No | Context window size in tokens. Default: `16384`. Adjust based on your GPU VRAM. |
| `LLM_TEMPERATURE` | No | Sampling temperature. Lower = more focused. Default: `0.2`. |

To generate a secure secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 6. Pull a model

The app requires a model to be available in Ollama before starting. We recommend `llama3.1:8b` for a good balance of quality and speed on consumer hardware:

```bash
ollama pull llama3.1:8b
```

Any chat model supported by Ollama will work. Set `LLM_MODEL` in your `.env` to match the model you pulled. To see what models are available locally:

```bash
ollama list
```

### 7. Make sure Ollama is running

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

Docker runs both the app and Ollama as containers — no local Ollama install or spaCy download required. The spaCy model is downloaded automatically during the image build.

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

1. Select a **content goal** (e.g. "Appeal to a Donor") and a **target audience** (e.g. "Individual Donors") on the home screen.
2. The local LLM conducts a structured five-question interview, asking about the person, moment, tension, change, and outcome at the center of the story.
3. Once all five elements are collected, the local model extracts them into a JSON object and saves it to the `interviews/` directory.
4. The extracted story is sent to Claude (Sonnet 4.6), which generates a finished, audience-ready narrative based on the selected goal and audience.
5. The narrative is scanned for six categories of personally identifiable information — names, locations, relationship identifiers, legal details, health details, and immigration/legal status. Any flagged content is highlighted in amber with a plain-language explanation and suggested fix. The system warns but does not block; the staff member is the final decision-maker.
6. A Flesch Reading Ease score is calculated and compared against the target reading level for the selected audience. The result is shown alongside the narrative as a plain-language grade label.

The interview locks after the narrative is generated. Use **Start Over** to begin a new interview with the same goal and audience.

---

## Content Goals

| Goal | Description |
|---|---|
| Promote an Event | Drive registrations with a compelling, action-oriented summary |
| Promote a Program or Service | Build awareness; answer what it is, who it serves, and how to access it |
| Tell a Program Story | Create emotional connection through one real person's experience |
| Report Impact to a Funder | Open with a human story, support with data, connect outcomes to funder priorities |
| Appeal to a Donor | Lead with a specific moment, connect to reader values, close with a clear donation ask |
| Recruit a Volunteer | Lead with a specific moment, connect to reader's desire to contribute, close with a volunteer ask |

---

## GPU Memory Notes

Context window size (`LLM_NUM_CTX`) significantly affects VRAM usage. The default of `16384` is tuned for `llama3.1:8b` on a 12GB GPU. If you have less VRAM or are using a larger model, lower this value. A typical interview uses well under 2,000 tokens, so even `4096` is more than sufficient.

To check what's loaded and how much memory it's using:

```bash
ollama ps
```
