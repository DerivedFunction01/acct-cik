import subprocess
import time
import sys
from pathlib import Path

# CONFIGURATION
PYTHON_EXEC = sys.executable
LOG_FILE = "pipeline_run.log"

# Definition: (Script, Output_DB, Output_CSV)
PIPELINE_STAGES = [
    # 0. Attempt to cleanup tables
    ("prefilter_database.py", "prefiltered_data.db", "prefiltered.csv"),
    # 1. Drop simple nonusers
    ("prefilter_simple_nonuse.py", "refined_data.db", "prefiltered_refined.csv"),
    # 2. Tag each sentence
    ("prefilter_tagging.py", "tagged_data.db", "prefiltered_refined.csv"),
    # 3. Tag each sentence
    ("prefilter_evidence.py", "evidence_data.db", "prefiltered_refined.csv"),
    # 4. Classify
    ("classify_users.py", "classified_data.db", "classified_users.csv"),
]

# FINAL REPORT CONFIG: Compare first stage output to last stage output
FINAL_REPORT_CONFIG = {
    "enabled": True,
    "start_index": 0,  # Which pipeline stage's CSV to use as "start"
    "end_index": -1,  # Which pipeline stage's CSV to use as "end" (-1 = last)
    "report_name": "Final Attrition Report (Start vs End)",
}


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
    previous_csv = None
    stage_csvs = []  # Track all CSV outputs for final report

    for script, db_target, csv_target in PIPELINE_STAGES:
        if not Path(script).exists():
            log(f"❌ MISSING SCRIPT: {script}")
            sys.exit(1)

        # 1. Processing Step
        if not run_command([PYTHON_EXEC, script], f"Running {script}"):
            sys.exit(1)

        # 2. Export Step
        if Path(db_target).exists() and csv_target:
            run_command(
                [PYTHON_EXEC, "database_export.py", db_target, csv_target],
                f"Exporting {csv_target}",
            )

            stage_csvs.append(csv_target)

            # # 3. Analysis: Visual Sampling (HTML)
            # if not run_command(
            #     [PYTHON_EXEC, "run_analysis.py", "sample", db_target],
            #     f"Visual Sample: {db_target}",
            # ):
            #     log(
            #         f"⚠️ Non-critical error: Visual sampling failed for {db_target}. Continuing."
            #     )

            # # 4. Analysis: Diff Comparison (Excel)
            # if previous_csv and Path(previous_csv).exists():
            #     if not run_command(
            #         [
            #             PYTHON_EXEC,
            #             "run_analysis.py",
            #             "compare",
            #             previous_csv,
            #             csv_target,
            #         ],
            #         f"Compare: {previous_csv} vs {csv_target}",
            #     ):
            #         log(f"⚠️ Non-critical error: Comparison failed. Continuing.")

            # previous_csv = csv_target

        else:
            log(f"⚠️  Output DB {db_target} not found. Skipping export/analysis.")

        time.sleep(5)

    # # Final Summary Comparison (Dynamic)
    # log("=" * 60)
    # log("RUNNING FINAL SUMMARY ANALYSIS")

    # if FINAL_REPORT_CONFIG["enabled"] and len(stage_csvs) >= 2:
    #     start_idx = FINAL_REPORT_CONFIG["start_index"]
    #     end_idx = FINAL_REPORT_CONFIG["end_index"]

    #     # Resolve negative indices
    #     if end_idx < 0:
    #         end_idx = len(stage_csvs) + end_idx

    #     start_csv = stage_csvs[start_idx]
    #     end_csv = stage_csvs[end_idx]

    #     if Path(start_csv).exists() and Path(end_csv).exists():
    #         run_command(
    #             [
    #                 PYTHON_EXEC,
    #                 "run_analysis.py",
    #                 "compare",
    #                 start_csv,
    #                 end_csv,
    #             ],
    #             FINAL_REPORT_CONFIG["report_name"],
    #         )
    #     else:
    #         log(f"⚠️ Cannot generate final report: {start_csv} or {end_csv} not found.")
    # else:
    #     log("⚠️ Final report disabled or insufficient pipeline stages.")

    total_duration = time.time() - total_start
    log("=" * 60)
    log(f"🎉 PIPELINE COMPLETE in {total_duration/3600:.2f} hours")
    log("=" * 60)


if __name__ == "__main__":
    run_pipeline()
