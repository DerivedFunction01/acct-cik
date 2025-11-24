import subprocess
import time
import sys
from pathlib import Path

# CONFIGURATION
PYTHON_EXEC = sys.executable
LOG_FILE = "pipeline_run.log"

# Format: (Script to Run, Output DB Name, Output CSV Name)
PIPELINE_STAGES = [
    # Stage 1: Regex & Structure (The Heavy Lift)
    ("filter_database.py", "prepared_data.db", "1_prepared.csv"),
    # Stage 2: Merge/Gatekeeper
    ("roberta_merge.py", "hedge_data.db", "2_merged.csv"),
    # Stage 3: Historical Cleaning
    ("year_deletion.py", "current_data.db", "3_current_year.csv"),
    # Stage 4: Linguistic Intent
    ("active_use_filter.py", "active_data.db", "4_intent_filtered.csv"),
    # Stage 5: Termination Logic
    ("termination_filter.py", "active_data2.db", "5_termination_filtered.csv"),
    # Stage 6: Quantitative Zero
    ("notional_filter.py", "active_nonzero_data.db", "6_nonzero.csv"),
    # Stage 7: Final Verification
    ("final_verification.py", "verified_active_data.db", "7_final_verified.csv"),
]


def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def run_pipeline():
    log("=" * 60)
    log("STARTING 265K PRODUCTION RUN WITH CHECKPOINT EXPORTS")
    log("=" * 60)

    total_start = time.time()

    for script, db_target, csv_target in PIPELINE_STAGES:
        # 1. Run the Processing Script
        if not Path(script).exists():
            log(f"❌ MISSING SCRIPT: {script}")
            sys.exit(1)

        log(f"🚀 RUNNING: {script}...")
        t0 = time.time()
        try:
            subprocess.run([PYTHON_EXEC, script], check=True)
            log(f"   ✓ Finished {script} in {(time.time()-t0)/60:.2f} min")
        except subprocess.CalledProcessError:
            log(f"❌ CRITICAL FAILURE in {script}")
            sys.exit(1)

        # 2. Run the Export immediately
        if Path(db_target).exists():
            log(f"   💾 Exporting {db_target} -> {csv_target}...")
            try:
                # Call database_export.py with arguments
                subprocess.run(
                    [PYTHON_EXEC, "database_export.py", db_target, csv_target],
                    check=True,
                )
            except subprocess.CalledProcessError:
                log(f"⚠️  Export failed for {db_target}, continuing pipeline...")
        else:
            log(f"⚠️  DB {db_target} not found. Skipping export.")

        # 3. Cooldown (Let OS reclaim file handles)
        time.sleep(5)

    total_duration = time.time() - total_start
    log("=" * 60)
    log(f"🎉 PIPELINE COMPLETE in {total_duration/3600:.2f} hours")
    log("=" * 60)


if __name__ == "__main__":
    run_pipeline()
