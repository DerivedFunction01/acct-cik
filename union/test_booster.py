import random
import sys
import os

# Ensure we can import from local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from defs.region_regex import weighted_division, _CODE_TO_WEIGHT, COMPOSITE_REGION_MAP, REGION_CODES

def run_booster_tests():
    # Array of populations to test
    populations = [50, 100, 500, 800, 1000, 2500, 5000, 10000, 25000, 50000, 100000]

    # Composite regions to sample from
    composite_keys = list(COMPOSITE_REGION_MAP.keys())
    random.shuffle(composite_keys)

    print(f"{'POP':<8} | {'DOM':<3} | {'N':<2} | {'OTHERS':<25} | {'FINAL %':<8} | {'NOTE'}")
    print("-" * 120)

    for i in range(50): # Run 50 random scenarios
        # 1. Pick a random population
        pop = float(random.choice(populations))

        # 2. Pick a composite region (cycle through shuffled list)
        region_key = composite_keys[i % len(composite_keys)]
        region_countries = COMPOSITE_REGION_MAP[region_key]

        if not region_countries:
            continue

        # 3. Pick a random domestic code
        domestic_code = random.choice(region_countries)

        # 4. Dynamically add X entities
        possible_others = [c for c in region_countries if c != domestic_code]

        # Branch out: Add random global codes
        all_codes = [c for c in _CODE_TO_WEIGHT.keys() if c not in REGION_CODES and len(c) == 2]
        if all_codes:
            random_globals = random.sample(all_codes, min(len(all_codes), 10))
            for c in random_globals:
                if c != domestic_code and c not in possible_others:
                    possible_others.append(c)

        if not possible_others:
            possible_others = ["US", "CN", "DE", "EU"] 

        num_others = random.randint(1, min(8, len(possible_others)))
        others = random.sample(possible_others, num_others)

        # Construct entities list
        entities = [{"key": domestic_code}] + [{"key": o} for o in others]

        # Run weighted division
        distribution, note = weighted_division(
            val=pop, 
            entities=entities, 
            domestic_country=domestic_code
        )

        # Calculate results
        dom_val = distribution.get(domestic_code, 0)
        final_share = dom_val / pop if pop > 0 else 0

        # Format output
        others_str = ",".join(others)
        if len(others_str) > 25:
            others_str = others_str[:22] + "..."

        print(f"{int(pop):<8} | {domestic_code:<3} | {num_others:<2} | {others_str:<25} | {final_share:.1%}   | [{region_key}] {note}")
        sorted_dist = sorted(distribution.items(), key=lambda x: x[1], reverse=True)
        print(f"          -> {', '.join([f'{k}={int(v)}' for k, v in sorted_dist])}")

    # Add specific targeted tests
    print("\n--- Targeted Tests (Smoothing Logic) ---")
    targeted_scenarios = [
        {
            "pop": 100,
            "dom": "JE",
            "others": ["US"],
            "desc": "Small Dom vs Giant (Should Smooth)",
        },
        {
            "pop": 100,
            "dom": "US",
            "others": ["CN"],
            "desc": "Giant Dom vs Giant (No Smooth)",
        },
        {
            "pop": 100,
            "dom": "US",
            "others": ["JE"],
            "desc": "Giant Dom vs Small (No Smooth)",
        },
        {
            "pop": 100000,
            "dom": "US",
            "others": ["MX", "CA", "CN", "DE", "GB", "JP"],
            "desc": "US MNE typical (low N, NAMERICA + G20)",
        },
        # Expected: ~65–75% domestic (BEA ~68%)
        {
            "pop": 100000,
            "dom": "CN",
            "others": ["US", "JP", "KR", "DE", "VN", "IN"],
            "desc": "Chinese MNE (ASEAN + G20 focus)",
        },
        # Expected: ~70–85% (many Chinese firms very home-heavy)
        {
            "pop": 50000,
            "dom": "DE",
            "others": ["FR", "PL", "CZ", "NL", "IT", "US"],
            "desc": "German MNE (EU core + US)",
        },
        {
            "pop": 100,
            "dom": "BM",
            "others": ["US", "GB", "CA"],
            "desc": "Bermuda HQ vs major markets (harsh penalty + smoothing)",
        },
        # Expected: <5–10% domestic (real: very low operational jobs in Bermuda)
        {
            "pop": 500,
            "dom": "KY",
            "others": ["US", "GB", "IE", "SG"],
            "desc": "Cayman HQ finance firm vs conduits/majors",
        },
        {
            "pop": 500,
            "dom": "HK",
            "others": ["US"],
            "desc": "Semi Tax Haven",
        },
        # Expected: ~0–15% (penalties should crush domestic share)
        {
            "pop": 100,
            "dom": "JE",
            "others": ["GB", "US", "IE", "CH"],
            "desc": "Jersey finance vs big financial centers",
        },
        {
            "pop": 25000,
            "dom": "TW",
            "others": ["CN", "US", "JP", "KR", "SG"],
            "desc": "TSMC-like (strong Taiwan booster in EASIA)",
        },
        # Expected: ~75–90% domestic (real TSMC ~87% in Taiwan)
        {
            "pop": 10000,
            "dom": "IL",
            "others": ["US", "DE", "GB", "IN", "FR"],
            "desc": "Israeli tech MNE (strong booster)",
        },
        # Expected: ~60–80% (high domestic retention in R&D/tech)
        {
            "pop": 50000,
            "dom": "KR",
            "others": ["CN", "US", "VN", "IN", "JP"],
            "desc": "Korean chaebol (EASIA + global)",
        },
        {
            "pop": 5000,
            "dom": "IE",
            "others": ["US", "GB", "DE", "FR", "CN"],
            "desc": "Irish pharma/tech conduit (moderate penalty)",
        },
        # Expected: ~20–40% domestic (higher than pure havens, but not huge)
        {
            "pop": 25000,
            "dom": "NL",
            "others": ["DE", "FR", "GB", "US", "BE", "CH"],
            "desc": "Dutch MNE (INT_NL, BENELUX smoothing)",
        },
        # Expected: ~40–60% (Dutch firms often quite internationalized)
        {
            "pop": 10000,
            "dom": "SG",
            "others": ["CN", "ID", "MY", "TH", "IN", "US"],
            "desc": "Singapore hub (EASIA/ASEAN, booster?)",
        },
        {
            "pop": 500,
            "dom": "IS",
            "others": ["NO", "DK", "SE", "FI"],
            "desc": "Icelandic firm purely NORDIC",
        },
        # Expected: high domestic (~60–85%) if cluster strong
        {
            "pop": 1000,
            "dom": "EE",
            "others": ["LV", "LT", "FI", "SE", "RU"],
            "desc": "Estonian tech (BALTIC + NORDIC)",
        },
        # Expected: ~40–70% (Estonian firms often quite home/regional)
        {
            "pop": 500,
            "dom": "LU",
            "others": ["DE", "FR", "BE", "NL"],
            "desc": "Luxembourg finance (BENELUX/DACH)",
        },
        # Expected: low–moderate (~10–40%) due to conduit role
        {
            "pop": 500,
            "dom": "US",
            "others": ["EU", "CN"],
            "desc": "US/EU/China",
        },
        {
            "pop": 2000,
            "dom": "US",
            "others": ["EU", "CN"],
            "desc": "US/EU/China",
        },
        {
            "pop": 5000,
            "dom": "US",
            "others": ["EU", "CN"],
            "desc": "US/EU/China",
        },
        {
            "pop": 10000,
            "dom": "US",
            "others": ["EU", "CN"],
            "desc": "US/EU/China",
        },
        {
            "pop": 10000,
            "dom": "US",
            "others": ["DE", "FR", "CN", "JP", "KR"],
            "desc": "US/DE/FR+ CN/JP/KR",
        },
        {
            "pop": 10000,
            "dom": "INT",
            "others": ["CIS", "SASIA", "DACH"],
            "desc": "Dynamic",
        },
    ]

    for t in targeted_scenarios:
        pop = float(t["pop"])
        domestic_code = t["dom"]
        others = t["others"]
        entities = [{"key": domestic_code}] + [{"key": o} for o in others]

        distribution, note = weighted_division(
            val=pop, 
            entities=entities, 
            domestic_country=domestic_code
        )

        dom_val = distribution.get(domestic_code, 0)
        final_share = dom_val / pop if pop > 0 else 0
        others_str = ",".join(others)

        print(f"{int(pop):<8} | {domestic_code:<3} | {len(others):<2} | {others_str:<25} | {final_share:.1%}   | {t['desc']} -> {note}")
        sorted_dist = sorted(distribution.items(), key=lambda x: x[1], reverse=True)
        print(f"          -> {', '.join([f'{k}={int(v)}' for k, v in sorted_dist])}")

if __name__ == "__main__":
    run_booster_tests()
