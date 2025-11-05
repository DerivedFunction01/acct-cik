#!/usr/bin/env python3
"""
Interactive Python Environment Setup Script
Optimized for Qwen2.5 and modern ML workflows
"""

import subprocess
import sys
import os
import re
import argparse
from pathlib import Path

VENV_DIR = "venv-acct-cik"
TORCH_LOCK_FILE = f"{VENV_DIR}/torch.lock"
USE_VENV = True  # Global flag

BASE_PACKAGES = [
    "pandas",
    "requests",
    "beautifulsoup4",
    "tqdm",
    "psutil",
    "numpy",
    "openpyxl",
    "xlsxwriter",
    "flask",
    "pydrive2",
    "waitress",
    "gunicorn",
    "matplotlib",
]

# Updated versions for Qwen2.5-7B-Instruct compatibility
ML_PACKAGES = [
    "scikit-learn",
    "datasets",
    "transformers>=4.37.0",  # Qwen2.5 requires transformers>=4.37
    "accelerate>=0.26.0",  # Updated for better performance
    "peft>=0.8.0",  # Updated for compatibility
    "trl",
    "IPython",
    "ipywidgets",
    "ipykernel",
    "bitsandbytes",
]


def run_command(cmd, check=True):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(
            cmd, shell=True, check=check, capture_output=True, text=True
        )
        return result.stdout.strip(), result.returncode
    except subprocess.CalledProcessError as e:
        return e.stderr.strip(), e.returncode


def check_gpu():
    """Detect GPU type and return appropriate PyTorch install command"""
    # Check for NVIDIA GPU
    nvidia_output, nvidia_code = run_command("nvidia-smi", check=False)
    if nvidia_code == 0:
        print("🎮 NVIDIA GPU detected.")
        # Extract CUDA version
        match = re.search(r"CUDA Version: (\d+\.\d+)", nvidia_output)
        if match:
            cuda_version = match.group(1)
            print(f"   Detected CUDA version: {cuda_version}")

            cuda_major, cuda_minor = cuda_version.split(".")
            cuda_tag = f"cu{cuda_major}{cuda_minor}"
            print(f"   Using CUDA tag: {cuda_tag}")

            return f"torch torchvision torchaudio --index-url https://download.pytorch.org/whl/{cuda_tag}"

    # Check for AMD GPU
    rocm_output, rocm_code = run_command("rocm-smi", check=False)
    if rocm_code == 0:
        print("🎮 AMD GPU with ROCm detected.")
        return "torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2"

    # Default to CPU
    print("💻 No GPU detected. Using CPU-only PyTorch.")
    return (
        "torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu"
    )


def install_pytorch(force_reinstall=False):
    """Install or update PyTorch based on system configuration"""
    if USE_VENV:
        lock_file = Path(TORCH_LOCK_FILE)
    else:
        lock_file = Path("torch.lock")

    if lock_file.exists() and not force_reinstall:
        print("🧱 PyTorch is locked. Skipping reinstall.")
        print("   (Choose 'Reinstall PyTorch' option to reinstall or upgrade)")
        return

    print("🔄 Installing or updating PyTorch...")
    torch_cmd = check_gpu()

    print(f"   Running: pip install {torch_cmd}")
    result = subprocess.run(f"pip install {torch_cmd}", shell=True)

    if result.returncode == 0:
        # Get installed version
        version_cmd = "python -c 'import torch; print(torch.__version__)'"
        version, _ = run_command(version_cmd)
        print(f"✅ PyTorch {version} installed successfully.")

        # Create lock file
        if USE_VENV:
            lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text(version)
    else:
        print("❌ PyTorch installation failed.")


def install_packages(package_list, description):
    """Install a list of packages"""
    print(f"📦 Installing {description}...")
    packages = " ".join(package_list)
    result = subprocess.run(f"pip install {packages}", shell=True)

    if result.returncode == 0:
        print(f"✅ {description} installed successfully.")
    else:
        print(f"❌ Failed to install some {description}.")


