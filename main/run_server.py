import argparse
import os
import subprocess
import psutil
import multiprocessing as mp
import platform
import time
import json
import shutil

# =============================================================================
# CONFIGURATION
# =============================================================================

# Server ports
NGINX_PORT = 5000
GPU_SERVER_PORT = 5001
CPU_SERVER_PORT = 5002

# File paths
PID_FILE = "server.pid"
NGINX_CONF_FILE = "nginx.conf"
SERVER_SCRIPT = "server:app"
CACHE_FILE = ".server_cache.json"

# Gunicorn settings
GUNICORN_TIMEOUT = 120

# =============================================================================
# CACHING FUNCTIONS
# =============================================================================


def load_cache():
    """Load cached system info if it exists and is recent (< 24 hours old)."""
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache is less than 24 hours old
        cache_age = time.time() - cache.get("timestamp", 0)
        if cache_age < 86400 * 7:  # 7 days in seconds
            return cache
    except (json.JSONDecodeError, IOError):
        pass

    return None


def save_cache(model_available, gpu_ram_gb):
    """Save system info to cache file."""
    cache = {
        "timestamp": time.time(),
        "model_available": model_available,
        "gpu_ram_gb": gpu_ram_gb,
    }
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except IOError as e:
        print(f"⚠️  Could not write cache file: {e}")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def pre_download_model():
    """
    Downloads the Hugging Face model and tokenizer before starting the servers
    to prevent Gunicorn worker timeouts on the first run.
    Returns True if model is available, False otherwise.
    """
    # Check cache first
    cache = load_cache()
    if cache and cache.get("model_available"):
        print("✅ Model is available (cached).")
        return True

    print("🔍 Checking for model... (This may take a while on first run)")
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        from server import MODEL_PATH  # Import MODEL_PATH from your server script

        AutoTokenizer.from_pretrained(MODEL_PATH)
        AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
        print("✅ Model is available locally.")
        return True
    except ImportError:
        print("⚠️  Could not import 'transformers'. Skipping model pre-download.")
        print("   Please run 'pip install transformers torch' if you encounter issues.")
        return False
    except Exception as e:
        print(f"❌ An error occurred during model pre-download: {e}")
        return False


def check_nginx():
    """
    Checks if nginx is installed. If not, prompts to install it on Debian-based systems.
    """
    if shutil.which("nginx") is not None:
        print("✅ Nginx is available.")
        return True

    print("❌ ERROR: 'nginx' command not found.")
    print("   The server management script requires Nginx for load balancing.")

    # Attempt to auto-install on Debian-based systems
    if platform.system() == "Linux":
        try:
            distro_id = platform.freedesktop_os_release().get("ID")
            if distro_id in ["ubuntu", "debian"]:
                install_prompt = (
                    input(
                        "   Would you like to try and install it now? (sudo apt install nginx) [y/N]: "
                    )
                    .lower()
                    .strip()
                )
                if install_prompt == "y":
                    print(
                        "   -> Running 'sudo apt update && sudo apt install -y nginx'..."
                    )
                    try:
                        subprocess.check_call("sudo apt update".split())
                        subprocess.check_call("sudo apt install -y nginx".split())
                        if shutil.which("nginx"):
                            print("   ✅ Nginx installed successfully.")
                            return True
                        else:
                            print(
                                "   ❌ Installation failed. Please install Nginx manually."
                            )
                            return False
                    except (
                        subprocess.CalledProcessError,
                        FileNotFoundError,
                    ) as install_err:
                        print(f"   ❌ Installation failed: {install_err}")
                        print(
                            "      Please try installing Nginx manually: sudo apt install nginx"
                        )
                        return False
        except (AttributeError, FileNotFoundError):
            # Could not determine Linux distribution
            pass

    print("   Please install Nginx to continue.")
    print(
        "   On Debian/Ubuntu, you can run: sudo apt update && sudo apt install -y nginx"
    )
    return False


def is_windows():
    """Check if the operating system is Windows."""
    return platform.system() == "Windows"


def get_system_resources():
    """Detects system CPU cores and RAM."""
    cpu_cores = mp.cpu_count()
    ram_gb = psutil.virtual_memory().total / (1024**3)
    return cpu_cores, ram_gb


