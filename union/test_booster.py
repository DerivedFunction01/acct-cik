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
        {"pop": 100, "dom": "JE", "others": ["US"], "desc": "Small Dom vs Giant (Should Smooth)"},
        {"pop": 100, "dom": "US", "others": ["CN"], "desc": "Giant Dom vs Giant (No Smooth)"},
        {"pop": 100, "dom": "US", "others": ["JE"], "desc": "Giant Dom vs Small (No Smooth)"},
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