import argparse
import os
import subprocess
import sys
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
PID_FILE = "server-roberta.pid"
NGINX_CONF_FILE = "nginx-roberta.conf"
SERVER_SCRIPT = "roberta_server:app"  # Changed to use the new generative model server
CACHE_FILE = ".server_cache-roberta.json"

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
        if cache_age < 60 * 60 * 24:  # 12 hours in seconds
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
        # Use Unsloth to pre-download the new generative model
        from unsloth import FastLanguageModel
        from server2 import MODEL_PATH, MAX_SEQ_LENGTH

        FastLanguageModel.from_pretrained(
            model_name=MODEL_PATH,
            max_seq_length=MAX_SEQ_LENGTH,
            load_in_4bit=True,
        )
        print("✅ Model is available locally.")
        return True
    except ImportError:
        print("⚠️  Could not import 'unsloth'. Skipping model pre-download.")
        print(
            "   Please run 'pip install \"unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git\"' if you encounter issues."
        )
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


def check_waitress():
    """Checks if waitress is installed, which is needed for Windows."""
    if shutil.which("waitress-serve") is not None:
        return True

    print("⚠️  'waitress-serve' command not found.")
    install_prompt = (
        input(
            "   It's needed for Windows support. Install it now? (pip install waitress) [y/N]: "
        )
        .lower()
        .strip()
    )
    if install_prompt == "y":
        subprocess.check_call([sys.executable, "-m", "pip", "install", "waitress"])
        return shutil.which("waitress-serve") is not None
    return False


