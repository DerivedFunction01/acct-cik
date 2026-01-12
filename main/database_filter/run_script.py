import subprocess
import time
import sys
from pathlib import Path

# CONFIGURATION
PYTHON_EXEC = sys.executable
LOG_FILE = "pipeline_run.log"

# Definition: (Script, additonal args)
PIPELINE_STAGES = [
    # 0. Filter and Parse
    ("prefilter_database.py", None),
    # 2. Tag each sentence
    ("prefilter_tagging.py",  None),
    # 3. Tag each sentence
    ("prefilter_evidence.py", None),
    # 4. Classify
    ("classify_users.py", None),
    # 5. Export
    ("database_export.py", "classified_data.db"),
]

def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def run_command(cmd_list, description):
    log(f"🚀 {description}...")
    t0 = time.time()
    try:
        subprocess.run(cmd_list, check=True)
        log(f"   ✓ Finished in {(time.time()-t0)/60:.2f} min")
        return True
    except subprocess.CalledProcessError as e:
        log(f"❌ FAILED: {' '.join(cmd_list)}")
        return False


def run_pipeline():
    log("=" * 60)
    log("STARTING PIPELINE")
    log("=" * 60)

    total_start = time.time()
    
    for script, arg in PIPELINE_STAGES:
        if not Path(script).exists():
            log(f"❌ MISSING SCRIPT: {script}")
            sys.exit(1)

        # 1. Processing Step
        if not run_command([PYTHON_EXEC, script, arg], f"Running {script}"):
            sys.exit(1)

        time.sleep(5)


    total_duration = time.time() - total_start
    log("=" * 60)
    log(f"🎉 PIPELINE COMPLETE in {total_duration/3600:.2f} hours")
    log("=" * 60)


if __name__ == "__main__":
    run_pipeline()
