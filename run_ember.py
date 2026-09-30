import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path

LOG_DIR = "logs"
Path(LOG_DIR).mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/ember.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

SCRIPTS = [
    ("pull_data.py",       "Pulling Oura data"),
    ("score_baseline.py",  "Scoring deviation"),
    ("summarize.py",       "Generating summary"),
    ("model_logreg.py",    "Training stress model / predicting today"),
]

def run(script: str, label: str) -> bool:
    logging.info(f"--- {label} ---")
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        logging.info(result.stdout.strip())
    if result.returncode != 0:
        logging.error(f"FAILED: {script}")
        logging.error(result.stderr.strip())
        return False
    return True

def main():
    logging.info(f"=== EMBER run started: {datetime.now().isoformat()} ===")
    for script, label in SCRIPTS:
        if not run(script, label):
            logging.error("Pipeline halted.")
            sys.exit(1)
    logging.info(f"=== EMBER run complete: {datetime.now().isoformat()} ===")

if __name__ == "__main__":
    main()