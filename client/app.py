"""lab — app pra publicar projetos locais em *.devi.tools."""
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import config
import net


APP_TITLE = "lab"
PAD = 12


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("560x440")
        root.minsize(560, 440)

        self.events: queue.Queue = queue.Queue()
        self.tunnel_thread: threading.Thread | None = None
        self.tunnel_client: net.TunnelClient | None = None

        style = ttk.Style()
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
        elif "vista" in style.theme_names():
            style.theme_use("vista")

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        self.publish_tab = PublishTab(nb, self)
        self.tunnel_tab = TunnelTab(nb, self)
        nb.add(self.publish_tab.frame, text="Publicar pasta")
        nb.add(self.tunnel_tab.frame, text="Conectar porta")

        footer = ttk.Label(
            root,
            text=f"servidor: {config.SERVER_HOST}",
            foreground="#888",
        )
        footer.pack(side="bottom", pady=(0, 6))

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(80, self._drain_events)

    def _drain_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self.tunnel_tab.handle_event(kind, payload)
        except queue.Empty:
            pass
        self.root.after(80, self._drain_events)

    def on_close(self):
        if self.tunnel_client:
            self.tunnel_client.stop()
        self.root.after(150, self.root.destroy)


class PublishTab:
    def __init__(self, parent, app: App):
        self.app = app
        self.frame = ttk.Frame(parent, padding=PAD)
        f = self.frame

        ttk.Label(f, text="Pasta do build (ex: dist/)").grid(row=0, column=0, sticky="w")
        self.path_var = tk.StringVar()
        path_row = ttk.Frame(f)
        path_row.grid(row=1, column=0, sticky="ew", pady=(2, 10))
        path_row.columnconfigure(0, weight=1)
        ttk.Entry(path_row, textvariable=self.path_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(path_row, text="Escolher…", command=self.pick).grid(row=0, column=1, padx=(6, 0))

        ttk.Label(f, text="Nome amigável (opcional)").grid(row=2, column=0, sticky="w")
        self.friendly_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.friendly_var).grid(row=3, column=0, sticky="ew", pady=(2, 10))

        self.publish_btn = ttk.Button(f, text="Publicar", command=self.publish)
        self.publish_btn.grid(row=4, column=0, sticky="ew", pady=(4, 10))

        self.progress = ttk.Progressbar(f, mode="indeterminate")
        self.progress.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        self.progress.grid_remove()

        ttk.Separator(f, orient="horizontal").grid(row=6, column=0, sticky="ew", pady=8)

        ttk.Label(f, text="URL publicada").grid(row=7, column=0, sticky="w")
        self.url_var = tk.StringVar()
        url_row = ttk.Frame(f)
        url_row.grid(row=8, column=0, sticky="ew", pady=(2, 0))
        url_row.columnconfigure(0, weight=1)
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var, state="readonly")
        self.url_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(url_row, text="Copiar", command=self.copy_url).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(url_row, text="Abrir", command=self.open_url).grid(row=0, column=2, padx=(6, 0))

        f.columnconfigure(0, weight=1)

    def pick(self):
        path = filedialog.askdirectory(title="Escolher pasta do build")
        if path:
            self.path_var.set(path)

    def publish(self):
        path = self.path_var.get().strip()
        friendly = self.friendly_var.get().strip() or None
        if not path:
            messagebox.showerror(APP_TITLE, "Escolha a pasta do build primeiro.")
            return
        self.publish_btn.state(["disabled"])
        self.progress.grid()
        self.progress.start(12)
        self.url_var.set("")
        threading.Thread(target=self._do_publish, args=(path, friendly), daemon=True).start()

    def _do_publish(self, path, friendly):
        try:
            result = net.publish_folder(path, friendly)
            self.app.root.after(0, self._on_publish_ok, result)
        except Exception as e:
            self.app.root.after(0, self._on_publish_err, e)

    def _on_publish_ok(self, result):
        self.progress.stop()
        self.progress.grid_remove()
        self.publish_btn.state(["!disabled"])
        self.url_var.set(result["url"])

    def _on_publish_err(self, err):
        self.progress.stop()
        self.progress.grid_remove()
        self.publish_btn.state(["!disabled"])
        messagebox.showerror(APP_TITLE, f"Falha ao publicar:\n{err}")

    def copy_url(self):
        url = self.url_var.get()
        if not url:
            return
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(url)

    def open_url(self):
        url = self.url_var.get()
        if url:
            webbrowser.open(url)


