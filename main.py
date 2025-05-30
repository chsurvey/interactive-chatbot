import subprocess
import sys
import time
import os
from client import UserClient

SERVER_SCRIPT = "server.py"
CLIENT_SCRIPT = "client.py"


def main():
    # 1. Launch server (capture output to keep console clean)
    server_proc = subprocess.Popen([
        sys.executable,
        SERVER_SCRIPT,
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1)  # give server time to bind

    # 2. Launch GPT bot in background (no console window)
    gpt_proc = subprocess.Popen(
        [sys.executable, CLIENT_SCRIPT, "gpt"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )

    try:
        # 3. Run user client interactively in foreground
        UserClient("ws://localhost:8765").run()
    finally:
        server_proc.terminate()
        gpt_proc.terminate()
        server_proc.wait()
        gpt_proc.wait()

if __name__ == "__main__":
    main()