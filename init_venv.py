#!/usr/bin/env python3
"""
Interactive Python Environment Setup Script
Optimized for Qwen2.5 and modern ML workflows
"""

import subprocess
import sys
import argparse
from pathlib import Path

VENV_DIR = "venv-acct-cik"
USE_VENV = True  # Global flag, can be overridden by --no-venv

# Unsloth handles its own dependencies, including PyTorch, Transformers, etc.

PACKAGES = [
    # Core ML and data handling
    # unsloth installs torch, transformers, peft, accelerate, trl, numpy
    "unsloth[colab-new] git+https://github.com/unslothai/unsloth.git",
    "datasets",  # Installs pandas, requests, tqdm, numpy
    "scikit-learn",
    # Web scraping and server
    "beautifulsoup4",
    "flask",
    "gunicorn",
    "waitress",
    # System and file utilities
    "psutil",
    "openpyxl",
    "xlsxwriter",
    "pydrive2",
    # Plotting and interactive
    "matplotlib",
    "IPython",
]


def get_pip_executable():
    """Returns the path to the pip executable, respecting the venv toggle."""
    if USE_VENV:
        return f"{VENV_DIR}/bin/pip"
    return "pip"


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
        print(f"Found existing virtual environment: '{VENV_DIR}'")


def show_menu():
    """Display interactive menu"""
    print("\n" + "=" * 60)
    print("🐍 INTERACTIVE ENVIRONMENT SETUP")
    print("   Optimized for Unsloth")
    print("=" * 60)
    venv_status = f"ACTIVE (in ./{VENV_DIR})" if USE_VENV else "INACTIVE (global site-packages)"
    print(f"Virtual Environment Status: {venv_status}")
    print("\nOptions:")
    print("  1. Install all packages (Base + ML with Unsloth)")
    print("  2. Check current installation")
    print("  3. Exit")
    print("-" * 60)


def check_installation():
    """Check what's currently installed"""
    print("\n🔍 Checking current installation...")

    python_exec = f"{VENV_DIR}/bin/python" if USE_VENV else sys.executable
    print(f"   Using Python: {python_exec}")

    def get_package_version(pkg_name):
        return subprocess.run(f"{python_exec} -c \"import {pkg_name}; print({pkg_name}.__version__)\"", shell=True, capture_output=True, text=True).stdout.strip()

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


def main():
    """Main interactive loop"""
    global USE_VENV

    parser = argparse.ArgumentParser(description="Interactive environment setup script.")
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="Install packages in the global environment instead of the virtual environment.",
    )
    args = parser.parse_args()

    if args.no_venv:
        USE_VENV = False

    if USE_VENV:
        create_venv()

    while True:
        show_menu()
        choice = input("\nEnter your choice (1-3): ").strip()

        if choice == "1":
            print("\n Full setup starting...")
            install_packages(PACKAGES, "project packages")
            print("\n✅ Environment setup complete!")

        elif choice == "2":
            check_installation()

        elif choice == "3":
            print("\n👋 Goodbye!")
            break

        else:
            print("\n❌ Invalid choice. Please enter 1-3.")

        input("\nPress Enter to continue...")


if __name__ == "__main__":
    main()