class TunnelTab:
    STATES = {
        "off":          ("Desconectado", "#aaa"),
        "connecting":   ("Conectando…",  "#e8a500"),
        "up":           ("No ar",        "#1aa051"),
        "reconnecting": ("Reconectando…", "#d97506"),
        "error":        ("Erro",         "#cc3333"),
    }

    def __init__(self, parent, app: App):
        self.app = app
        self.frame = ttk.Frame(parent, padding=PAD)
        f = self.frame

        ttk.Label(f, text="Porta local (ex: 5173 ou 65432)").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar(value="5173")
        ttk.Spinbox(
            f, from_=1024, to=65535, textvariable=self.port_var, width=10
        ).grid(row=1, column=0, sticky="w", pady=(2, 10))

        ttk.Label(f, text="Nome amigável (opcional)").grid(row=2, column=0, sticky="w")
        self.friendly_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.friendly_var).grid(row=3, column=0, sticky="ew", pady=(2, 10))

        action_row = ttk.Frame(f)
        action_row.grid(row=4, column=0, sticky="ew", pady=(4, 10))
        self.action_btn = ttk.Button(action_row, text="Conectar", command=self.toggle)
        self.action_btn.pack(side="left")

        status_row = ttk.Frame(action_row)
        status_row.pack(side="right")
        self.status_dot = tk.Canvas(status_row, width=14, height=14, highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_label = ttk.Label(status_row, text="Desconectado")
        self.status_label.pack(side="left")
        self._draw_dot("#aaa")

        ttk.Separator(f, orient="horizontal").grid(row=5, column=0, sticky="ew", pady=8)

        ttk.Label(f, text="URL ativa").grid(row=6, column=0, sticky="w")
        self.url_var = tk.StringVar()
        url_row = ttk.Frame(f)
        url_row.grid(row=7, column=0, sticky="ew", pady=(2, 0))
        url_row.columnconfigure(0, weight=1)
        ttk.Entry(url_row, textvariable=self.url_var, state="readonly").grid(row=0, column=0, sticky="ew")
        ttk.Button(url_row, text="Copiar", command=self.copy_url).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(url_row, text="Abrir", command=self.open_url).grid(row=0, column=2, padx=(6, 0))

        self.error_var = tk.StringVar()
        self.error_label = ttk.Label(f, textvariable=self.error_var, foreground="#cc3333", wraplength=480)
        self.error_label.grid(row=9, column=0, sticky="ew", pady=(10, 0))

        f.columnconfigure(0, weight=1)

    def _draw_dot(self, color: str):
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 12, 12, fill=color, outline="")

    def _set_state(self, state: str, detail: str = ""):
        label, color = self.STATES[state]
        if detail:
            label = f"{label} ({detail})"
        self.status_label.config(text=label)
        self._draw_dot(color)

    def toggle(self):
        if self.app.tunnel_client is None:
            self.connect()
        else:
            self.disconnect()

    def connect(self):
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror(APP_TITLE, "Porta inválida.")
            return
        if not 1 <= port <= 65535:
            messagebox.showerror(APP_TITLE, "Porta fora do intervalo 1-65535.")
            return

        friendly = self.friendly_var.get().strip() or None
        self.url_var.set("")
        self._set_state("connecting")
        self.action_btn.config(text="Desconectar")

        def emit(kind, payload):
            self.app.events.put((kind, payload))

        self.app.tunnel_client = net.TunnelClient(port, friendly, emit)
        self.app.tunnel_thread = threading.Thread(
            target=self.app.tunnel_client.start, daemon=True
        )
        self.app.tunnel_thread.start()

    def disconnect(self):
        if self.app.tunnel_client:
            self.app.tunnel_client.stop()
        self.action_btn.config(text="Conectar")

    def handle_event(self, kind: str, payload: dict):
        if kind == "up":
            self.url_var.set(payload["url"])
            self.error_var.set("")
            self._set_state("up")
        elif kind == "status":
            state = payload.get("state", "off")
            detail = ""
            if state == "reconnecting":
                detail = f"em {payload.get('in_s', '?')}s"
            self._set_state(state, detail)
            if state == "off":
                self.app.tunnel_client = None
                self.app.tunnel_thread = None
                self.url_var.set("")
                self.error_var.set("")
                self.action_btn.config(text="Conectar")
        elif kind == "error":
            msg = payload.get("message", "")
            self.error_var.set(f"último erro: {msg}")
            self._set_state("error", msg[:40])

    def copy_url(self):
        url = self.url_var.get()
        if url:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(url)

    def open_url(self):
        url = self.url_var.get()
        if url:
            webbrowser.open(url)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