def get_gpu_ram():
    """Detects GPU and its RAM directly using torch, with caching."""
    # Check cache first
    cache = load_cache()
    if cache and "gpu_ram_gb" in cache:
        gpu_ram = cache["gpu_ram_gb"]
        if gpu_ram > 0:
            print(f"✅ GPU RAM: {gpu_ram:.2f} GB (cached).")
        else:
            print("   - No GPU detected (cached).")
        return gpu_ram

    print("🔎 Detecting GPU RAM...")
    gpu_ram = 0
    try:
        import torch

        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_ram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"✅ GPU Detected: {gpu_name} with {gpu_ram:.2f} GB RAM.")
        else:
            print("   - No CUDA-enabled GPU found.")
    except ImportError:
        print("⚠️  'torch' is not installed. Cannot detect GPU. Assuming 0 GB GPU RAM.")
        print("   Please run 'pip install torch' if you encounter issues.")
    except Exception as e:
        print(f"⚠️  An error occurred while detecting GPU: {e}")

    return gpu_ram


def calculate_server_weights(gpu_ram_gb, cpu_cores, ram_gb):
    """
    Calculate optimal GPU and CPU server weights based on hardware.
    Returns (gpu_weight, cpu_weight, gpu_threads, cpu_threads, start_cpu_server)
    """
    # Base configuration
    gpu_weight = 1
    cpu_weight = 1
    gpu_threads = 2
    cpu_threads = 1
    start_cpu_server = True

    # === GPU Configuration ===
    if gpu_ram_gb > 0:
        # GPU threads based on VRAM
        if gpu_ram_gb >= 40:  # A100 (40GB/80GB)
            gpu_threads = 16
            gpu_weight = 20
        elif gpu_ram_gb >= 24:  # A100 24GB, RTX 4090/3090
            gpu_threads = 12
            gpu_weight = 16
        elif gpu_ram_gb >= 16:  # V100, RTX 4080, A10
            gpu_threads = 10
            gpu_weight = 12
        elif gpu_ram_gb >= 12:  # RTX 3080 Ti, T4 (16GB)
            gpu_threads = 8
            gpu_weight = 10
        elif gpu_ram_gb >= 8:  # RTX 3070, 4060 Ti
            gpu_threads = 6
            gpu_weight = 8
        elif gpu_ram_gb >= 6:  # RTX 3060
            gpu_threads = 4
            gpu_weight = 6
        else:  # Low-end GPU
            gpu_threads = 2
            gpu_weight = 4

    # === CPU Configuration ===
    # CPU threads based on core count
    if cpu_cores >= 80:  # TPU or high-core server (treat as very powerful)
        cpu_threads = 16
        cpu_weight = 12
    elif cpu_cores >= 32:  # High-end server/workstation
        cpu_threads = 8
        cpu_weight = 8
    elif cpu_cores >= 16:  # Mid-high workstation
        cpu_threads = 6
        cpu_weight = 6
    elif cpu_cores >= 12:  # Gaming PC / Colab standard
        cpu_threads = 4
        cpu_weight = 4
    elif cpu_cores >= 8:  # Standard desktop
        cpu_threads = 3
        cpu_weight = 3
    elif cpu_cores >= 4:  # Entry-level
        cpu_threads = 2
        cpu_weight = 2
    else:  # Very low-end (2 cores)
        cpu_threads = 1
        cpu_weight = 1

    # === Adjust weights based on RAM ===
    # If RAM is limited, reduce CPU weight to avoid OOM
    if ram_gb < 8:
        cpu_weight = max(1, cpu_weight // 2)
        cpu_threads = max(1, cpu_threads // 2)
    elif ram_gb < 16:
        cpu_weight = max(1, int(cpu_weight * 0.75))

    # === Decide whether to start CPU server ===
    # Scenarios where CPU server should be disabled:
    # 1. Very powerful GPU + weak CPU/RAM (let GPU handle everything)
    # 2. Very limited resources overall

    if gpu_ram_gb > 0:
        # CPU has little cores (~2)
        if cpu_cores <= 2:
            start_cpu_server = False
            print("   Strategy: Poor CPU/RAM → GPU-only mode")
        # High-end GPU with low-end CPU
        elif gpu_ram_gb >= 4 and (cpu_cores <= 4 or ram_gb < 12):
            start_cpu_server = False
            print("   Strategy: GPU-focused + limited CPU/RAM → GPU-only mode")

        # Gaming PC scenario: strong GPU + strong CPU
        elif gpu_ram_gb >= 8 and cpu_cores >= 16 and ram_gb >= 24:
            # Balance the load more evenly for powerful systems
            gpu_weight = min(gpu_weight, cpu_weight + 4)
            print("   Strategy: Balanced high-end system → GPU leads, CPU assists")

        # Colab-like scenario: Good GPU, decent CPU
        elif gpu_ram_gb >= 12 and cpu_cores >= 8:
            print("   Strategy: Cloud GPU instance → GPU primary, CPU backup")

        # Low-end GPU with many cores (e.g., TPU environment)
        elif cpu_cores >= 80:
            # Treat TPU-like environments as CPU-focused
            cpu_weight = max(cpu_weight, gpu_weight)
            print("   Strategy: TPU/High-core environment → Balanced distribution")

    else:
        # No GPU - CPU only
        print("   Strategy: CPU-only mode")
        start_cpu_server = True
        gpu_weight = 0

    # === Final adjustments ===
    # Never make weights too extreme
    if gpu_ram_gb > 0 and start_cpu_server:
        ratio = gpu_weight / max(cpu_weight, 1)
        if ratio > 10:  # GPU shouldn't dominate too much
            gpu_weight = cpu_weight * 10

    return gpu_weight, cpu_weight, gpu_threads, cpu_threads, start_cpu_server


def generate_nginx_config(gpu_weight, cpu_weight, cpu_server_enabled):
    """
    Generates the nginx.conf file with calculated weights.
    """
    # Build the upstream block
    if cpu_server_enabled:
        upstream_block = f"""
        # GPU server - handles more requests if available
        server 127.0.0.1:{GPU_SERVER_PORT} weight={gpu_weight};
        # CPU server - takes a smaller portion of the load
        server 127.0.0.1:{CPU_SERVER_PORT} weight={cpu_weight};"""
        print(f"✅ Nginx config: GPU weight={gpu_weight}, CPU weight={cpu_weight}")
    else:
        upstream_block = f"""
        # Only GPU server is running
        server 127.0.0.1:{GPU_SERVER_PORT};"""
        print(f"✅ Nginx config: GPU-only mode")

    config = f"""
worker_processes auto;
pid {os.path.abspath(PID_FILE).replace(os.sep, '/')};

events {{
    worker_connections 1024;
}}

http {{
    upstream model_servers {{
        {upstream_block}
    }}

    server {{
        listen {NGINX_PORT};
        server_name localhost;

        location / {{
            proxy_pass http://model_servers;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout {GUNICORN_TIMEOUT};
            proxy_send_timeout {GUNICORN_TIMEOUT};
            proxy_read_timeout {GUNICORN_TIMEOUT};
        }}
    }}
}}
"""
    with open(NGINX_CONF_FILE, "w") as f:
        f.write(config)


def start_servers():
    """Starts the Gunicorn and Nginx servers."""
    if is_windows():
        print(
            "❌ ERROR: Gunicorn is not supported on Windows. Please use WSL (Windows Subsystem for Linux)."
        )
        return

    # Check for Nginx before proceeding
    if not check_nginx():
        return

    # Pre-download the model and get GPU info
    model_available = pre_download_model()
    cpu_cores, ram_gb = get_system_resources()
    gpu_ram_gb = get_gpu_ram()

    # Save to cache
    save_cache(model_available, gpu_ram_gb)

    # Calculate optimal configuration
    gpu_weight, cpu_weight, gpu_threads, cpu_threads, start_cpu_server = (
        calculate_server_weights(gpu_ram_gb, cpu_cores, ram_gb)
    )

    print("\n" + "=" * 70)
    print("🚀 Starting Servers with Optimized Configuration:")
    print(
        f"   System: {cpu_cores} CPU cores, {ram_gb:.1f} GB RAM, {gpu_ram_gb:.1f} GB GPU"
    )
    print("-" * 70)
    if gpu_ram_gb > 0:
        print(
            f"   - GPU Server: 1 Worker, {gpu_threads} Threads (Port {GPU_SERVER_PORT})"
        )
    if start_cpu_server:
        print(
            f"   - CPU Server: 1 Worker, {cpu_threads} Threads (Port {CPU_SERVER_PORT})"
        )
    print(f"   - Nginx Load Balancer on Port {NGINX_PORT}")
    print("=" * 70 + "\n")

    # Generate Nginx config
    generate_nginx_config(gpu_weight, cpu_weight, start_cpu_server)

    # --- Launch Processes ---
    # GPU Server (if available)
    if gpu_ram_gb > 0:
        gpu_cmd = f"gunicorn --workers 1 --threads {gpu_threads} --timeout {GUNICORN_TIMEOUT} --bind 127.0.0.1:{GPU_SERVER_PORT} {SERVER_SCRIPT}"
        gpu_env = os.environ.copy()
        gpu_env["DEVICE_TYPE"] = "gpu"
        subprocess.Popen(gpu_cmd.split(), env=gpu_env)
        print(f"🚀 Launched GPU server.")

    # CPU Server
    if start_cpu_server:
        cpu_cmd = f"gunicorn --workers 1 --threads {cpu_threads} --timeout {GUNICORN_TIMEOUT} --bind 127.0.0.1:{CPU_SERVER_PORT} {SERVER_SCRIPT}"
        cpu_env = os.environ.copy()
        cpu_env["DEVICE_TYPE"] = "cpu"
        subprocess.Popen(cpu_cmd.split(), env=cpu_env)
        print(f"🚀 Launched CPU server.")

    # Nginx Server
    nginx_cmd = f"nginx -c {os.path.abspath(NGINX_CONF_FILE)}"
    subprocess.Popen(nginx_cmd.split())
    print(f"🚀 Launched Nginx load balancer.")
    print(
        f"\n✅ All services started. Your application is available at http://127.0.0.1:{NGINX_PORT}"
    )


def stop_servers():
    """Stops the Gunicorn and Nginx servers."""
    if is_windows():
        print(
            "❌ ERROR: This script cannot manage processes on Windows. Please stop them manually."
        )
        return

    print("🛑 Stopping all services...")

    # Stop Nginx
    if os.path.exists(PID_FILE):
        nginx_stop_cmd = f"nginx -s stop -c {os.path.abspath(NGINX_CONF_FILE)}"
        subprocess.run(nginx_stop_cmd.split(), check=False)
        print("   - Nginx stopped.")
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
    else:
        print("   - Nginx PID file not found, may already be stopped.")

    # Stop Gunicorn processes
    # This is a bit aggressive but effective. It finds and kills processes listening on the specific ports.
    try:
        subprocess.run(f"pkill -f 'gunicorn.*{SERVER_SCRIPT}'", shell=True, check=False)
        print("   - Gunicorn processes stopped.")
    except Exception as e:
        print(f"   - Could not stop Gunicorn processes automatically: {e}")
        print(f"   - You may need to stop them manually: pkill -f gunicorn")

    print("✅ All services stopped.")


# =============================================================================
# MAIN CLI
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manage the Gunicorn and Nginx servers for the model API.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "action",
        nargs="?",  # Make the action optional
        default=None,  # Default to None if no action is provided
        choices=["start", "stop", "restart", "status", "clear-cache"],
        help="""
start       - Start the Gunicorn and Nginx servers.
stop        - Stop all running servers.
restart     - Stop and then start all servers.
status      - Check if the servers are running.
clear-cache - Clear the cached system information.

If no action is provided, the script will intelligently start or stop the servers.
""",
    )

    args = parser.parse_args()
    action = args.action

    # If no action is specified, intelligently start or stop
    if action is None:
        # The PID file is a good indicator of whether Nginx was started.
        if os.path.exists(PID_FILE):
            print("ℹ️ Servers appear to be running. Stopping them now.")
            stop_servers()
        else:
            print("ℹ️ Servers appear to be stopped. Starting them now.")
            start_servers()
    elif action == "start":
        start_servers()
    elif action == "stop":
        stop_servers()
    elif action == "restart":
        stop_servers()
        print("\nRestarting in 3 seconds...")
        time.sleep(3)
        start_servers()
    elif action == "status":
        if os.path.exists(PID_FILE):
            print("✅ Servers appear to be RUNNING.")
        else:
            print("❌ Servers appear to be STOPPED.")
    elif action == "clear-cache":
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            print("✅ Cache cleared. Next start will re-detect system resources.")
        else:
            print("ℹ️ No cache file found.")
