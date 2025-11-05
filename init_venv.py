#!/usr/bin/env python3
"""
Interactive Python Environment Setup Script
Optimized for Qwen2.5 and modern ML workflows
"""

import subprocess
import sys
from pathlib import Path

VENV_DIR = "venv-acct-cik"

# Unsloth handles its own dependencies, including PyTorch, Transformers, etc.

PACKAGES = [
    # Core ML and data handling
    # unsloth installs torch, transformers, peft, accelerate, trl, numpy
    "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git",
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


def install_packages(package_list, description):
    """Install a list of packages"""
    print(f"📦 Installing {description}...")
    packages = " ".join(package_list)
    result = subprocess.run(f"pip install --upgrade {packages}", shell=True)

    if result.returncode == 0:
        print(f"✅ {description} installed successfully.")
    else:
        print(f"❌ Failed to install some {description}.")


def show_menu():
    """Display interactive menu"""
    print("\n" + "=" * 60)
    print("🐍 INTERACTIVE ENVIRONMENT SETUP")
    print("   Optimized for Unsloth")
    print("=" * 60)
    print("\nOptions:")
    print("  1. Install all packages (Base + ML with Unsloth)")
    print("  2. Check current installation")
    print("  3. Exit")
    print("-" * 60)


def check_installation():
    """Check what's currently installed"""
    print("\n🔍 Checking current installation...")
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
        try:
            mod = __import__(pkg)
            version = getattr(mod, "__version__", "unknown")
            print(f"   {pkg}: {version}")
        except ImportError:
            print(f"   {pkg}: Not installed")


def main():
    """Main interactive loop"""
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
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Setup cancelled by user.")
        sys.exit(0)
