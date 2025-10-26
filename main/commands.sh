# For Jupyter notebooks
!pip install xlsxwriter
!git clone https://github.com/DerivedFunction/acct-cik
!cp -rf acct-cik/main/* .

!cd acct-cik && git pull && cd ..
!cp -rf acct-cik/main/* .

# For Ubuntu systems, switch to Python 3.12
#!/usr/bin/env bash
set -e

echo "=== Checking for Python 3.12 installation ==="
if ! command -v python3.12 >/dev/null 2>&1; then
    echo "Python 3.12 not found. Installing..."
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update
    sudo apt install -y python3.12 python3.12-venv python3.12-distutils
else
    echo "Python 3.12 already installed."
fi

echo "=== Registering python3 versions with update-alternatives ==="
if [ -x /usr/bin/python3.10 ]; then
    sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 10 || true
fi
if [ -x /usr/bin/python3.12 ]; then
    sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 12 || true
fi

echo "=== Setting python3 default to 3.12 ==="
sudo update-alternatives --set python3 /usr/bin/python3.12

echo "=== Verifying default python3 ==="
python3 --version

echo "Done. python3 now points to:"
readlink -f "$(command -v python3)"
