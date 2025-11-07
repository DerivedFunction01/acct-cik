# For Jupyter notebooks
!git clone https://github.com/DerivedFunction/acct-cik
!cp -rf acct-cik/main/* .

!python init_venv.py --no-venv

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

echo "🔧 Starting setup process..."

# 1. Go to base directory and clone repo
cd /c/Users/del226
if [ ! -d "acct-cik" ]; then
    echo "📦 Cloning repository..."
    git clone https://github.com/DerivedFunction/acct-cik
else
    echo "✓ Repository already exists"
fi

# 2. Copy secrets file
cd acct-cik/main
echo "📋 Copying secrets file..."
cp /h/client_secrets.json .

# 3. Extract WinPython if needed
if [ ! -d "/c/Users/del226/WPy64-31241" ]; then
    echo "📦 Extracting WinPython..."
    /h/winpython/Winpython64-3.12.4.1.exe
fi

# 4. Run init_venv.sh AND launch workers - all inside WinPython PowerShell's sh environment
echo "🐍 Initializing virtual environment and launching workers..."

for i in $(seq 1 5); do
    echo "🔁 Launching WinPython PowerShell Prompt (run $i of 5)..."
    powershell.exe -NoProfile -Command "& { & 'C:\Users\del226\WPy64-31241\WinPython Powershell Prompt.exe' }"
done

echo ""
echo "✅ Setup complete! Command is copied to clipboard"

printf "source /h/.bashrc && \
cd /c/Users/del226/acct-cik && \
./init_venv.sh && \
source ./venv-acct-cik/Scripts/activate && \
cd main" | clip