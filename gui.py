import tkinter as tk
from tkinter.scrolledtext import ScrolledText

class ChatWindow:
    def __init__(self, send_callback):
        self.root = tk.Tk()
        self.root.title("Chat")
        self.text = ScrolledText(self.root, state="disabled", width=50, height=20)
        self.text.pack(padx=5, pady=5)
        self.entry = tk.Entry(self.root, width=50)
        self.entry.pack(padx=5, pady=5)
        self.entry.bind("<Return>", self.on_send)
        self.send_callback = send_callback

    def on_send(self, event=None):
        msg = self.entry.get().strip()
        if msg:
            self.send_callback(msg)
            self.append_message(f"You: {msg}")
            self.entry.delete(0, tk.END)

    def append_message(self, msg: str):
        def _append():
            self.text.configure(state="normal")
            self.text.insert(tk.END, msg + "\n")
            self.text.configure(state="disabled")
            self.text.see(tk.END)
        self.text.after(0, _append)
        
    def mainloop(self):
        """Run the Tkinter main loop."""
        self.root.mainloop()

class LogWindow:
    def __init__(self, root: tk.Misc):
        """Create a log window attached to an existing Tk root."""
        self.root = tk.Toplevel(root)

        self.root.title("GPT Logs")
        self.text = ScrolledText(self.root, state="disabled", width=60, height=20)
        self.text.pack(padx=5, pady=5)

    def append_log(self, msg: str):
        def _append():
            self.text.configure(state="normal")
            self.text.insert(tk.END, msg + "\n")
            self.text.configure(state="disabled")
            self.text.see(tk.END)
        self.text.after(0, _append)

