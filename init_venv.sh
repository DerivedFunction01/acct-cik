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
if [ -f "$VENV_DIR/bin/activate" ]; then
  source "$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
  source "$VENV_DIR/Scripts/activate"
else
  echo "Could not find activation script. Virtual environment may not have been created correctly."
  exit 1
fi

# --- Verify activation ---
if [ -z "$VIRTUAL_ENV" ]; then
  echo "Virtual environment not activated. Aborting to avoid global install."
  exit 1
fi

# --- Packages ---
BASE_PACKAGES="beautifulsoup4 psutil openpyxl xlsxwriter pydrive2 matplotlib IPython"
ML_PACKAGES="torch unsloth torchvision datasets scikit-learn flask gunicorn waitress"

# --- Install packages ---
if [ "$BASE_ONLY" = true ]; then
  pip install --upgrade $BASE_PACKAGES
else
  pip install --upgrade $BASE_PACKAGES $ML_PACKAGES
fi

echo "Setup complete."