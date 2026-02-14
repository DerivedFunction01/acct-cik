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
).round(4)

# %%
world_gdp = merged_final["last_known_gdp"].sum()
merged_final["gdp_pct"] = merged_final["last_known_gdp"] / world_gdp
merged_final["gdp_pct"] = (merged_final["last_known_gdp"] / world_gdp * 100).round(4)
# %%
# Keep only the 2 digit code and the pct
output_csv = merged_final[["alpha2", "pop_pct", "gdp_pct"]]
output_csv.columns = ["code", "population_pct", "gdp_pct"]
# %%
output_csv.to_csv(r"gdp_pop_pct.csv", index=False)
# %%
import pandas as pd

cb_df = pd.read_excel("cb_rate.xlsx")
cb = cb_df[cb_df["indicator.label"] == "Collective bargaining coverage rate (%)"]
cb_avg = (
    cb_df[cb_df["indicator.label"] == "Collective bargaining coverage rate (%)"]
    .groupby("ref_area.label", as_index=False)
    .agg(cb_rate=("obs_value", "mean"))
)
cb_avg["cb_rate"] = cb_avg["cb_rate"].round(4)
union_df = pd.read_excel("union_rate.xlsx")
union = union_df[union_df["indicator.label"] == "Trade union density rate (%)"]
union_avg = union.groupby("ref_area.label", as_index=False).agg(
    union_rate=("obs_value", "mean")
)
union_avg["union_rate"] = union_avg["union_rate"].round(4)
cb_union = cb_avg.merge(union_avg, on="ref_area.label", how="outer")
cb_union["cb_rate"] = cb_union["cb_rate"].fillna(cb_union["union_rate"])
cb_union["union_rate"] = cb_union["union_rate"].fillna(cb_union["cb_rate"])
cb_union["labor_rate"] = cb_union[["cb_rate", "union_rate"]].mean(axis=1).round(4)
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
#%%
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
#%%
# --- Merge using fuzzy name to get alpha2 ---
cb_union_merged = cb_union.merge(
    codes_conv[["name", "alpha2"]], left_on="country_fuzzy", right_on="name", how="left"
)
# %%
