"""
Interactive Python Environment Setup Script
Optimized for Qwen2.5 and modern ML workflows
Includes automatic GPU detection for PyTorch installation
"""

import subprocess
import sys
import argparse
from pathlib import Path

VENV_DIR = "venv-acct-cik"
USE_VENV = True  # Global flag, can be overridden by --no-venv
GPU_AVAILABLE = False  # Will be "nvidia", "amd", or False
CUDA_VERSION = "cu121"  # Default to CUDA 12.1

BASE_PACKAGES = [
    # Web scraping and server
    "beautifulsoup4",
    "html2text",
    "lxml",
    # System and file utilities
    "psutil",
    "openpyxl",
    "xlsxwriter",
    "pydrive2",
    # Plotting and interactive
    "matplotlib",
    "IPython",
    "pandas",
    # Other
    "num2words",
    "tqdm",
]

# Core dependencies (without torch, which we'll handle specially)
UNSLOTH_PACKAGES_BASE = [
    "torchvision",
    "torchaudio",
    "transformers",
    "peft",
    "accelerate",
    "trl",
    "datasets",
]

# Platform-specific Unsloth installation
if sys.platform == "win32":
    # On Windows, install Unsloth dependencies manually
    UNSLOTH_INSTALL = UNSLOTH_PACKAGES_BASE
else:
    # On Linux/WSL/Mac, use the optimized Unsloth package
    UNSLOTH_INSTALL = [
        "unsloth",
        "unsloth_zoo",
        "torchvision",
        "torchaudio",
    ]

ML_PACKAGES_BASE = [
    "scikit-learn",
    "tensorboardX",
    "flask",
    "flask_cors",
    "gunicorn",
    "waitress",
] + UNSLOTH_INSTALL

PACKAGES = ML_PACKAGES_BASE + BASE_PACKAGES


