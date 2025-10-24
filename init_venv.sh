#!/usr/bin/env bash
set -e

VENV_DIR="venv-acct-cik"

# --- Parse command-line arguments ---
REINSTALL=false
BASE_ONLY=false

for arg in "$@"; do
  case $arg in
    --reinstall)
      REINSTALL=true
      shift
      ;;
    --base)
      BASE_ONLY=true
      shift
      ;;
  esac
done

# --- Create virtual environment if needed ---
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment '$VENV_DIR'..."
  if command -v python3 &> /dev/null; then
    python3 -m venv "$VENV_DIR"
  elif command -v python &> /dev/null; then
    python -m venv "$VENV_DIR"
  else
    echo "Error: Neither python3 nor python is available"
    exit 1
  fi
else
  echo "Virtual environment '$VENV_DIR' already exists."
  if [ "$REINSTALL" = true ]; then
    echo "Reinstall flag detected — proceeding with package installation anyway."
  else
    echo "Skipping installation. Use --reinstall to force reinstallation."
    exit 0
  fi
fi

# --- Activate the environment ---
if [ -f "$VENV_DIR/Scripts/activate" ]; then
  source "$VENV_DIR/Scripts/activate"
else
  source "$VENV_DIR/bin/activate"
fi

# --- Package lists ---
BASE_PACKAGES="pandas requests beautifulsoup4 tqdm psutil numpy openpyxl xlsxwriter flask pydrive2 waitress gunicorn"
ML_PACKAGES="scikit-learn datasets transformers accelerate IPython"

# --- Detect GPU & CUDA ---
if command -v nvidia-smi &> /dev/null; then
  echo "NVIDIA GPU detected!"
  CUDA_VERSION=$(nvidia-smi | grep -oP 'CUDA Version: \K[0-9]+\.[0-9]+')
  echo "Detected CUDA version: $CUDA_VERSION"

  if [[ "$CUDA_VERSION" == 12.4* ]]; then
    CUDA_TAG="cu124"
  elif [[ "$CUDA_VERSION" == 12.1* ]]; then
    CUDA_TAG="cu121"
  elif [[ "$CUDA_VERSION" == 11.* ]]; then
    CUDA_TAG="cu118"
  else
    echo "Unknown CUDA version ($CUDA_VERSION), defaulting to cu121"
    CUDA_TAG="cu121"
  fi

  echo "Installing PyTorch 2.6.0 ($CUDA_TAG build)..."
  pip install torch==2.6.0+${CUDA_TAG} torchvision==0.21.0+${CUDA_TAG} torchaudio==2.6.0 \
    --index-url https://download.pytorch.org/whl/${CUDA_TAG}

else
  echo "No NVIDIA GPU detected. Installing CPU-only PyTorch 2.6.0..."
  pip install torch==2.6.0+cpu torchvision==0.21.0+cpu torchaudio==2.6.0 \
    --index-url https://download.pytorch.org/whl/cpu
fi

# --- Install other packages ---
if [ "$BASE_ONLY" = true ]; then
  echo "Installing base packages only..."
  pip install $BASE_PACKAGES
else
  echo "Installing all packages (including ML)..."
  pip install $BASE_PACKAGES $ML_PACKAGES
fi

echo "✅ Environment setup complete."