def check_gunicorn():
    """Checks if gunicorn is installed."""
    if shutil.which("gunicorn") is not None:
        return True

    print("⚠️  'gunicorn' command not found.")
    install_prompt = (
        input(
            "   It's needed for server management. Install it now? (pip install gunicorn) [y/N]: "
        )
        .lower()
        .strip()
    )
    if install_prompt == "y":
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gunicorn"])
        return shutil.which("gunicorn") is not None
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
    # Revised for a 4B parameter model (4-bit quantized)
    if gpu_ram_gb > 0:
        # GPU threads based on VRAM
        if gpu_ram_gb >= 40:  # A100 (40GB/80GB) - Can handle more parallel requests
            gpu_threads = 8
            gpu_weight = 10
        elif gpu_ram_gb >= 24:  # RTX 4090/3090
            gpu_threads = 6
            gpu_weight = 8
        elif gpu_ram_gb >= 16:  # V100, T4, A10
            gpu_threads = 4
            gpu_weight = 6
        elif gpu_ram_gb >= 12:  # RTX 3080, etc.
            gpu_threads = 2
            gpu_weight = 4
        else:  # Low-end GPU
            gpu_threads = 1
            gpu_weight = 2

        # For a large generative model, CPU inference is extremely slow and memory-intensive.
        # It's better to run in GPU-only mode if a GPU is available.
        start_cpu_server = False
        cpu_weight = 0
        print(
            "   Strategy: GPU detected. Forcing GPU-only mode for large model performance."
        )

    # === CPU Configuration ===
    # This only applies if no GPU is detected.
    else:
        print("   Strategy: No GPU detected. Running in CPU-only mode (will be slow).")
        # CPU threads based on core count (be conservative due to high RAM usage)
        if ram_gb < 16:
            print("   -> Low RAM detected. Using minimal CPU threads.")
            cpu_threads = 1
        elif cpu_cores >= 16:
            cpu_threads = 4
        elif cpu_cores >= 8:
            cpu_threads = 2
        else:
            cpu_threads = 1
        cpu_weight = cpu_threads  # Weight proportional to threads
        gpu_weight = 0
        start_cpu_server = True

    # === Adjust weights based on RAM ===
    # If RAM is limited, reduce CPU weight to avoid OOM
    if ram_gb < 8:
        cpu_weight = max(1, cpu_weight // 2)
        cpu_threads = max(1, cpu_threads // 2)
    elif ram_gb < 16:
        cpu_weight = max(1, int(cpu_weight * 0.75))

    return gpu_weight, cpu_weight, gpu_threads, cpu_threads, start_cpu_server


def generate_nginx_config(gpu_weight, cpu_weight, cpu_server_enabled):
    """
    Generates the nginx.conf file with calculated weights.
    """
    # Create a local logs directory to avoid permission issues with /var/log/nginx
    log_dir = os.path.abspath("logs")
    os.makedirs(log_dir, exist_ok=True)
    access_log_path = os.path.join(log_dir, "nginx_access.log").replace(os.sep, "/")
    error_log_path = os.path.join(log_dir, "nginx_error.log").replace(os.sep, "/")
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
    access_log {access_log_path};
    error_log {error_log_path};

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

            # Failover logic: if a server fails, try the next one.
            # This is crucial for redirecting from a failed CPU server to the GPU server.
            # non_idempotent allows POST requests to be retried on the next server.
            proxy_next_upstream error timeout invalid_header http_500 http_502 http_503 http_504 non_idempotent;

            proxy_connect_timeout {GUNICORN_TIMEOUT};
            proxy_send_timeout {GUNICORN_TIMEOUT};
            proxy_read_timeout {GUNICORN_TIMEOUT};
        }}

        # Limit the number of simultaneous connections to prevent overwhelming the backend.
        # This helps queue requests instead of dropping them.
        limit_conn_zone $binary_remote_addr zone=addr:10m;
        limit_conn addr 20; # Allow up to 20 concurrent connections from a single IP
    }}
}}
"""
    with open(NGINX_CONF_FILE, "w") as f:
        f.write(config)


def interactive_config_editor(
    gpu_weight, cpu_weight, gpu_threads, cpu_threads, start_cpu_server, gpu_ram_gb
):
    """Allows the user to interactively modify the server configuration."""
    while True:
        print("\n" + "=" * 70)
        print("🤖 Auto-Detected Server Configuration:")

        # Display GPU options only if a GPU is present
        if gpu_ram_gb > 0:
            print(f"   [1] GPU Weight:   {gpu_weight}")
            print(f"   [2] GPU Threads:  {gpu_threads}")
        else:
            print("   - GPU Server:     Disabled (No GPU detected)")

        # Display CPU options
        cpu_status = "✅ Enabled" if start_cpu_server else "❌ Disabled"
        print(f"   [3] CPU Weight:   {cpu_weight if start_cpu_server else 'N/A'}")
        print(f"   [4] CPU Threads:  {cpu_threads if start_cpu_server else 'N/A'}")
        print(f"   [5] CPU Server:   {cpu_status}")

        print("=" * 70)

        prompt = "Accept this configuration and start servers? [Y/n] or enter a number to edit: "
        choice = input(prompt).lower().strip()

        if choice in ["y", "yes", ""]:
            break  # Accept and exit loop

        if choice == "n":
            print("Please enter the number of the setting you want to change.")
            continue

        try:
            choice_num = int(choice)
            if gpu_ram_gb > 0:
                if choice_num == 1:
                    gpu_weight = int(
                        input(f"   Enter new GPU weight (current: {gpu_weight}): ")
                    )
                elif choice_num == 2:
                    gpu_threads = int(
                        input(f"   Enter new GPU threads (current: {gpu_threads}): ")
                    )

            if choice_num == 3 and start_cpu_server:
                cpu_weight = int(
                    input(f"   Enter new CPU weight (current: {cpu_weight}): ")
                )
            elif choice_num == 4 and start_cpu_server:
                cpu_threads = int(
                    input(f"   Enter new CPU threads (current: {cpu_threads}): ")
                )
            elif choice_num == 5:
                toggle = input(f"   Enable CPU server? [y/N]: ").lower().strip()
                start_cpu_server = toggle == "y"
                if not start_cpu_server:
                    cpu_weight = 0  # Set weight to 0 if disabled
            else:
                # Handle cases where the number is out of range or not applicable
                if not (1 <= choice_num <= 5):
                    print(f"   Invalid number. Please enter a number from the list.")

        except ValueError:
            print(f"   Invalid input '{choice}'. Please enter 'y', 'n', or a number.")

    return gpu_weight, cpu_weight, gpu_threads, cpu_threads, start_cpu_server


def start_servers():
    """Starts the Gunicorn and Nginx servers."""
    # --- Windows-Specific Handling ---
    if is_windows():
        print("ℹ️  Windows detected. Using 'waitress' server instead of Gunicorn/Nginx.")
        if not check_waitress():
            print("❌ Cannot start server on Windows without 'waitress'.")
            return

        model_available = pre_download_model()
        gpu_ram_gb = get_gpu_ram()
        save_cache(model_available, gpu_ram_gb)

        server_env = os.environ.copy()
        if gpu_ram_gb > 0:
            print(f"🚀 Starting server in GPU mode on http://127.0.0.1:{NGINX_PORT}")
            server_env["DEVICE_TYPE"] = "gpu"
        else:
            print(f"🚀 Starting server in CPU mode on http://127.0.0.1:{NGINX_PORT}")
            server_env["DEVICE_TYPE"] = "cpu"

        # Use waitress-serve on Windows. It runs in the foreground.
        waitress_cmd = (
            f"waitress-serve --host 127.0.0.1 --port {NGINX_PORT} {SERVER_SCRIPT}"
        )
        print("   To stop the server, press Ctrl+C in this window.")
        try:
            subprocess.run(waitress_cmd.split(), env=server_env)
        except KeyboardInterrupt:
            print("\n✅ Server stopped by user.")
        except FileNotFoundError:
            print("❌ 'waitress-serve' not found. Please run 'pip install waitress'.")
        except Exception as e:
            print(f"❌ An error occurred while running the server: {e}")
        return  # End of Windows-specific logic

    # --- Linux/macOS Handling ---

    # Check for Nginx before proceeding
    if not check_nginx():
        return

    # Check for gunicorn
    if not check_gunicorn():
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

    # --- Interactive Configuration Step ---
    (
        gpu_weight,
        cpu_weight,
        gpu_threads,
        cpu_threads,
        start_cpu_server,
    ) = interactive_config_editor(
        gpu_weight, cpu_weight, gpu_threads, cpu_threads, start_cpu_server, gpu_ram_gb
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
        gpu_cmd = f"gunicorn --workers 1 --threads {gpu_threads} --timeout {GUNICORN_TIMEOUT} --bind 127.0.0.1:{GPU_SERVER_PORT} --backlog 2048 {SERVER_SCRIPT}"
        gpu_env = os.environ.copy()
        gpu_env["DEVICE_TYPE"] = "gpu"
        subprocess.Popen(gpu_cmd.split(), env=gpu_env)
        print(f"🚀 Launched GPU server.")

    # CPU Server
    if start_cpu_server:
        cpu_cmd = f"gunicorn --workers 1 --threads {cpu_threads} --timeout {GUNICORN_TIMEOUT} --bind 127.0.0.1:{CPU_SERVER_PORT} --backlog 2048 {SERVER_SCRIPT}"
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
    # On Windows, the server runs in the foreground, so it's stopped with Ctrl+C.
    if is_windows():
        print(
            "ℹ️  On Windows, the server runs in the foreground. To stop it, press Ctrl+C in the terminal where it is running."
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