def detect_nvidia_gpu():
    """Detect if NVIDIA GPU is available and extract CUDA version dynamically"""
    global GPU_AVAILABLE, CUDA_VERSION

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            GPU_AVAILABLE = True
            print("✅ NVIDIA GPU detected!")

            # Try to get GPU info
            try:
                gpu_info = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if gpu_info.returncode == 0:
                    print(f"   GPU: {gpu_info.stdout.strip()}")
            except:
                pass

            # Dynamically extract CUDA version from nvidia-smi output
            try:
                cuda_info = subprocess.run(
                    ["nvidia-smi"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                # Look for pattern like "CUDA Version: 12.1" or "CUDA Version: 11.8"
                import re

                match = re.search(r"CUDA Version: (\d+)\.(\d+)", cuda_info.stdout)
                if match:
                    major, minor = match.groups()
                    CUDA_VERSION = f"cu{major}{minor}"
                    print(f"   Detected CUDA version: {major}.{minor}")
                else:
                    print(
                        f"   Could not parse CUDA version, using default: {CUDA_VERSION}"
                    )
                print(f"   Using PyTorch wheel: {CUDA_VERSION}")
            except Exception as e:
                print(
                    f"   Could not detect CUDA version: {e}, using default: {CUDA_VERSION}"
                )

            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    GPU_AVAILABLE = False
    return False


def detect_amd_gpu():
    """Detect if AMD GPU is available with ROCm"""
    try:
        result = subprocess.run(
            ["rocm-smi"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print("✅ AMD GPU with ROCm detected!")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def get_pytorch_install_cmd():
    """Generate PyTorch installation command based on GPU availability"""
    if GPU_AVAILABLE == "nvidia":
        return f"torch --index-url https://download.pytorch.org/whl/{CUDA_VERSION}"
    elif GPU_AVAILABLE == "amd":
        return "torch --index-url https://download.pytorch.org/whl/rocm6.2"
    else:
        return "torch --index-url https://download.pytorch.org/whl/cpu"


def get_pip_executable():
    """Returns the path to the pip executable, respecting the venv toggle."""
    if not USE_VENV:
        return "pip"

    if sys.platform == "win32":
        return f"{VENV_DIR}\\Scripts\\pip.exe"
    else:
        return f"{VENV_DIR}/bin/pip"


def install_packages(package_list, description):
    """Install a list of packages"""
    print(f"📦 Installing {description}...")
    packages = " ".join(package_list)
    pip_exec = get_pip_executable()
    cmd = f"{pip_exec} install --upgrade {packages}"
    print(f"   Running: {cmd}")
    result = subprocess.run(cmd, shell=True)

    if result.returncode == 0:
        print(f"✅ {description} installed successfully.")
    else:
        print(f"❌ Failed to install some {description}.")


def install_pytorch():
    """Install PyTorch with appropriate GPU support"""
    print(f"📦 Installing PyTorch...")
    torch_cmd = get_pytorch_install_cmd()
    pip_exec = get_pip_executable()
    cmd = f"{pip_exec} install --upgrade {torch_cmd}"
    print(f"   Running: {cmd}")
    result = subprocess.run(cmd, shell=True)

    if result.returncode == 0:
        if GPU_AVAILABLE == "nvidia":
            print(f"✅ PyTorch (NVIDIA GPU {CUDA_VERSION}) installed successfully.")
        elif GPU_AVAILABLE == "amd":
            print(f"✅ PyTorch (AMD ROCm) installed successfully.")
        else:
            print(f"✅ PyTorch (CPU) installed successfully.")
    else:
        print(f"❌ Failed to install PyTorch.")


def create_venv():
    """Creates the virtual environment if it doesn't exist."""
    venv_path = Path(VENV_DIR)
    if not venv_path.exists():
        print(f"🛠️ Creating virtual environment in '{VENV_DIR}'...")
        try:
            subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)
            print(f"✅ Virtual environment created successfully.")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to create virtual environment: {e}")
            sys.exit(1)
    else:
        print(f"✓ Found existing virtual environment: '{VENV_DIR}'")


def show_menu():
    """Display interactive menu"""
    print("\n" + "=" * 60)
    print("🐍 INTERACTIVE ENVIRONMENT SETUP")
    print("   Optimized for Unsloth")
    print("=" * 60)
    venv_status = (
        f"ACTIVE (in ./{VENV_DIR})" if USE_VENV else "INACTIVE (global site-packages)"
    )
    print(f"Virtual Environment Status: {venv_status}")
    platform_info = "Windows" if sys.platform == "win32" else "Linux/WSL/Mac"
    print(f"Platform: {platform_info}")
    gpu_status = (
        f"GPU: Detected ({CUDA_VERSION})"
        if GPU_AVAILABLE == "nvidia"
        else "GPU: Not detected (CPU-only)"
    )
    if GPU_AVAILABLE == "amd":
        gpu_status = "GPU: AMD ROCm detected"
    print(f"{gpu_status}")
    print("\nOptions:")
    print("  0. Basic setup")
    print("  1. Install all packages (Base + ML with Unsloth)")
    print("  2. Check current installation")
    print("  3. Exit")
    print("-" * 60)


def check_installation():
    """Check what's currently installed"""
    print("\n🔍 Checking current installation...")

    if USE_VENV:
        if sys.platform == "win32":
            python_exec = f"{VENV_DIR}\\Scripts\\python.exe"
        else:
            python_exec = f"{VENV_DIR}/bin/python"
    else:
        python_exec = sys.executable

    print(f"   Using Python: {python_exec}")

    def get_package_version(pkg_name):
        cmd = f'{python_exec} -c "import {pkg_name}; print({pkg_name}.__version__)"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip()

    # Try to import key packages
    packages_to_check = [
        "torch",
        "pandas",
        "transformers",
        "accelerate",
        "peft",
        "sklearn",
        "unsloth",
        "trl",
    ]
    for pkg in packages_to_check:
        version = get_package_version(pkg)
        if version:
            print(f"   {pkg}: {version}")
        else:
            print(f"   {pkg}: Not installed")

    # Check GPU support if torch is installed
    print("\n🎮 Checking GPU support...")
    gpu_check_cmd = f"{python_exec} -c \"import torch; print(f'CUDA available: {{torch.cuda.is_available()}}'); print(f'Device: {{torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"CPU\"}}');\""
    subprocess.run(gpu_check_cmd, shell=True)


def main():
    """Main interactive loop"""
    global USE_VENV, GPU_AVAILABLE

    parser = argparse.ArgumentParser(
        description="Interactive environment setup script."
    )
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="Install packages in the global environment instead of the virtual environment.",
    )
    args = parser.parse_args()

    if args.no_venv:
        USE_VENV = False

    print("\n🔍 Detecting hardware...")
    if detect_nvidia_gpu():
        GPU_AVAILABLE = "nvidia"
    elif detect_amd_gpu():
        GPU_AVAILABLE = "amd"
    else:
        print("   No GPU detected. Will use CPU-only PyTorch.")

    if USE_VENV:
        create_venv()

    while True:
        show_menu()
        choice = input("\nEnter your choice (0-3): ").strip()
        if choice == "0":
            print("\nBasic setup starting...")
            install_packages(BASE_PACKAGES, "base packages")
            print("\n✅ Basic setup complete!")
            exit(0)
        elif choice == "1":
            print("\nFull setup starting...")
            install_pytorch()
            install_packages(ML_PACKAGES_BASE, "ML and Unsloth packages")
            install_packages(BASE_PACKAGES, "base packages")
            print("\n✅ Environment setup complete!")
            exit(0)
        elif choice == "2":
            check_installation()
        elif choice == "3":
            print("\n👋 Goodbye!")
            break
        else:
            print("\n❌ Invalid choice. Please enter 0-3.")


if __name__ == "__main__":
    main()
