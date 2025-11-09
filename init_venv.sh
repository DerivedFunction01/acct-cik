#!/usr/bin/env bash
set -e

VENV_DIR="venv-acct-cik"

# --- Parse arguments ---
REINSTALL=false
BASE_ONLY=false

for arg in "$@"; do
  case $arg in
    --reinstall) REINSTALL=true ;;
    --base) BASE_ONLY=true ;;
  esac
done

# --- Create venv if needed ---
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment '$VENV_DIR'..."
  python3 -m venv "$VENV_DIR" || python -m venv "$VENV_DIR"
else
  [ "$REINSTALL" = false ] && echo "Skipping install. Use --reinstall." && exit 0
fi

# --- Activate venv ---
source "$VENV_DIR/bin/activate" 2>/dev/null || source "$VENV_DIR/Scripts/activate"

# --- Packages ---
BASE_PACKAGES="beautifulsoup4 psutil openpyxl xlsxwriter pydrive2 matplotlib IPython"
ML_PACKAGES="unsloth torchvision datasets scikit-learn flask gunicorn waitress"

# --- Install packages ---
if [ "$BASE_ONLY" = true ]; then
  pip install $BASE_PACKAGES
else
  pip install $BASE_PACKAGES $ML_PACKAGES
fi

echo "Setup complete."