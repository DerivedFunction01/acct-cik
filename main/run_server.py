import argparse
import os
import subprocess
import psutil
import multiprocessing as mp
import platform
import time
import requests

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

def is_windows():
    """Check if the operating system is Windows."""
    return platform.system() == "Windows"

def get_system_resources():
    """Detects system CPU cores and RAM."""
    cpu_cores = mp.cpu_count()
    ram_gb = psutil.virtual_memory().total / (1024**3)
    return cpu_cores, ram_gb

def get_gpu_ram():
    """Queries the server info endpoint to get GPU RAM, if available."""
    try:
        # Temporarily start the GPU server to query its info
        print("Temporarily starting server to detect GPU RAM...")
        cmd = f"gunicorn --workers 1 --threads 1 --bind 127.0.0.1:{GPU_SERVER_PORT} {SERVER_SCRIPT}"
        proc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(5) # Give it a moment to start

        response = requests.get(f"http://127.0.0.1:{GPU_SERVER_PORT}/info", timeout=5)
        if response.status_code == 200:
            info = response.json()
            if info.get("gpu_available"):
                print(f"✅ GPU Detected: {info.get('gpu_name')} with {info.get('total_ram_gb', 0):.2f} GB RAM.")
                return info.get("total_ram_gb", 0)
    except Exception as e:
        print(f"⚠️  Could not query server for GPU info: {e}")
    finally:
        if 'proc' in locals():
            proc.terminate()
            proc.wait()
            print("Temporary server stopped.")
    return 0

def generate_nginx_config():
    """Generates the nginx.conf file for load balancing."""
    config = f"""
worker_processes auto;
pid {os.path.abspath(PID_FILE).replace(os.sep, '/')};

events {{
    worker_connections 1024;
}}

http {{
    upstream model_servers {{
        # GPU server - handles more requests if available
        server 127.0.0.1:{GPU_SERVER_PORT} weight=3;
        # CPU server - takes a smaller portion of the load
        server 127.0.0.1:{CPU_SERVER_PORT};
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
    print(f"✅ Generated '{NGINX_CONF_FILE}' successfully.")

def start_servers():
    """Starts the Gunicorn and Nginx servers."""
    if is_windows():
        print("❌ ERROR: Gunicorn is not supported on Windows. Please use WSL (Windows Subsystem for Linux).")
        return

    cpu_cores, ram_gb = get_system_resources()
    gpu_ram_gb = get_gpu_ram()

    # --- Configure GPU Server ---
    if gpu_ram_gb > 14: # High-end GPU
        gpu_threads = 8
    elif gpu_ram_gb > 6: # Mid-range GPU
        gpu_threads = 4
    else: # Low-end GPU or CPU mode
        gpu_threads = 2

    # --- Configure CPU Server ---
    # Be conservative to avoid memory overload on small machines
    if ram_gb < 8 or cpu_cores < 4:
        cpu_workers = 1 # Very conservative for small machines
        print("⚠️  Low system resources detected. Running CPU server with 1 worker.")
    else:
        # A safe number of workers is num_cores, as each loads a full model.
        cpu_workers = max(1, cpu_cores // 2)

    print("\n" + "="*50)
    print("🚀 Starting Servers with Optimized Configuration:")
    print(f"   - GPU Server: 1 Worker, {gpu_threads} Threads (Port {GPU_SERVER_PORT})")
    print(f"   - CPU Server: {cpu_workers} Workers (Port {CPU_SERVER_PORT})")
    print(f"   - Nginx Load Balancer on Port {NGINX_PORT}")
    print("="*50 + "\n")

    # Generate Nginx config
    generate_nginx_config()

    # --- Launch Processes ---
    # GPU Server
    gpu_cmd = f"gunicorn --workers 1 --threads {gpu_threads} --timeout {GUNICORN_TIMEOUT} --bind 127.0.0.1:{GPU_SERVER_PORT} {SERVER_SCRIPT}"
    gpu_env = os.environ.copy()
    gpu_env["DEVICE_TYPE"] = "gpu"
    subprocess.Popen(gpu_cmd.split(), env=gpu_env)
    print(f"🚀 Launched GPU server.")

    # CPU Server
    cpu_cmd = f"gunicorn --workers {cpu_workers} --timeout {GUNICORN_TIMEOUT} --bind 127.0.0.1:{CPU_SERVER_PORT} {SERVER_SCRIPT}"
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