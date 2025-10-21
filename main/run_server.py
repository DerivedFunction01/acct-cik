import argparse
import os
import subprocess
import psutil
import multiprocessing as mp
import platform
import time
import requests
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

# Gunicorn settings
GUNICORN_TIMEOUT = 120

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def pre_download_model():
    """
    Downloads the Hugging Face model and tokenizer before starting the servers
    to prevent Gunicorn worker timeouts on the first run.
    """
    print("🔍 Checking for model... (This may take a while on first run)")
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        from server import MODEL_PATH  # Import MODEL_PATH from your server script

        AutoTokenizer.from_pretrained(MODEL_PATH)
        AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
        print("✅ Model is available locally.")
    except ImportError:
        print("⚠️  Could not import 'transformers'. Skipping model pre-download.")
        print("   Please run 'pip install transformers torch' if you encounter issues.")
    except Exception as e:
        print(f"❌ An error occurred during model pre-download: {e}")

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
    """Detects GPU and its RAM directly using torch, without starting a server."""
    print("🔎 Detecting GPU RAM...")
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            total_memory_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"✅ GPU Detected: {gpu_name} with {total_memory_gb:.2f} GB RAM.")
            return total_memory_gb
        else:
            print("   - No CUDA-enabled GPU found.")
    except ImportError:
        print("⚠️  'torch' is not installed. Cannot detect GPU. Assuming 0 GB GPU RAM.")
        print("   Please run 'pip install torch' if you encounter issues.")
    except Exception as e:
        print(f"⚠️  An error occurred while detecting GPU: {e}")
    return 0

def generate_nginx_config(gpu_ram: float = 0, cpu_cores: int = 2, cpu_server_enabled: bool = True):
    """
    Generates the nginx.conf file with a dynamic weight for the GPU server
    based on available system resources.
    """
    # Start with a base weight for the GPU server
    gpu_weight = 4

    # Increase weight based on GPU VRAM (more RAM can handle more concurrent requests)
    if gpu_ram > 20:  # High-end GPU (e.g., >20GB VRAM)
        gpu_weight += 3
    elif gpu_ram > 12: # Mid-range GPU (e.g., 12-20GB VRAM)
        gpu_weight += 2
    elif gpu_ram > 6:  # Entry-level GPU (e.g., 6-12GB VRAM)
        gpu_weight += 1

    # Slightly adjust weight based on CPU cores.
    # If the CPU is very weak, lean more heavily on the GPU.
    if cpu_cores < 4:
        gpu_weight += 1

    # Build the upstream block
    if cpu_server_enabled:
        upstream_block = f"""
        # GPU server - handles more requests if available
        server 127.0.0.1:{GPU_SERVER_PORT} weight={gpu_weight};
        # CPU server - takes a smaller portion of the load
        server 127.0.0.1:{CPU_SERVER_PORT};"""
    else:
        upstream_block = f"""
        # Only GPU server is running
        server 127.0.0.1:{GPU_SERVER_PORT};"""

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
    if cpu_server_enabled:
        print(f"✅ Generated '{NGINX_CONF_FILE}' with GPU weight = {gpu_weight}.")
    else:
        print(f"✅ Generated '{NGINX_CONF_FILE}' to route all traffic to the GPU server.")

def start_servers():
    """Starts the Gunicorn and Nginx servers."""
    if is_windows():
        print("❌ ERROR: Gunicorn is not supported on Windows. Please use WSL (Windows Subsystem for Linux).")
        return

    # Check for Nginx before proceeding
    if not check_nginx():
        return

    # Pre-download the model to prevent worker timeouts
    pre_download_model()

    cpu_cores, ram_gb = get_system_resources()
    gpu_ram_gb = get_gpu_ram()

    # --- Configure GPU Server ---
    if gpu_ram_gb > 14: # High-end GPU
        gpu_threads = 8
    elif gpu_ram_gb > 6: # Mid-range GPU
        gpu_threads = 4
    else: # Low-end GPU or CPU mode
        gpu_threads = 2

    # --- Configure CPU Server (using threads for memory safety) ---
    # Using a single worker and multiple threads is safer for memory, as the model is only loaded once.
    # This prevents overloading the system with multiple copies of a large model in RAM.
    if cpu_cores >= 8:
        cpu_threads = 4 # Good balance for machines with many cores
    elif cpu_cores >= 4:
        cpu_threads = 2 # A safe default for standard machines
    else:
        cpu_threads = 1 # Very conservative for small machines

    # --- Decide whether to start the CPU server ---
    start_cpu_server = True
    if gpu_ram_gb > 0 and (cpu_cores < 4 or ram_gb < 8):
        start_cpu_server = False
        print("⚠️  Low system resources (CPU/RAM) detected with a GPU present.")
        print("   -> The CPU server will NOT be started to conserve resources.")

    print("\n" + "="*50)
    print("🚀 Starting Servers with Optimized Configuration:")
    if gpu_ram_gb > 0:
        print(f"   - GPU Server: 1 Worker, {gpu_threads} Threads (Port {GPU_SERVER_PORT})")
    if start_cpu_server:
        print(f"   - CPU Server: 1 Worker, {cpu_threads} Threads (Port {CPU_SERVER_PORT})")
    
    print(f"   - Nginx Load Balancer on Port {NGINX_PORT}")
    print("="*50 + "\n")

    # Generate Nginx config
    generate_nginx_config(gpu_ram=gpu_ram_gb, cpu_cores=cpu_cores, cpu_server_enabled=start_cpu_server)

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
    print(f"\n✅ All services started. Your application is available at http://127.0.0.1:{NGINX_PORT}")

def stop_servers():
    """Stops the Gunicorn and Nginx servers."""
    if is_windows():
        print("❌ ERROR: This script cannot manage processes on Windows. Please stop them manually.")
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
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "action",
        nargs="?",  # Make the action optional
        default=None,  # Default to None if no action is provided
        choices=["start", "stop", "restart", "status"],
        help="""
start   - Start the Gunicorn and Nginx servers.
stop    - Stop all running servers.
restart - Stop and then start all servers.
status  - Check if the servers are running.

If no action is provided, the script will intelligently start or stop the servers.
"""
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
