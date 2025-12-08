# MAX MUNCH PRINCIPLE: Training Data Generation Only

## The Real Problem: Masking for ML Training

Your ML training pipeline has **one specific goal**: Take sentences with derivative instruments and mask them so the model learns to classify based on **context alone**, not surface-level instrument names.

The Max Munch principle solves a **data generation problem**, NOT a database filtering problem:

```
PIPELINE FLOW:

Database (Active User Classifications)
         ↓
Raw text extraction
         ↓
Sentence selection
         ↓
[MASKING FOR ML] ← Max Munch applies HERE
         ↓
Training data with masked instruments
         ↓
RoBERTa model training
```

---

## The Problem: Partial Masking

When you want to mask an instrument for training, you need the **complete instrument phrase** to be replaced with a generic form, not just the base word.

### Example: The Partial Match Problem

```
Original sentence (Label: IR):
"The Company maintains interest rate swaps to manage floating rate debt."

Goal: Create training example where model must use CONTEXT, not the instrument name

WRONG APPROACH (naive regex without Max Munch):
- Pattern "swap" matches first → "interest rate [GENERIC]"
- Problem: Model can still see "interest rate" in context
- Model learns: "interest rate" + [something] = IR
- Not genuine context learning

CORRECT APPROACH (with Max Munch):
- Pattern "interest rate swap" matches first → "[GENERIC]"
- Model sees: "maintains [GENERIC] to manage floating rate debt"
- Model learns: maintenance + floating rate debt + debt context = IR
- Genuine context-based learning
```

### Why This Matters

```
BAD training example (leaked category signal):
Input:  "maintains interest rate [GENERIC] to manage floating rate debt"
Label:  IR
Problem: Model can partially infer from "interest rate" alone

GOOD training example (clean context only):
Input:  "maintains [GENERIC] to manage floating rate debt"
Label:  IR
Result: Model must learn from "maintains", "floating rate", "rate debt"
```

---

## The Solution: Replace Full Phrases, Not Words

Max Munch ensures you **match and replace entire derivative phrases**, not partial components.

### Implementation

```python
# In create_labeled_dataset.py

def prepare_training_example(sentence, target_category):
    """
    Replace the FULL instrument phrase with a generic form.
    """
    
    # Get the STRICT regex (already ordered longest-first)
    target_regex = CATEGORY_DELETION_MAP[target_category][0]
    
    # Match will capture the LONGEST phrase
    match = target_regex.search(sentence)
    
    if not match:
        return None
    
    matched_text = match.group(0)  # Gets "interest rate swap", not just "swap"
    
    # Replace with generic equivalent
    generic_form = _get_generic_form(target_category)
    # e.g., "hedging instruments", "derivative contracts", etc.
    
    training_text = sentence[:match.start()] + generic_form + sentence[match.end():]
    
    # Result: "The Company maintains hedging instruments to manage 
    #          floating rate debt."
    
    return training_text, target_category, metadata
```

### Why Longest-First Ordering

```python
# IR instruments, ordered longest → shortest
IR_PATTERNS = [
    "interest rate swap agreement",        # 4 words
    "interest rate swap",                  # 3 words
    "pay fixed receive floating",          # 4 words
    "treasury lock",                       # 2 words
    "swap",                                # 1 word ← MUST BE LAST
]

# Regex: (?:interest rate swap agreement|pay fixed receive floating|...|swap)
#         Longest ─────────────────────────────────────────────────── Shortest

# When matching "interest rate swap agreement":
# - Tries "interest rate swap agreement" first → MATCHES ✓ STOPS
# - Never gets to "swap" pattern
# Result: Full phrase replaced, not partial
```

---

## Real Example from Your Code

```python
class AugmentationEngine:
    """
    Augment by replacing matched instrument with a variant.
    """
    
    def augment(self, text, span, match_text, strategy="dynamic_base"):
        start, end = span
        
        # match_text is the FULL matched instrument (thanks to Max Munch)
        # e.g., "interest rate swaps", not just "swaps"
        
        if strategy == "dynamic_base":
            # Replace with generic base form
            base_replacement = _get_dynamic_base(match_text)
            # "interest rate swaps" → "hedging instruments"
            
            augmented_text = text[:start] + base_replacement + text[end:]
            return augmented_text, "DynamicBase"
        
        # Result: Full phrase replaced with generic form
        # No partial category signal leaks
```

---

## Data Flow Example

```
STEP 1: Extraction from Active User Database
Original: "The Company maintains interest rate swaps with a fair value of $2.1M 
           to manage floating rate debt exposure."

STEP 2: Sentence selection
Sentence: "The Company maintains interest rate swaps to manage floating rate debt."

STEP 3: Masking for ML (Max Munch applies HERE)
Regex finds: "interest rate swaps" (full phrase, thanks to longest-first ordering)
Replacement: "interest rate swaps" → "hedging instruments"
Result: "The Company maintains hedging instruments to manage floating rate debt."

STEP 4: Create context window with substitutions
Before numeric/currency substitution:
"[...previous context...] [SEP] The Company maintains hedging instruments 
 to manage floating rate debt. [SEP] [...next context...] [SEP]"

With numeric substitution:
- Years stay consistent across window
- Months adjusted uniformly
- Numbers perturbed ±5%

STEP 5: Training example ready
{
  "text": "[...context...] [SEP] The Company maintains hedging instruments 
           to manage floating rate debt. [SEP] [...context...] [SEP]",
  "label": "IR",
  "difficulty": "L2_Masked_Scrubbed"
}

MODEL TRAINING:
Input: Context window with [generic instrument]
Output: Predict "IR"
Model learns: Context patterns, not lexical shortcuts
```

---

## Why Not Just Use a Simple Regex?

Without Max Munch ordering, you'd need to check phrase length manually:

```python
# WITHOUT Max Munch (brittle, error-prone):
def mask_instrument_naive(text, sentence):
    # Have to manually check longest phrases first
    if "interest rate swap agreement" in text:
        return text.replace("interest rate swap agreement", "[GENERIC]")
    elif "interest rate swap" in text:
        return text.replace("interest rate swap", "[GENERIC]")
    elif "swap" in text:
        return text.replace("swap", "[GENERIC]")
    # ... many more elif branches
    # Easy to forget cases, easy to mis-order

# WITH Max Munch (clean, automatic):
def mask_instrument_smart(text, sentence):
    regex = IR_REGEX  # Already ordered longest-first
    match = regex.search(text)  # Gets longest match automatically
    if match:
        return text[:match.start()] + "[GENERIC]" + text[match.end():]
    # Done. Entire phrase replaced.
```

---

## Summary

**Max Munch Principle for ML Training:**

1. **Scope**: Applied during **training data generation** (masking), NOT during database filtering
2. **Purpose**: Ensure complete instrument phrases are replaced with generic forms, not partial matches
3. **Benefit**: Training data has **no category signal leakage** from leftover instrument components
4. **Implementation**: Regex alternation ordered longest-first ensures first match is the full phrase
5. **Result**: RoBERTa model learns to classify from **context alone**, not surface patterns

The database pipeline filters derivative content correctly at Phase 1-7. The Max Munch principle then ensures that when you create training examples from those filtered sentences, you're replacing **entire instrument phrases** with generics, creating clean training data for the classifier.

