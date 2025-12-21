---
description: Guide for modifying the core analysis graph and worker logic
---

# Development: Analysis Graph (syxplain_lib)

The core analysis logic resides in `syxplain_lib.py`, which implements a LangGraph workflow. It is designed to run in two modes:
1.  **Backend Mode**: Invoked by `backend/workers/analysis_worker.py`. Logs progress to DB via `ProgressTracker`.
2.  **CLI Mode**: Invoked by `syxplain.py`. Runs independently with dummy logging.

## Key Components

### 1. `syxplain_lib.py`
- **State**: TypedDict defining the graph state.
- **Nodes**: Functions like `data_summary`, `llm_pysr_config_generator`, `pysr_executor`.
- **Graph**: `StateGraph` definition in `run_syxplain`.
- **Dependencies**: Imports services from `backend.services.llm_service`.

### 2. `backend/workers/analysis_worker.py`
- Handles process lifecycle (multiprocessing).
- Initializes environment (Logging, Database, Langfuse).
- **Crucial**: Passes `ProgressTracker` instance (as `state["logger"]`) to `syxplain_lib` to enable DB updates.

### 3. `syxplain.py` (CLI)
- Minimal entry point for local testing.
- Sets up simplified state.
- Does NOT pass a logger, triggering fallback logic in `syxplain_lib.py`.

## Modifying Logic

### Adding a Step
1.  Define a new node function in `syxplain_lib.py`: `def my_node(state: State) -> State`.
2.  Use `state["logger"].log_step(...)` for progress updates.
3.  Add node to `StateGraph` in `run_syxplain`.
4.  Add edge (connection) to the graph.

### Modifying LLM Calls
- **Do not** implement raw LLM calls in `syxplain_lib.py`.
- Implement them in `backend/services/llm_service.py` and import the function.
- This ensures Langfuse tracing and standard configuration are used.

### Testing Changes
- **Quick Test (CLI)**: Run `python syxplain.py` (Requires local `.env` setup).
- **Full Test (Backend)**: Start server, trigger analysis via API, check `analysis_worker` logs.
