import argparse
import json
import random
from tqdm import tqdm
import os

# Important: This script assumes it's run from the `main` directory.
# We need to adjust the path to import from the sibling `defs` directory.
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import generator2

def generate_dataset(
    num_samples: int,
    output_file: str,
    archetype_mode: str = "random_predefined",
    allow_drops: bool = True,
    drop_overrides: dict = None,
    generation_overrides: dict = None,
    debug: bool = False,
):
    """
    Generates a dataset of training samples and saves it to a JSONL file.

    Args:
        num_samples: The number of samples to generate.
        output_file: The path to the output JSONL file.
        archetype_mode: 'random_predefined' to pick from SCENARIO_ARCHETYPES,
                        'truly_random' to create fully random archetypes.
        allow_drops: Whether to enable probabilistic dropping of narrative sections.
        drop_overrides: A dictionary to override default DROP_PROBABILITIES.
        generation_overrides: A dictionary to override default GENERATION_PROBABILITIES.
        debug: If True, includes debug info in the output file.
    """
    print(f"Starting dataset generation for {num_samples} samples...")

    # --- Configure Probabilities ---
    if drop_overrides:
        print("Applying custom drop probabilities...")
        generator2.DROP_PROBABILITIES.update(drop_overrides)
    if generation_overrides:
        print("Applying custom generation probabilities...")
        generator2.GENERATION_PROBABILITIES.update(generation_overrides)

    # --- Set Debug Mode ---
    generator2.DEBUG = debug

    with open(output_file, "w") as f:
        for _ in tqdm(range(num_samples), desc="Generating Samples"):
            archetype_index = None
            if archetype_mode == "random_predefined":
                # Select a random archetype from the predefined list
                archetype_index = random.randint(0, len(generator2.SCENARIO_ARCHETYPES) - 1)
            # If 'truly_random', archetype_index remains None, which is the correct signal.

            # 1. Create the "story" or scenario
            scenario = generator2.create_random_scenario(archetype_index=archetype_index)

            # 2. Generate the narrative text and the evidence list from the scenario
            narrative, evidence = generator2.generate_narrative_from_scenario(
                scenario, allow_random_drops=allow_drops
            )

            # 3. Generate the structured JSON output from the evidence
            target_json = generator2.generate_json_from_scenario(scenario, evidence)

            # 4. Format for instruction fine-tuning
            # The prompt provides the context and instruction for the model.
            # The response is the JSON object the model must learn to generate.
            prompt = (
                "Analyze the following text from a financial report to identify derivative usage. "
                "Extract details on all derivative instruments, the company's risk exposures, and its mitigation strategies. "
                "Your response must be a single, valid JSON object conforming to the required schema.\n\n"
                f"Text: {narrative}"
            )

            training_record = {
                "prompt": prompt,
                "response": json.dumps(target_json, indent=2),
            }

            if debug:
                training_record["debug_info"] = generator2._generate_debug_output(scenario, evidence)

            f.write(json.dumps(training_record) + "\n")

    print(f"\nSuccessfully generated {num_samples} samples to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a dataset for derivative analysis model training.")
    parser.add_argument("-n", "--num_samples", type=int, default=100, help="Number of samples to generate.")
    parser.add_argument("-o", "--output_file", type=str, default="training_dataset.jsonl", help="Output JSONL file path.")
    parser.add_argument(
        "--archetype",
        type=str,
        choices=["random_predefined", "truly_random"],
        default="random_predefined",
        help="Method for selecting company archetypes."
    )
    parser.add_argument("--no_drops", action="store_true", help="Disable random dropping of narrative sections for complete text.")
    parser.add_argument("--debug", action="store_true", help="Include detailed debug information in the output file.")

    args = parser.parse_args()

    generate_dataset(
        num_samples=args.num_samples,
        output_file=args.output_file,
        archetype_mode=args.archetype,
        allow_drops=not args.no_drops,
        debug=args.debug,
    )