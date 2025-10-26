#!/usr/bin/env bash
set -e

VENV_DIR="venv-acct-cik"
TORCH_LOCK_FILE="$VENV_DIR/torch.lock"

# --- Parse arguments ---
REINSTALL=false
BASE_ONLY=false
INSTALL_ONLY=false
REINSTALL_TORCH=false

for arg in "$@"; do
  case $arg in
    --reinstall)
      REINSTALL=true
      ;;
    --base)
      BASE_ONLY=true
      ;;
    --install)
      INSTALL_ONLY=true
      ;;
    --reinstall-torch)
      REINSTALL_TORCH=true
      ;;
  esac
done

# --- Create venv if needed ---
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment '$VENV_DIR'..."
  if command -v python &> /dev/null; then
    python -m venv "$VENV_DIR"
  elif command -v python3 &> /dev/null; then
    python3 -m venv "$VENV_DIR"
  else
    echo "Error: Neither python3 nor python is available"
    exit 1
  fi
else
  echo "Virtual environment '$VENV_DIR' already exists."
  if [ "$REINSTALL" = false ] && [ "$INSTALL_ONLY" = false ]; then
    echo "Skipping package install. Use --install, --reinstall, or --reinstall-torch."
    exit 0
  fi
fi

# --- Activate venv ---
if [ -f "$VENV_DIR/Scripts/activate" ]; then
  source "$VENV_DIR/Scripts/activate"
else
  source "$VENV_DIR/bin/activate"
fi

# --- Packages ---
BASE_PACKAGES="pandas requests beautifulsoup4 tqdm psutil numpy openpyxl xlsxwriter flask pydrive2 waitress gunicorn"
ML_PACKAGES="scikit-learn datasets transformers accelerate IPython"

# --- Handle PyTorch (skip if locked unless --reinstall-torch) ---
if [ -f "$TORCH_LOCK_FILE" ] && [ "$REINSTALL_TORCH" = false ]; then
  echo "🧱 PyTorch is locked. Skipping reinstall."
  echo "  (Run with --reinstall-torch to reinstall or upgrade)"
else
  echo "🔄 Installing or updating PyTorch..."
  if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU detected."
    CUDA_VERSION=$(nvidia-smi | grep -oP 'CUDA Version: \K[0-9]+\.[0-9]+')
    echo "Detected CUDA version: $CUDA_VERSION"
    
    # Dynamically determine CUDA tag. e.g., "12.1" -> "cu121", "11.8" -> "cu118"
    CUDA_MAJOR=$(echo "$CUDA_VERSION" | cut -d. -f1)
    CUDA_MINOR=$(echo "$CUDA_VERSION" | cut -d. -f2)
    
    if [[ "$CUDA_MAJOR" -eq 12 ]]; then
      # For CUDA 12.x, try to match the minor version (e.g., 12.4 -> cu124).
      # If a specific wheel doesn't exist for a newer version (e.g., 12.8),
      # PyTorch recommends using the cu121 wheel, which is forward-compatible.
      if [[ "$CUDA_MINOR" -ge 1 ]]; then
        CUDA_TAG="cu121" # Default to the most compatible CUDA 12 wheel
      fi
      # Override with more specific versions if they match
      if [[ "$CUDA_VERSION" == "12.4"* ]]; then
        CUDA_TAG="cu124"
      fi
    elif [[ "$CUDA_MAJOR" -eq 11 ]]; then
      # For CUDA 11.x, the latest supported wheel is typically cu118.
      CUDA_TAG="cu118"
    else
      echo "Warning: Unsupported CUDA major version ($CUDA_MAJOR). Attempting to fall back to CPU."
      CUDA_TAG="cpu"
    fi

    pip install torch==2.6.0+${CUDA_TAG} torchvision==0.21.0+${CUDA_TAG} torchaudio==2.6.0 \
      --index-url https://download.pytorch.org/whl/${CUDA_TAG}
    echo "✅ PyTorch with CUDA $CUDA_VERSION installed."
  elif command -v rocm-smi &> /dev/null; then
    echo "✅ AMD GPU with ROCm detected."
    pip install torch==2.6.0+rocm6.1 torchvision==0.21.0+rocm6.1 torchaudio==2.6.0 \
      --index-url https://download.pytorch.org/whl/rocm6.1
    echo "✅ PyTorch with ROCm installed."
  else
    echo "No NVIDIA GPU detected. Installing CPU-only PyTorch..."
    pip install torch==2.6.0+cpu torchvision==0.21.0+cpu torchaudio==2.6.0 \
      --index-url https://download.pytorch.org/whl/cpu
  fi

  echo "PyTorch $(python -c 'import torch; print(torch.__version__)') installed successfully."
  echo "$(python -c 'import torch; print(torch.__version__)')" > "$TORCH_LOCK_FILE"
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