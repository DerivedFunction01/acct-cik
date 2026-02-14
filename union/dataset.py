# %%
import pandas as pd

population = pd.read_excel("population.xls", header=3)
population = population.drop(columns=["Indicator Name", "Indicator Code"])
# %%
year_cols = [col for col in population.columns if col.isdigit()]
population["last_known_population"] = population[year_cols].bfill(axis=1).iloc[:, -1]
pop_final = population[["Country Code", "last_known_population", "Country Name"]]

# %%
codes_conv = pd.read_excel("Country Codes.xlsx", header=None)
codes_conv.columns = ["name", "alpha2", "Country Code"]
# %%
pop_merged = pop_final.merge(codes_conv[["alpha2", "Country Code"]], how="left")
pop_merged = pop_merged.dropna(subset=["alpha2"])
# %%
gdp = pd.read_excel("gdp.xls", header=3)
gdp = gdp.drop(columns=["Indicator Name", "Indicator Code"])
# %%
gdp_year_cols = [col for col in gdp.columns if col.isdigit()]
gdp["last_known_gdp"] = gdp[gdp_year_cols].bfill(axis=1).iloc[:, -1]
gdp["last_known_gdp"] = gdp["last_known_gdp"].fillna(1)
gdp_final = gdp[["Country Code", "Country Name", "last_known_gdp"]]
# %%
gdp_merged = gdp_final.merge(codes_conv[["alpha2", "Country Code"]], how="left")
gdp_merged = gdp_merged.dropna(subset=["alpha2"]).reset_index(drop=True)
# %%
merged_final = pop_merged.merge(gdp_merged[["Country Code", "last_known_gdp"]], how="left")
merged_final["gdp_per_capita"] = round(merged_final["last_known_gdp"] / merged_final["last_known_population"], 2)

# %%
world_pop = merged_final["last_known_population"].sum()
merged_final["pop_pct"] = (
    merged_final["last_known_population"] / world_pop * 100
).round(6)

# %%
world_gdp = merged_final["last_known_gdp"].sum()
merged_final["gdp_pct"] = merged_final["last_known_gdp"] / world_gdp
merged_final["gdp_pct"] = (merged_final["last_known_gdp"] / world_gdp * 100).round(6)
# %%
# Keep only the 2 digit code and the pct
pop_gdp = merged_final[["alpha2", "pop_pct", "gdp_pct"]]
pop_gdp.columns = ["code", "population_pct", "gdp_pct"]
print(len(pop_gdp))
manual_rows = {
    # Example: Taiwan (TW)
    # Values are in 0–1 scale (not 0–100)
    "TW": {"gdp_pct": 0.0084, "population_pct": 0.0029},
    "XK": {"gdp_pct": 0.0001, "population_pct": 0.00022},
    "GG": {"gdp_pct": 0.000008, "population_pct": 0.000035},
    "JE": {"gdp_pct": 0.000013, "population_pct": 0.000073},
}


man_pop_gdp = pd.DataFrame.from_dict(manual_rows, orient="index").reset_index()
man_pop_gdp.columns = ["code", "gdp_pct", "population_pct"]

# Ensure column order matches pop_gdp
man_pop_gdp = man_pop_gdp[["code", "population_pct", "gdp_pct"]]