def upgrade_packages():
    """Upgrade key ML packages to latest compatible versions"""
    print("\n🔄 Upgrading ML packages to latest compatible versions...")
    print("   This will upgrade transformers, accelerate, and peft...")

    upgrade_list = ["transformers>=4.37.0", "accelerate>=0.26.0", "peft>=0.8.0"]

    for pkg in upgrade_list:
        print(f"\n   Upgrading {pkg}...")
        result = subprocess.run(f"pip install --upgrade {pkg}", shell=True)
        if result.returncode == 0:
            print(f"   ✅ {pkg} upgraded successfully")
        else:
            print(f"   ❌ Failed to upgrade {pkg}")


def show_menu():
    """Display interactive menu"""
    print("\n" + "=" * 60)
    print("🐍 INTERACTIVE ENVIRONMENT SETUP")
    print("   Optimized for Qwen2.5-7B-Instruct")
    print("=" * 60)
    print("\nOptions:")
    print("  1. Install base packages only")
    print("  2. Install all packages (base + ML)")
    print("  3. Install PyTorch only")
    print("  4. Reinstall PyTorch (force)")
    print("  5. Full setup (PyTorch + all packages)")
    print("  6. Upgrade ML packages (transformers, accelerate, peft)")
    print("  7. Check current installation")
    print("  8. Exit")
    print("-" * 60)


def check_installation():
    """Check what's currently installed"""
    print("\n🔍 Checking current installation...")

    lock_file = Path(TORCH_LOCK_FILE)
    if lock_file.exists():
        version = lock_file.read_text().strip()
        print(f"   PyTorch: {version} (locked)")
    else:
        print("   PyTorch: Not locked")

    # Try to import key packages
    packages_to_check = [
        "torch",
        "pandas",
        "transformers",
        "accelerate",
        "peft",
        "sklearn",
        "trl",
    ]
    for pkg in packages_to_check:
        try:
            mod = __import__(pkg)
            version = getattr(mod, "__version__", "unknown")
            print(f"   {pkg}: {version}")
        except ImportError:
            print(f"   {pkg}: Not installed")

    # Check for Qwen2.5 compatibility
    print("\n📋 Qwen2.5-7B Requirements Check:")
    try:
        import transformers
        from packaging import version

        tf_version = version.parse(transformers.__version__)
        required_version = version.parse("4.37.0")
        if tf_version >= required_version:
            print(f"   ✅ transformers {transformers.__version__} (>= 4.37.0 required)")
        else:
            print(
                f"   ❌ transformers {transformers.__version__} (< 4.37.0, UPGRADE NEEDED)"
            )
    except ImportError:
        print("   ❌ transformers: Not installed")


def main():
    """Main interactive loop"""
    while True:
        show_menu()
        choice = input("\nEnter your choice (1-8): ").strip()

        if choice == "1":
            print("\n📦 Installing base packages only...")
            install_packages(BASE_PACKAGES, "base packages")

        elif choice == "2":
            print("\n📦 Installing all packages...")
            install_packages(BASE_PACKAGES, "base packages")
            install_packages(ML_PACKAGES, "ML packages")

        elif choice == "3":
            print("\n🔄 Installing PyTorch...")
            install_pytorch(force_reinstall=False)

        elif choice == "4":
            print("\n🔄 Reinstalling PyTorch (forced)...")
            install_pytorch(force_reinstall=True)

        elif choice == "5":
            print("\n🚀 Full setup starting...")
            install_pytorch(force_reinstall=False)
            install_packages(BASE_PACKAGES, "base packages")
            install_packages(ML_PACKAGES, "ML packages")
            print("\n✅ Environment setup complete!")

        elif choice == "6":
            upgrade_packages()

        elif choice == "7":
            check_installation()

        elif choice == "8":
            print("\n👋 Goodbye!")
            break

        else:
            print("\n❌ Invalid choice. Please enter 1-8.")

        input("\nPress Enter to continue...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Setup cancelled by user.")
        sys.exit(0)
