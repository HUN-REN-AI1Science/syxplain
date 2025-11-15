import json
from datetime import datetime
from pathlib import Path


class StepLogger:
    """
    Logs arbitrary payloads from a multi-step process with automatic numbering.

    Each run creates a new folder:
        outputs/YYYYMMDD_HHMMSS/

    Each call to log_step(step_name, payload) writes:
        outputs/<run_id>/NNN_<step_name>.txt
    """

    def __init__(self, base_dir="outputs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)

        # Create unique run folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = self.base_dir / f"syxplain_run_{timestamp}"
        self.run_dir.mkdir()

        # Create folder for charts
        self.operator_selection_charts_dir = self.run_dir / "operator_selection_charts"
        self.operator_selection_charts_dir.mkdir()

        # Step counter
        self.step_num = 1

    def log_step(self, step_name: str, payload):
        """
        Saves payload into <run_dir>/NNN_<step_name>.txt.
        Automatically increases step counter.
        """

        # Format step number as 3 digits
        step_prefix = f"{self.step_num:03d}"

        filename = f"{step_prefix}_{step_name}.txt"
        file_path = self.run_dir / filename

        # Prepare payload
        if isinstance(payload, (dict, list)):
            text = json.dumps(payload, indent=4)
        else:
            text = str(payload)

        # Write file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)

        # Increment for next step
        self.step_num += 1

        return file_path

