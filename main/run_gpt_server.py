import argparse
import os
import subprocess
import sys
import psutil
import platform
import time
import json
import shutil

# =============================================================================
# CONFIGURATION
# =============================================================================

MODEL_PATH = "DerivedFunction/Qwen3-1.7B-derivatives-classifier"
MODEL_SIZE_GB = 3.5
ESTIMATED_OVERHEAD_GB = 1.0

NGINX_PORT = 5000
GPU_SERVER_PORT = 5001

PID_FILE = "server.pid"
NGINX_CONF_FILE = "nginx.conf"
SERVER_SCRIPT = "server:app"
CACHE_FILE = ".server_cache.json"
CONFIG_FILE = ".server_config.json"

GUNICORN_TIMEOUT = 120

# =============================================================================
# CONFIGURATION FILE MANAGEMENT
# =============================================================================


def save_config(num_threads_per_process, gpu_ram_gb):
    config = {
        "timestamp": time.time(),
        "num_processes": 1,
        "num_threads_per_process": num_threads_per_process,
        "gpu_ram_gb": gpu_ram_gb,
        "notes": "Single-process mode. Edit num_threads_per_process manually if needed.",
    }
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        print(f"Configuration saved to '{CONFIG_FILE}'")
    except IOError as e:
        print(f"Could not write config file: {e}")


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


# =============================================================================
# CACHING FUNCTIONS
# =============================================================================


def load_cache():
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
        if time.time() - cache.get("timestamp", 0) < 60 * 60 * 24:
            return cache
    except (json.JSONDecodeError, IOError):
        pass
    return None


def save_cache(model_available, gpu_ram_gb):
    cache = {
        "timestamp": time.time(),
        "model_available": model_available,
        "gpu_ram_gb": gpu_ram_gb,
    }
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except IOError as e:
        print(f"Could not write cache file: {e}")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def pre_download_model():
    cache = load_cache()
    if cache and cache.get("model_available"):
        print("Model is available (cached).")
        return True
    print("Checking for model...")
    try:
        from transformers import AutoTokenizer

        AutoTokenizer.from_pretrained(MODEL_PATH)
        print("Model is available locally.")
        return True
    except ImportError:
        print("Could not import 'transformers'.")
        return False
    except Exception as e:
        print(f"Model pre-download error: {e}")
        return False


def check_nginx():
    if shutil.which("nginx") is not None:
        print("Nginx is available.")
        return True
    print("ERROR: 'nginx' command not found.")
    if platform.system() == "Linux":
        try:
            distro_id = platform.freedesktop_os_release().get("ID")
            if distro_id in ["ubuntu", "debian"]:
                install = (
                    input("Install it? (sudo apt install nginx) [y/N]: ")
                    .lower()
                    .strip()
                    == "y"
                )
                if install:
                    subprocess.check_call("sudo apt update".split())
                    subprocess.check_call("sudo apt install -y nginx".split())
                    return shutil.which("nginx") is not None
        except Exception:
            pass
    print("Please install Nginx manually.")
    return False


def check_gunicorn():
    if shutil.which("gunicorn") is not None:
        return True
    print("'gunicorn' not found.")
    install = input("Install it? (pip install gunicorn) [y/N]: ").lower().strip() == "y"
    if install:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gunicorn"])
        return shutil.which("gunicorn") is not None
    return False


def check_uvicorn():
    if shutil.which("uvicorn") is not None:
        return True
    try:
        import uvicorn

        return True
    except Exception:
        pass
    print("'uvicorn' not found. Needed for Gunicorn + FastAPI.")
    install = (
        input("Install it? (pip install uvicorn[standard]) [y/N]: ").lower().strip()
        == "y"
    )
    if install:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "uvicorn[standard]"]
        )
        try:
            import uvicorn

            return True
        except Exception:
            return False
    return False


def check_waitress():
    if shutil.which("waitress-serve") is not None:
        return True
    print("'waitress-serve' not found.")
    install = input("Install it? (pip install waitress) [y/N]: ").lower().strip() == "y"
    if install:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "waitress"])
        return shutil.which("waitress-serve") is not None
    return False


def is_windows():
    return platform.system() == "Windows"


def get_gpu_ram():
    cache = load_cache()
    if cache and "gpu_ram_gb" in cache:
        gpu_ram = cache["gpu_ram_gb"]
        print(
            f"GPU RAM: {gpu_ram:.2f} GB (cached)."
            if gpu_ram > 0
            else "No GPU (cached)."
        )
        return gpu_ram
    print("Detecting GPU RAM...")
    gpu_ram = 0
    try:
        import torch

        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_ram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"GPU: {gpu_name} with {gpu_ram:.2f} GB RAM.")
        else:
            print("No CUDA GPU found.")
    except ImportError:
        print("'torch' not installed.")
    except Exception as e:
        print(f"GPU detection error: {e}")
    return gpu_ram


