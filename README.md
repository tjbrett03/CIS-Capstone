# CIS Capstone

A Flask web application that helps organizations write audience-specific content — including event promos, program stories, funder reports, and donor appeals — tailored to the right tone, length, and reading level for each audience.

## Prerequisites

- Python 3.12+
- pip

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/tjbrett03/CIS-Capstone.git
   cd CIS-Capstone
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Copy the example environment file and fill in your values:
   ```bash
   cp .env.example .env
   ```

## Running the App

```bash
python run.py
```

Visit `http://localhost:5000` in your browser.

## Running with Docker

```bash
docker compose up --build
```

Visit `http://localhost:5000` in your browser.