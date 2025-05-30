import subprocess
import sys
import time
import os
import threading
import queue
from client import GUIUserClient
from gui import ChatWindow, LogWindow

SERVER_SCRIPT = "server.py"
CLIENT_SCRIPT = "client.py"


def main():
    # 1. Launch server (capture output to keep console clean)
    server_proc = subprocess.Popen([
        sys.executable,
        SERVER_SCRIPT,
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1)  # give server time to bind

    # 2. Launch GPT bot and capture logs
    gpt_proc = subprocess.Popen(
        [sys.executable, CLIENT_SCRIPT, "gpt"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    log_window = LogWindow()
    log_queue: queue.Queue[str] = queue.Queue()

    def log_reader():
        for line in gpt_proc.stdout:
            log_queue.put(line.rstrip())

    threading.Thread(target=log_reader, daemon=True).start()

    chat_window = ChatWindow(lambda msg: None)
    chat_client = GUIUserClient("ws://localhost:8765", chat_window.append_message)
    chat_window.send_callback = chat_client.send_message

    def client_thread():
        chat_client.run()

    threading.Thread(target=client_thread, daemon=True).start()

    def poll_logs():
        while not log_queue.empty():
            log_window.append_log(log_queue.get())
        chat_window.root.after(100, poll_logs)

    poll_logs()

    try:
        chat_window.mainloop()
    finally:
        server_proc.terminate()
        gpt_proc.terminate()
        server_proc.wait()
        gpt_proc.wait()

if __name__ == "__main__":
    main()