def interactive_config_editor(threads_per_process, gpu_ram_gb):
    while True:
        print("\n" + "=" * 60)
        print("Server Configuration (Single Process):")
        print(f"   [1] Threads per Process: {threads_per_process}")
        print(f"   GPU Memory:              {gpu_ram_gb:.2f} GB")
        print("=" * 60)
        choice = input("Accept? [Y/n] or 1 to edit threads: ").lower().strip()
        if choice in ["y", "yes", ""]:
            break
        if choice == "1":
            threads_per_process = max(
                1,
                min(int(input(f"New threads (current: {threads_per_process}): ")), 16),
            )
        else:
            print("Invalid input.")
    return threads_per_process


def generate_nginx_config():
    log_dir = os.path.abspath("logs")
    os.makedirs(log_dir, exist_ok=True)
    access_log = os.path.join(log_dir, "nginx_access.log").replace(os.sep, "/")
    error_log = os.path.join(log_dir, "nginx_error.log").replace(os.sep, "/")
    config = f"""
worker_processes auto;
pid {os.path.abspath(PID_FILE).replace(os.sep, '/')};

events {{
    worker_connections 1024;
}}

http {{
    access_log {access_log};
    error_log {error_log};

    upstream model_server {{
        server 127.0.0.1:{GPU_SERVER_PORT};
    }}

    server {{
        listen {NGINX_PORT};
        server_name localhost;

        location / {{
            proxy_pass http://model_server;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout {GUNICORN_TIMEOUT};
            proxy_send_timeout {GUNICORN_TIMEOUT};
            proxy_read_timeout {GUNICORN_TIMEOUT};
            proxy_buffering off;
        }}
    }}
}}
"""
    with open(NGINX_CONF_FILE, "w") as f:
        f.write(config)
    print("Nginx config generated (single backend)")


def start_servers():
    if is_windows():
        print("Windows detected. Using waitress.")
        if not check_waitress():
            return
        model_available = pre_download_model()
        gpu_ram_gb = get_gpu_ram()
        save_cache(model_available, gpu_ram_gb)
        print(f"Starting waitress on http://127.0.0.1:{NGINX_PORT}")
        cmd = f"waitress-serve --host 127.0.0.1 --port {NGINX_PORT} {SERVER_SCRIPT}"
        try:
            subprocess.run(cmd.split())
        except KeyboardInterrupt:
            print("Server stopped.")
        return

    if not check_nginx() or not check_gunicorn() or not check_uvicorn():
        return

    model_available = pre_download_model()
    gpu_ram_gb = get_gpu_ram()
    save_cache(model_available, gpu_ram_gb)

    threads_per_process = 1
    threads_per_process = interactive_config_editor(threads_per_process, gpu_ram_gb)
    save_config(threads_per_process, gpu_ram_gb)

    print("\n" + "=" * 60)
    print("Starting single-process server")
    print("=" * 60 + "\n")

    generate_nginx_config()

    cmd = (
        f"gunicorn --workers 1 --threads {threads_per_process} --timeout {GUNICORN_TIMEOUT} "
        f"-k uvicorn.workers.UvicornWorker --bind 127.0.0.1:{GPU_SERVER_PORT} {SERVER_SCRIPT}"
    )
    proc = subprocess.Popen(cmd.split())
    print(f"Launched model process on port {GPU_SERVER_PORT}")

    nginx_cmd = f"nginx -c {os.path.abspath(NGINX_CONF_FILE)}"
    subprocess.Popen(nginx_cmd.split())
    print(f"Launched Nginx on port {NGINX_PORT}\n")
    print(f"Server running at http://127.0.0.1:{NGINX_PORT}")

    try:
        proc.wait()
    except KeyboardInterrupt:
        stop_servers()


def stop_servers():
    print("Stopping services...")
    if os.path.exists(PID_FILE):
        subprocess.run(
            f"nginx -s stop -c {os.path.abspath(NGINX_CONF_FILE)}".split(), check=False
        )
        print("Nginx stopped.")
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
    subprocess.run(f"pkill -f 'gunicorn.*{SERVER_SCRIPT}'", shell=True, check=False)
    print("Gunicorn stopped.")
    print("All services stopped.")


# =============================================================================
# MAIN CLI
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manage FastAPI server (single process)."
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=["start", "stop", "restart", "status", "clear-cache"],
        help="start, stop, restart, status, clear-cache",
    )
    args = parser.parse_args()
    action = args.action

    if action is None:
        print(
            "Starting server..."
            if not os.path.exists(PID_FILE)
            else "Stopping server..."
        )
        stop_servers() if os.path.exists(PID_FILE) else start_servers()
    elif action == "start":
        start_servers()
    elif action == "stop":
        stop_servers()
    elif action == "restart":
        stop_servers()
        time.sleep(3)
        start_servers()
    elif action == "status":
        print("RUNNING" if os.path.exists(PID_FILE) else "STOPPED")
    elif action == "clear-cache":
        for f in [CACHE_FILE, CONFIG_FILE]:
            if os.path.exists(f):
                os.remove(f)
                print(f"{f} cleared.")