# Append to pop_gdp
pop_gdp = pd.concat([pop_gdp, man_pop_gdp], ignore_index=True)
# %%
cb_df = pd.read_excel("cb_rate.xlsx")
cb = cb_df[cb_df["indicator.label"] == "Collective bargaining coverage rate (%)"]
cb_avg = (
    cb_df[cb_df["indicator.label"] == "Collective bargaining coverage rate (%)"]
    .groupby("ref_area.label", as_index=False)
    .agg(cb_rate=("obs_value", "mean"))
)
cb_avg["cb_rate"] = cb_avg["cb_rate"].round(6)
union_df = pd.read_excel("union_rate.xlsx")
union = union_df[union_df["indicator.label"] == "Trade union density rate (%)"]
union_avg = union.groupby("ref_area.label", as_index=False).agg(
    union_rate=("obs_value", "mean")
)
union_avg["union_rate"] = union_avg["union_rate"].round(6)
cb_union = cb_avg.merge(union_avg, on="ref_area.label", how="outer")
cb_union["cb_rate"] = cb_union["cb_rate"].fillna(cb_union["union_rate"])
cb_union["union_rate"] = cb_union["union_rate"].fillna(cb_union["cb_rate"])
cb_union["labor_rate"] = cb_union[["cb_rate", "union_rate"]].mean(axis=1).round(6)
cb_union.rename(
    columns={
        "ref_area.label": "name",
    },
    inplace=True,
)
cb_union.head()

# %%
cb_union = cb_union.merge(
    codes_conv[["name", "alpha2"]],  how="left"
)
# %%
import difflib

# --- Fuzzy match helper ---
iso_names = codes_conv["name"].tolist()


def fuzzy_match(name, choices, cutoff=0.6):
    matches = difflib.get_close_matches(name, choices, n=1, cutoff=cutoff)
    return matches[0] if matches else None


# --- Add fuzzy-matched ISO name ---
cb_union["country_fuzzy"] = cb_union["name"].apply(
    lambda x: fuzzy_match(x, iso_names)
)
# %%
# --- Merge using fuzzy name to get alpha2 ---
cb_union_merged = cb_union.merge(
    codes_conv[["name", "alpha2"]], left_on="country_fuzzy", right_on="name", how="left"
)
cb_union_merged.drop(columns=["name_y", "alpha2_y", "country_fuzzy"], inplace=True)
cb_union_merged.rename(columns={"name_x": "name", "alpha2_x": "alpha2"}, inplace=True)

# %%
from defs.region_regex import COMPOSITE_REGION_MAP

region_fallback = {}

for region, codes in COMPOSITE_REGION_MAP.items():
    subset = cb_union[cb_union["alpha2"].isin(codes)]
    if not subset.empty:
        region_fallback[region] = subset["labor_rate"].mean()

alpha2_to_region = {}

for region, codes in COMPOSITE_REGION_MAP.items():
    for code in codes:
        alpha2_to_region.setdefault(code, []).append(region)
# %%

# --- Merge with GDP/Population table ---
full_df = pop_gdp.merge(
    cb_union_merged, left_on="code", right_on="alpha2", how="left"
)

# --- Clean up ---
full_df = full_df.drop(columns=["alpha2"])

full_df["region"] = full_df["code"].apply(lambda c: alpha2_to_region.get(c, [None])[0])
full_df["labor_rate"] = full_df.apply(
    lambda row: (
        region_fallback.get(row["region"])
        if pd.isna(row["labor_rate"]) and row["region"] in region_fallback
        else row["labor_rate"]
    ),
    axis=1,
)

# %%
from sklearn.linear_model import LinearRegression

train = full_df[full_df["labor_rate"].notna()]
X_train = train[["population_pct", "gdp_pct"]]
y_train = train["labor_rate"]

model = LinearRegression()
model.fit(X_train, y_train)

missing = full_df[full_df["labor_rate"].isna()]
X_missing = missing[["population_pct", "gdp_pct"]]

preds = model.predict(X_missing)

full_df.loc[full_df["labor_rate"].isna(), "labor_rate"] = preds.round(6)
# Labor rate back to decimal instead of pct
full_df["labor_rate"] = full_df["labor_rate"] / 100
region_stats = (
    full_df.groupby("region")["labor_rate"]
    .agg(["mean", "median", "std", "count"])
    .sort_values("mean", ascending=False)
)
full_df = full_df.drop(columns=["cb_rate", "union_rate", "name", "region"])

# %%
print(full_df.head())
print(full_df.describe())
print(region_stats)

full_df.to_csv(r"gdp_pop_pct.csv", index=False, float_format="%.10f")
