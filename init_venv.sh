#!/usr/bin/env bash
set -e

VENV_DIR="venv-acct-cik"

# Create and set up the virtual environment only if it doesn't exist
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

  # Activate the new environment
  if [ -f "$VENV_DIR/Scripts/activate" ]; then
    source "$VENV_DIR/Scripts/activate"
  else
    source "$VENV_DIR/bin/activate"
  fi


  # Define packages
  BASE_PACKAGES="pandas requests beautifulsoup4 tqdm psutil numpy openpyxl xlsxwriter flask pydrive2 waitress gunicorn"
  ML_PACKAGES="scikit-learn datasets transformers accelerate IPython"

  # --- Detect NVIDIA GPU ---
  if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU detected! Installing CUDA-enabled PyTorch..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
  else
    echo "No NVIDIA GPU detected. Installing CPU-only PyTorch..."
    pip install torch torchvision torchaudio
  fi

  # Install other packages
  if [[ "$1" == "--base" ]]; then
    echo "Installing base packages for fetching only..."
    pip install $BASE_PACKAGES
  else
    echo "Installing all packages (including ML)..."
    pip install $BASE_PACKAGES $ML_PACKAGES
  fi

else
  echo "Virtual environment '$VENV_DIR' already exists. Skipping creation and installation."
fi