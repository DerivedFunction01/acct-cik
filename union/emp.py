# %%
import pandas as pd

emp_df = pd.read_csv("employee_temp.csv")

# Clean and convert emp to whole numbers
emp_df = emp_df[emp_df["cik"].notna()].copy()

emp_df["emp"] = (
    (emp_df["emp"].astype(str).str.replace(",", "", regex=False).astype(float) * 1000)
    .round()
    .astype("Int64")
)

# Diagnostics
diag = (
    emp_df.groupby("cik")
    .agg(
        years_present=("year", "count"),
        min_year=("year", "min"),
        max_year=("year", "max"),
        gaps=("year", lambda x: (max(x) - min(x) + 1) - len(x)),
        emp_min=("emp", "min"),
        emp_max=("emp", "max"),
        emp_std=("emp", "std"),
    )
    .reset_index()
)

# Convert cik to int
diag["cik"] = diag["cik"].astype("Int64")


# Classification logic
def classify(row):
    # D: Only truly unusable cases (no employment data at all)
    if pd.isna(row["emp_min"]) or pd.isna(row["emp_max"]):
        return "D"

    # Everything else passes - you have at least one employment number to use as reference
    if row["years_present"] >= 1:
        return "PASS"

    return "D"


diag["class"] = diag.apply(classify, axis=1)

# Export only firms needing manual lookup (no employment data)
manual_needed = diag[diag["class"] == "D"]
manual_needed.to_csv("firms_needing_manual_employment.csv", index=False)

print(f"Total firms: {len(diag)}")
print(f"Firms needing manual lookup: {len(manual_needed)}")
print(f"Usable firms: {len(diag) - len(manual_needed)}")

# %%
# Process the usable employment data - interpolate and fill gaps
emp_df = emp_df.sort_values(["cik", "year"]).reset_index(drop=True)

emp_df["emp"] = emp_df.groupby("cik", group_keys=False)["emp"].apply(
    lambda s: s.interpolate()
)

emp_df["emp"] = emp_df.groupby("cik", group_keys=False)["emp"].apply(
    lambda s: s.ffill(limit=2).bfill(limit=2)
)
emp_df["cik"] = emp_df["cik"].astype("Int64")
emp_df["year"] = emp_df["year"].astype("Int64")
emp_df["emp"] = emp_df["emp"].astype("Int64")

# Save the processed employment data
emp_df.to_csv("employee_processed.csv", index=False)

print("\nEmployment data processing complete!")
print(f"Processed records: {len(emp_df)}")

# %%
