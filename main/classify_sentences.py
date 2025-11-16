# =============================================================================
# CLASSIFICATION SERVER
# =============================================================================
# A FastAPI server that uses a cross-encoder model to classify sentences
# against a set of core hypotheses for derivative usage.
#
# The server exposes a single endpoint, `/classify`, which expects a POST
# request with a JSON body containing:
#   - `term`: The specific derivative term (e.g., "interest rate swaps").
#   - `stage`: The classification stage ("policy" or "position").
#   - `sentences`: A list of sentences to classify.
#
# It returns a JSON object containing the classification results for each
# sentence, including the predicted label (entailment, contradiction, neutral)
# and raw scores for each hypothesis.
#
# This tiered approach allows for efficient, targeted classification based on
# the context of the sentences being processed.
#
# ---
#
# To run the server:
# uvicorn classification_server:app --host 0.0.0.0 --port 8000
# =============================================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from typing import List, Dict, Literal

# =============================================================================
# CONFIGURATION & MODEL LOADING
# =============================================================================

MODEL_NAME = "cross-encoder/nli-deberta-v3-large"

# Load the model and tokenizer at startup
print(f"🚀 Loading model: {MODEL_NAME}...")
try:
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model.eval()  # Set model to evaluation mode
    print("✅ Model loaded successfully.")
except Exception as e:
    print(f"❌ Failed to load model: {e}")
    model, tokenizer = None, None

# Define the 4 core hypotheses with the {TERM} placeholder
CORE_HYPOTHESES = {
    "H1_Policy": "The company's financial policy discloses or allows for the use or execution of {TERM}{YEAR_PHRASE}.",
    "H2_Existence": "The company held or carried outstanding, un-terminated {TERM} positions{YEAR_PHRASE}.",
    "H3_Notional": "The company reported a non-zero notional amount for {TERM}{YEAR_PHRASE}.",
    "H4_PnL_Impact": "The company recognized a gain, loss, or ongoing cash flow attributable to {TERM}{YEAR_PHRASE}.",
}

# Define which hypotheses to use for each stage
STAGE_HYPOTHESES_MAP = {
    "policy": ["H1_Policy"],
    "notional": ["H3_Notional"],
    "position": ["H2_Existence", "H4_PnL_Impact"],
}

# Mapping from model output index to label
LABEL_MAPPING = ["contradiction", "entailment", "neutral"]

# =============================================================================
# FASTAPI APP & DATA MODELS
# =============================================================================

app = FastAPI(
    title="Sentence Classification Server",
    description="A server to classify sentences against derivative usage hypotheses.",
    version="1.0.0",
)


class ClassificationRequest(BaseModel):
    term: str = Field(
        ...,
        json_schema_extra={"example": "interest rate swaps"},
        description="The derivative term to insert into the hypotheses.",
    )
    stage: Literal["policy", "position", "notional"] = Field(
        ...,
        json_schema_extra={"example": "position"},
        description="The classification stage to determine which hypotheses to use.",
    )
    sentences: List[str] = Field(
        ...,
        min_length=1,
        json_schema_extra={"example": ["The company uses interest rate swaps to manage risk."]},
    )
    year: int | None = Field(
        None,
        json_schema_extra={"example": 2023},
        description="Optional: The reporting year to insert into the hypotheses for time-specific classification.",
    )

class ClassificationResult(BaseModel):
    sentence: str
    classifications: Dict[str, str] = Field(
        description="A dictionary mapping hypothesis ID to its classification label (e.g., entailment)."
    )
    scores: Dict[str, List[float]] = Field(
        description="A dictionary mapping hypothesis ID to its raw logit scores, ordered as [contradiction, entailment, neutral]."
    )


class ClassificationResponse(BaseModel):
    results: List[ClassificationResult]

# =============================================================================
# API ENDPOINT
# =============================================================================

@app.post("/classify", response_model=ClassificationResponse)
async def classify_sentences(request: ClassificationRequest):
    """
    Classifies a batch of sentences against a selected set of hypotheses.

    This endpoint implements the tiered classification strategy:
    - **Stage 'policy'**: Checks sentences against the general `H1_Policy` hypothesis.
      This is ideal for sentences without a clear time reference.
    - **Stage 'notional'**: A focused check for `H3_Notional` to efficiently find
      sentences that disclose notional amounts.
    - **Stage 'position'**: Checks sentences against `H2_Existence`, `H3_Notional`,
      and `H4_PnL_Impact`. This is for sentences with a year or other time-specific
      markers to confirm active usage.

    **Request Body:**
    - `term` (str): The derivative term to inject into the hypothesis (e.g., "interest rate swaps").
    - `stage` (str): Either "policy" or "position".
    - `sentences` (List[str]): A list of sentences to classify. 
    - `year` (int, optional): The reporting year for time-specific classification.

    **Returns:**
    A JSON object containing a list of results, where each result includes:
    - `sentence`: The original input sentence.
    - `classifications`: A dictionary mapping each tested hypothesis ID to its predicted label.
    - `scores`: A dictionary mapping each hypothesis ID to its raw logit scores for
      [contradiction, entailment, neutral].
    """
    if not model or not tokenizer:
        raise HTTPException(status_code=503, detail="Model is not available.")

    # 1. Select hypotheses based on the requested stage
    hypothesis_ids = STAGE_HYPOTHESES_MAP.get(request.stage)
    if not hypothesis_ids:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {request.stage}")

    # 2. Determine the year phrase based on whether a year was provided
    year_phrase = f" in the year {request.year}" if request.year else ""

    # 3. Prepare sentence pairs for the model
    sentence_pairs = []
    hypotheses_to_run = {}
    for hypo_id in hypothesis_ids:
        # Insert the specific term and year phrase into the hypothesis template
        base_hypothesis = CORE_HYPOTHESES[hypo_id]
        formatted_hypothesis = base_hypothesis.format(
            TERM=request.term, YEAR_PHRASE=year_phrase
        ).strip()

        hypotheses_to_run[hypo_id] = formatted_hypothesis
        for sentence in request.sentences:
            sentence_pairs.append([sentence, formatted_hypothesis])

    # 3. Tokenize and predict in a single batch
    try:
        with torch.no_grad():
            features = tokenizer(
                sentence_pairs,
                padding=True,
                truncation=True,
                return_tensors="pt",
            )
            scores = model(**features).logits
            predictions = scores.argmax(dim=1)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")

    # 4. Structure the results
    results: List[ClassificationResult] = []
    num_hypotheses = len(hypotheses_to_run)

    for i, sentence in enumerate(request.sentences):
        sentence_classifications = {}
        sentence_scores = {}

        for j, hypo_id in enumerate(hypothesis_ids):
            # The model processes all sentences for the first hypothesis, then all for the second, etc.
            # We need to index into the flat list of results correctly.
            result_index = j * len(request.sentences) + i

            label = LABEL_MAPPING[predictions[result_index]]
            raw_scores = scores[result_index].tolist()

            sentence_classifications[hypo_id] = label
            sentence_scores[hypo_id] = raw_scores

        results.append(
            ClassificationResult(
                sentence=sentence,
                classifications=sentence_classifications,
                scores=sentence_scores,
            )
        )

    return ClassificationResponse(results=results)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
