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

#!/usr/bin/env bash
set -e  # exit on error

# 1. Go to base directory
cd /c/Users/del226

# 2. Clone the repo (skip if already exists)
if [ ! -d "acct-cik" ]; then
    git clone https://github.com/DerivedFunction/acct-cik
fi

# 3. Go into the main project folder
cd acct-cik/main

# 4. Copy secrets file
cp /h/client_secrets.json .

# 5. Install WinPython (optional if already installed)
# NOTE: This line will run the installer and block until it completes.
#       It only needs to run once ever.
/h/winpython/Winpython64-3.12.4.1.exe

# 6. Initialize virtual environment (waits until finished)
cd /c/Users/del226/acct-cik
bash ./init_venv.sh

# 7. Launch 4 Git Bash terminals using WinPython’s Python from venv
# Each window activates the venv and stays open
for ((i=1; i<=4; i++)); do
    setsid "C:/Program Files/Git/bin/bash.exe" -c "
        cd /c/Users/del226/acct-cik &&
        source venv_acct_cik/Scripts/activate &&
        cd main &&
        echo 'Worker $i started and venv activated.' &&
        exec bash
    " &
done

echo "✅ All workers launched in Git Bash terminals."