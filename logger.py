import json
import logging
import os
import yaml
from datetime import datetime
from pathlib import Path
from backend.database import SessionLocal, RunArtifact
import langchain


# Load progress config from YAML
def load_progress_config():
    """Load progress phase configuration from YAML file."""
    config_path = Path(__file__).parent / "backend" / "progress_config.yaml"
    if not config_path.exists():
        # Fallback if running from different directory
        config_path = Path(__file__).parent.parent / "backend" / "progress_config.yaml"
    if not config_path.exists():
        config_path = Path("backend/progress_config.yaml")

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('phases', [])
    except Exception as e:
        logging.warning(f"Failed to load progress_config.yaml: {e}. Using defaults.")
        return []


def get_progress_weights():
    """Build progress weights dictionary from YAML config."""
    phases = load_progress_config()
    weights = {}
    for phase in phases:
        weights[phase['name']] = phase['progress_end']
    return weights


# Cache the config at module load
_PROGRESS_PHASES = None
_PROGRESS_WEIGHTS = None


def get_cached_progress_config():
    """Get cached progress config, loading once."""
    global _PROGRESS_PHASES, _PROGRESS_WEIGHTS
    if _PROGRESS_PHASES is None:
        _PROGRESS_PHASES = load_progress_config()
        _PROGRESS_WEIGHTS = {p['name']: p['progress_end'] for p in _PROGRESS_PHASES}
    return _PROGRESS_PHASES, _PROGRESS_WEIGHTS


def configure_debug_logging():
    """
    Configures debug logging for LangChain and LangGraph.
    """
    # Enable LangChain debug mode (includes chat requests)
    langchain.debug = True

    # Enable LangGraph debug logging
    logging.getLogger("langgraph").setLevel(logging.DEBUG)


class DateFolderRotatingFileHandler(logging.FileHandler):
    """
    A handler that rotates log files into date-stamped folders.
    """
    def __init__(self, base_dir, filename, mode='a', encoding=None, delay=False):
        self.base_dir = Path(base_dir)
        self.filename = filename
        self.current_date = datetime.now().strftime("%Y-%m-%d")

        # Ensure initial directory exists
        log_dir = self.base_dir / self.current_date
        log_dir.mkdir(parents=True, exist_ok=True)

        filepath = log_dir / self.filename
        super().__init__(str(filepath), mode, encoding, delay)

    def emit(self, record):
        # Check if date has changed
        new_date = datetime.now().strftime("%Y-%m-%d")
        if new_date != self.current_date:
            self.current_date = new_date

            # Close current file
            self.close()

            # Create new directory
            log_dir = self.base_dir / self.current_date
            log_dir.mkdir(parents=True, exist_ok=True)

            # Open new file
            self.baseFilename = str(log_dir / self.filename)
            self.stream = self._open()

        super().emit(record)

def configure_logging(log_dir="logs", log_filename="syxplain.log", level=logging.INFO):
    """
    Configures the root logger to log to console and rolling files.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers to avoid duplicates
    root_logger.handlers = []

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root_logger.addHandler(console_handler)

    # File Handler
    file_handler = DateFolderRotatingFileHandler(log_dir, log_filename)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root_logger.addHandler(file_handler)

    logging.info(f"Logging configured. Logs will be saved to {log_dir}/<date>/{log_filename}")


class StepLogger:
    """
    Logs arbitrary payloads from a multi-step process to stdio and tracks progress.
    Loads progress weights dynamically from progress_config.yaml.
    """

    def __init__(self, base_dir="outputs", run_id=None, total_steps=None):
        self.logger = logging.getLogger(__name__)
        self.run_id = run_id
        self.step_num = 1
        self.current_progress = 0

        # Load progress weights from YAML config
        _, self.progress_weights = get_cached_progress_config()

        # We don't use base_dir anymore, but keeping signature compatible
        # Ensure run_id is provided for DB logging
        if not self.run_id:
            self.logger.warning("StepLogger initialized without run_id! DB logging will fail.")

    def set_progress(self, progress: int):
        """
        Explicitly set progress percentage (0-99). Use for long operations
        where you want more control over progress updates.
        """
        if not self.run_id:
            return

        progress = min(99, max(0, progress))
        self.current_progress = progress

        from backend.database import Run as DbRun
        db = SessionLocal()
        try:
            run = db.query(DbRun).filter(DbRun.id == self.run_id).first()
            if run:
                run.progress = progress
                db.commit()
                self.logger.info(f"Progress updated: {progress}%")
        except Exception as e:
            self.logger.error(f"Failed to set progress for {self.run_id}: {e}")
        finally:
            db.close()

    def _update_progress(self, step_name: str):
        """
        Updates the progress percentage in the database based on step name weights.
        """
        if not self.run_id:
            return

        # Get weighted progress for this step, or use current + 1 as fallback
        if step_name in self.progress_weights:
            progress = self.progress_weights[step_name]
        else:
            # For unknown steps, increment by 1 from current
            progress = min(99, self.current_progress + 1)

        # Ensure progress only goes up
        progress = max(progress, self.current_progress)
        progress = min(99, progress)
        self.current_progress = progress

        from backend.database import Run as DbRun
        db = SessionLocal()
        try:
            run = db.query(DbRun).filter(DbRun.id == self.run_id).first()
            if run:
                run.progress = progress
                db.commit()
                self.logger.debug(f"Updated progress for run {self.run_id}: {progress}%")
        except Exception as e:
            self.logger.error(f"Failed to update progress for {self.run_id}: {e}")
        finally:
            db.close()

    def log_step(self, step_name: str, payload):
        """
        Logs step information to stdio and updates progress.
        """
        # Prepare payload for display
        if not isinstance(payload, (dict, list, str, int, float, bool)):
             payload = str(payload)

        # Log to console (stdio) - but limit size to prevent buffer overflow
        self.logger.info(f"Step {self.step_num}: {step_name}")

        # For large payloads, only log a summary to avoid BlockingIOError
        if isinstance(payload, (dict, list)):
            payload_str = json.dumps(payload, indent=2)
            if len(payload_str) > 1000:  # Limit to 1000 chars
                self.logger.info(f"Payload size: {len(payload_str)} chars (truncated for display)")
                self.logger.info(payload_str[:1000] + "\n... (truncated)")
            else:
                self.logger.info(payload_str)
        else:
            payload_str = str(payload)
            if len(payload_str) > 1000:
                self.logger.info(f"Payload size: {len(payload_str)} chars (truncated for display)")
                self.logger.info(payload_str[:1000] + "\n... (truncated)")
            else:
                self.logger.info(payload_str)

        # Update progress in database
        self._update_progress(step_name)

        # Increment for next step
        self.step_num += 1

    def log_artifact(self, filename: str, content: bytes, media_type: str = None):
        """
        Saves an artifact (file/image) to the run_artifacts table.
        """
        if not self.run_id:
            return

        db = SessionLocal()
        try:
            artifact = RunArtifact(
                run_id=self.run_id,
                filename=filename,
                content=content,
                media_type=media_type
            )
            db.add(artifact)
            db.commit()
            self.logger.info(f"Artifact {filename} saved to DB")
        except Exception as e:
            self.logger.error(f"Failed to log artifact {filename} to DB: {e}")
        finally:
            db.close()

