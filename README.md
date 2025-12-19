# Syxplain

[![CI/CD](https://github.com/HUN-REN-AI1Science/syxplain/actions/workflows/deploy.yml/badge.svg)](https://github.com/HUN-REN-AI1Science/syxplain/actions/workflows/deploy.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/release/python-3100/)
[![React 18.2.0](https://img.shields.io/badge/react-18.2.0-61dafb.svg)](https://react.dev/)

This is a proof of concept system which uses state of the art symbolic regression models to predict a selected variable in a dataset and explain the predicted equations in natural language using large language models. Setting the hiperparameters of the symbolic regression can be tedious, so here we use an LLM withvision capabilities to analyze the dataset and suggest hiperparameters for the symbolic regression model.

## Prerequisites

- Anaconda (Miniconda is suggested)
- GNUPG for credential management
- Gemini API Key (encrypted using gnupg and stored in `credentials/api_key_gemini.gpg`)

The system has been developed and tested on Linux and intented to be used on a Linux environment as a server behind a reverse proxy.

## Installation
After cloning the repository, create a conda environment and install the dependencies. The following lines works only if your current directory is the root of the cloned repository.

```bash
conda env create -f syxplain_environment.yml
conda activate syxplain
```
## Web Application

The Syxplain application consists of a Python backend (FastAPI) and a React frontend.

### Environment Variables

Before running the application, you need to set up the environment variables.
Copy `.env.example` to `.env` and fill in the values.

```bash
cp .env.example .env
```

**Required Variables:**
- `OPENAI_API_KEY`: Your API key for the LLM service.
- `OPENAI_API_BASE`: Base URL for the LLM API.
- `OPENAI_MODEL_NAME`: Name of the model to use.
- `DEEP_RESEARCH_MODEL`: Comma-separated list of deep research models available for selection. Users can choose from these models when running Deep Analysis. Example: `o4-mini-deep-research,perplexity-deep-research,o3-deep-research`. If only one model is configured, it will be auto-selected.
- `DEEP_RESEARCH_API_KEY`: API key for the deep research model (required for Deep Analysis mode).
- `DEEP_RESEARCH_API_BASE`: Base URL for the deep research API (used in Deep Analysis mode).
- `DATABASE_URL`: Connection string for your PostgreSQL database.
- `SUPABASE_URL`: URL of your Supabase project.
- `SUPABASE_JWT_SECRET`: JWT secret for Supabase authentication.
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key for GDPR account deletion.
- `VITE_SUPABASE_URL`: Same as `SUPABASE_URL` (for frontend).
- `VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY`: Supabase publishable key (for frontend).
- `VITE_SUPABASE_ANON_KEY`: Supabase anon key (for frontend).

**Optional Variables (Performance Tuning):**
- `SHAP_SUBSAMPLE_FRACTION`: Fraction of data to use for SHAP calculations (default: `0.1` = 10%).
- `SHAP_SUBSAMPLE_MIN`: Minimum number of samples for SHAP (default: `1000`).
- `SHAP_SUBSAMPLE_MAX`: Maximum number of samples for SHAP (default: `5000`).
- `ANALYSIS_TIMEOUT_HOURS`: Maximum hours before an analysis is killed with timeout status (default: `24`). Set to `0` to disable.

**Optional Variables (LLM Tracing with Langfuse):**
- `LANGFUSE_PUBLIC_KEY`: Your Langfuse public key for tracing.
- `LANGFUSE_SECRET_KEY`: Your Langfuse secret key for tracing.
- `LANGFUSE_BASE_URL`: Langfuse API URL (default: `https://cloud.langfuse.com`).

### Running with Docker Compose (Recommended)

The easiest way to run the full stack is using Docker Compose.

```bash
docker-compose up --build
```

This will start:
- Backend on `http://localhost:8000`
- Frontend on `http://localhost:8080`

### Running Backend with Docker

If you want to run only the backend container:

```bash
docker build -t syxplain-backend -f backend/Dockerfile .
docker run -d \
  --name syxplain-backend \
  --env-file .env \
  -p 8000:8000 \
  syxplain-backend
```

### Running as a Systemd Service (Linux)

To run the backend as a systemd service using a Python virtual environment:

1.  **Create a virtual environment:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python -c "import juliapkg; juliapkg.resolve()"
    ```

2.  **Create a systemd service file:**
    Create `/etc/systemd/system/syxplain.service` with the following content (adjust paths and user):

    ```ini
    [Unit]
    Description=Syxplain Backend Service
    After=network.target

    [Service]
    User=your_user
    Group=your_group
    WorkingDirectory=/path/to/syxplain
    EnvironmentFile=/path/to/syxplain/.env
    ExecStart=/path/to/syxplain/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

3.  **Enable and start the service:**

    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable syxplain
    sudo systemctl start syxplain
    ```

### Local Development

For development, you can run the backend and frontend separately.

**Database:**

Start only the PostgreSQL database from docker-compose:

```bash
docker-compose up -d postgres
```

This will start PostgreSQL 18 on `localhost:5432` with:
- User: `syxplain`
- Password: `syxplain`
- Database: `syxplain`

**Backend:**

1.  Create and activate a virtual environment (or use Conda).
2.  Install dependencies: `pip install -r requirements.txt`
3.  Install Julia packages: `python -c "import juliapkg; juliapkg.resolve()"`
4.  Run the server:

    ```bash
    # Ensure .env variables are exported or use a tool like python-dotenv
    export $(grep -v '^#' .env | xargs)
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
    ```

**Frontend:**

1.  Navigate to the frontend directory: `cd frontend`
2.  Install dependencies: `npm install`
3.  Start the development server:

    ```bash
    npm run dev
    ```
    The frontend will be available at `http://localhost:5173` (by default).
