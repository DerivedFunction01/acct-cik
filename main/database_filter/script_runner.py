import subprocess
import time
import sys
from pathlib import Path

# CONFIGURATION
PYTHON_EXEC = sys.executable
LOG_FILE = "pipeline_run.log"

# Definition: (Script, Output_DB, Output_CSV)
PIPELINE_STAGES = [
    # 1. Extraction & Refinement
    ("filter_database.py", "prepared_data.db", "1_prepared.csv"),
    # 2. Gatekeeper (Pass-through if using simple mode)
    ("roberta_merge.py", "hedge_data.db", "2_merged.csv"),
    # 3. Historical Cleaning
    ("year_deletion.py", "current_data.db", "3_current_year.csv"),
    # 4. Intent Filtering (Potential/Negative)
    ("active_use_filter.py", "active_data.db", "4_intent_filtered.csv"),
    # 5. Termination Logic
    ("termination_filter.py", "active_data2.db", "5_termination_filtered.csv"),
    # 6. Quantitative Zero
    ("notional_filter.py", "active_nonzero_data.db", "6_nonzero.csv"),
    # 7. Final Verification
    ("final_verification.py", "verified_active_data.db", "7_final_verified.csv"),
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
    log("STARTING 265K PRODUCTION PIPELINE")
    log("=" * 60)

    total_start = time.time()

    # Track previous CSV for automated comparison
    previous_csv = None

    for script, db_target, csv_target in PIPELINE_STAGES:
        if not Path(script).exists():
            log(f"❌ MISSING SCRIPT: {script}")
            sys.exit(1)

        # 1. Processing Step
        if not run_command([PYTHON_EXEC, script], f"Running {script}"):
            sys.exit(1)

        # 2. Export Step
        if Path(db_target).exists():
            run_command(
                [PYTHON_EXEC, "database_export.py", db_target, csv_target],
                f"Exporting {csv_target}",
            )

            # 3. Analysis: Visual Sampling (HTML)
            # Generates sample_view_{db_name}.html
            if not run_command(
                [PYTHON_EXEC, "run_analysis.py", "sample", db_target],
                f"Visual Sample: {db_target}",
            ):
                log(
                    f"⚠️ Non-critical error: Visual sampling failed for {db_target}. Continuing."
                )

            # 4. Analysis: Diff Comparison (Excel)
            if previous_csv and Path(previous_csv).exists():
                if not run_command(
                    [
                        PYTHON_EXEC,
                        "run_analysis.py",
                        "compare",
                        previous_csv,
                        csv_target,
                    ],
                    f"Compare: {previous_csv} vs {csv_target}",
                ):
                    log(f"⚠️ Non-critical error: Comparison failed. Continuing.")

            previous_csv = csv_target

        else:
            log(f"⚠️  Output DB {db_target} not found. Skipping export/analysis.")

        # Cooldown
        time.sleep(5)

    # Final Summary Comparison (Start vs End)
    log("=" * 60)
    log("RUNNING FINAL SUMMARY ANALYSIS")
    if Path("1_prepared.csv").exists() and Path("7_final_verified.csv").exists():
        run_command(
            [
                PYTHON_EXEC,
                "run_analysis.py",
                "compare",
                "1_prepared.csv",
                "7_final_verified.csv",
            ],
            "Generating Final Attrition Report (Start vs End)",
        )

    total_duration = time.time() - total_start
    log("=" * 60)
    log(f"🎉 PIPELINE COMPLETE in {total_duration/3600:.2f} hours")
    log("=" * 60)


if __name__ == "__main__":
    run_pipeline()
