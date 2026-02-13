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
