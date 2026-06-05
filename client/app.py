"""lab — app pra compartilhar projetos locais via túnel em *.devi.tools."""
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import sv_ttk

import config
import net


APP_TITLE = "lab"
PAD = 16
MUTED = "#9ca3af"
ACCENT = "#a78bfa"

STATES = {
    "off":          ("",                MUTED),
    "idle":         ("",                MUTED),
    "connecting":   ("Conectando…",     "#f59e0b"),
    "up":           ("No ar",           "#34d399"),
    "reconnecting": ("Reconectando…",   "#f97316"),
    "error":        ("Erro",            "#f87171"),
}


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("580x620")
        root.minsize(560, 600)

        sv_ttk.set_theme("dark")
        style = ttk.Style()
        style.configure("Brand.TLabel", foreground=ACCENT, font=("TkDefaultFont", 18, "bold"))
        style.configure("Tagline.TLabel", foreground=MUTED, font=("TkDefaultFont", 10))
        style.configure("SectionHint.TLabel", foreground=MUTED, font=("TkDefaultFont", 10))
        style.configure("Hint.TLabel", foreground=MUTED, font=("TkDefaultFont", 9))
        style.configure("Footer.TLabel", foreground=MUTED, font=("TkDefaultFont", 9))
        style.configure("Action.TButton", font=("TkDefaultFont", 11, "bold"))
        style.configure("Status.TLabel", font=("TkDefaultFont", 10))

        self.events: queue.Queue = queue.Queue()
        self.tunnel_thread: threading.Thread | None = None
        self.tunnel_client: net.TunnelClient | None = None
        self._lockable: list = []

        self.mode_var = tk.StringVar(value="folder")

        # ── Brand (top) ──────────────────────────────────────────────────
        brand_bar = ttk.Frame(root, padding=(PAD, PAD, PAD, 0))
        brand_bar.pack(side="top", fill="x")
        ttk.Label(brand_bar, text="</> lab", style="Brand.TLabel").pack(side="left")
        ttk.Label(
            brand_bar, text="compartilhe qualquer pasta ou porta local",
            style="Tagline.TLabel",
        ).pack(side="left", padx=(10, 0), pady=(8, 0))

        outer = ttk.Frame(root, padding=(PAD, 12, PAD, PAD))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        # ── Mode selector ────────────────────────────────────────────────
        ttk.Label(outer, text="O que você quer compartilhar?", style="SectionHint.TLabel").grid(row=0, column=0, sticky="w")
        radios = ttk.Frame(outer)
        radios.grid(row=1, column=0, sticky="w", pady=(4, 12))
        rb_folder = ttk.Radiobutton(
            radios, text="Uma pasta",
            variable=self.mode_var, value="folder",
            command=self._on_mode_change,
        )
        rb_folder.pack(side="left", padx=(0, 16))
        rb_port = ttk.Radiobutton(
            radios, text="Uma porta local",
            variable=self.mode_var, value="port",
            command=self._on_mode_change,
        )
        rb_port.pack(side="left")
        self._lockable.extend([rb_folder, rb_port])

        ttk.Separator(outer, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=(0, 12))

        # ── Body (swappable) ─────────────────────────────────────────────
        self.body = ttk.Frame(outer)
        self.body.grid(row=3, column=0, sticky="ew")
        self.body.columnconfigure(0, weight=1)

        self.folder_view = FolderView(self.body, self)
        self.port_view = PortView(self.body, self)

        # ── Friendly name (shared) ───────────────────────────────────────
        ttk.Label(outer, text="Nome amigável (opcional)").grid(row=4, column=0, sticky="w", pady=(12, 2))
        self.friendly_var = tk.StringVar()
        self.friendly_entry = ttk.Entry(outer, textvariable=self.friendly_var)
        self.friendly_entry.grid(row=5, column=0, sticky="ew")
        self._lockable.append(self.friendly_entry)

        self.result_sep = ttk.Separator(outer, orient="horizontal")
        self.result_sep.grid(row=6, column=0, sticky="ew", pady=14)

        # ── Result block (URL + status), hidden when idle ────────────────
        self.result_frame = ttk.Frame(outer)
        self.result_frame.grid(row=7, column=0, sticky="ew")
        self.result_frame.columnconfigure(0, weight=1)

        ttk.Label(self.result_frame, text="URL pública", style="SectionHint.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 2))

        self.url_var = tk.StringVar()
        url_row = ttk.Frame(self.result_frame)
        url_row.grid(row=1, column=0, sticky="ew")
        url_row.columnconfigure(0, weight=1)
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var, state="readonly")
        self.url_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(url_row, text="Copiar", command=self.copy_url, width=8).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(url_row, text="Abrir", command=self.open_url, width=8).grid(row=0, column=2, padx=(6, 0))

        status_row = ttk.Frame(self.result_frame)
        status_row.grid(row=2, column=0, sticky="ew", pady=(8, 12))
        status_row.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_row, text="", foreground=MUTED, style="Status.TLabel")
        self.status_label.grid(row=0, column=0, sticky="w")

        # ── Action button (bottom) ───────────────────────────────────────
        self.action_btn = ttk.Button(
            outer, text="Compartilhar", command=self.toggle,
            style="Accent.TButton",
        )
        self.action_btn.grid(row=8, column=0, sticky="ew", ipady=6)

        self.error_var = tk.StringVar()
        ttk.Label(
            outer, textvariable=self.error_var,
            foreground="#f87171", wraplength=480,
        ).grid(row=9, column=0, sticky="ew", pady=(8, 0))

        # Footer
        ttk.Label(
            root, text=f"servidor: {config.SERVER_HOST}",
            style="Footer.TLabel",
        ).pack(side="bottom", pady=(0, 8))

        self._on_mode_change()
        self._show_result(False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(80, self._drain_events)

    # ── Mode switching ───────────────────────────────────────────────────
    def _on_mode_change(self):
        if self.tunnel_client is not None:
            return
        mode = self.mode_var.get()
        if mode == "folder":
            self.port_view.frame.grid_remove()
            self.folder_view.frame.grid(row=0, column=0, sticky="ew")
        else:
            self.folder_view.frame.grid_remove()
            self.port_view.frame.grid(row=0, column=0, sticky="ew")
        self.url_var.set("")
        self.error_var.set("")
        self.set_state("idle")

    def _show_result(self, visible: bool):
        if visible:
            self.result_sep.grid()
            self.result_frame.grid()
        else:
            self.result_sep.grid_remove()
            self.result_frame.grid_remove()

    # ── Connect / disconnect ─────────────────────────────────────────────
    def toggle(self):
        if self.tunnel_client is None:
            self.connect()
        else:
            self.disconnect()

    def connect(self):
        mode = self.mode_var.get()
        index_file = "index.html"
        try:
            if mode == "folder":
                target = self.folder_view.path_var.get().strip()
                if not target:
                    messagebox.showerror(APP_TITLE, "Escolha a pasta primeiro.")
                    return
                index_file = self.folder_view.index_var.get().strip() or "index.html"
            else:
                target = int(self.port_view.port_var.get())
                if not 1 <= target <= 65535:
                    messagebox.showerror(APP_TITLE, "Porta fora do intervalo 1-65535.")
                    return
        except ValueError:
            messagebox.showerror(APP_TITLE, "Porta inválida.")
            return

        friendly = self.friendly_var.get().strip() or None
        self.url_var.set("")
        self.error_var.set("")
        self._show_result(True)
        self.set_state("connecting")
        self.action_btn.config(text="Parar")
        self._lock_inputs(True)

        def emit(kind, payload):
            self.events.put((kind, payload))

        try:
            self.tunnel_client = net.TunnelClient(
                mode, target, friendly, emit, index_file=index_file,
            )
        except ValueError as e:
            self.error_var.set(str(e))
            self.action_btn.config(text="Compartilhar")
            self._lock_inputs(False)
            self._show_result(False)
            return

        self.tunnel_thread = threading.Thread(target=self.tunnel_client.start, daemon=True)
        self.tunnel_thread.start()

    def disconnect(self):
        if self.tunnel_client:
            self.tunnel_client.stop()
        self.action_btn.config(text="Compartilhar")

    def _lock_inputs(self, locked: bool):
        state = "disabled" if locked else "normal"
        for w in self._lockable + self.folder_view.lockable() + self.port_view.lockable():
            try:
                w.config(state=state)
            except tk.TclError:
                pass

    # ── Status / URL helpers ─────────────────────────────────────────────
    def set_state(self, state: str, detail: str = ""):
        label, color = STATES.get(state, ("", MUTED))
        if detail:
            label = f"{label} ({detail})"
        text = f"●  {label}" if label else ""
        self.status_label.config(text=text, foreground=color)

    def copy_url(self):
        url = self.url_var.get()
        if not url:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(url)

    def open_url(self):
        url = self.url_var.get()
        if url:
            webbrowser.open(url)

    # ── Event pump ───────────────────────────────────────────────────────
    def _drain_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self.handle_event(kind, payload)
        except queue.Empty:
            pass
        self.root.after(80, self._drain_events)

    def handle_event(self, kind: str, payload: dict):
        if kind == "up":
            self.url_var.set(payload["url"])
            self.error_var.set("")
            self.set_state("up")
        elif kind == "status":
            state = payload.get("state", "off")
            detail = ""
            if state == "reconnecting":
                detail = f"em {payload.get('in_s', '?')}s"
            self.set_state(state, detail)
            if state == "off":
                self.tunnel_client = None
                self.tunnel_thread = None
                self.url_var.set("")
                self.action_btn.config(text="Compartilhar")
                self._lock_inputs(False)
                self._show_result(False)
        elif kind == "error":
            msg = payload.get("message", "")
            self.error_var.set(f"último erro: {msg}")
            self.set_state("error", msg[:40])

    def on_close(self):
        if self.tunnel_client:
            self.tunnel_client.stop()
        self.root.after(150, self.root.destroy)


class FolderView:
    def __init__(self, parent, app: App):
        self.app = app
        self.frame = ttk.Frame(parent)
        f = self.frame
        f.columnconfigure(0, weight=1)

        ttk.Label(f, text="Pasta do projeto").grid(row=0, column=0, sticky="w")
        self.path_var = tk.StringVar()
        path_row = ttk.Frame(f)
        path_row.grid(row=1, column=0, sticky="ew", pady=(2, 12))
        path_row.columnconfigure(0, weight=1)
        self.path_entry = ttk.Entry(path_row, textvariable=self.path_var)
        self.path_entry.grid(row=0, column=0, sticky="ew")
        self.pick_btn = ttk.Button(path_row, text="Escolher…", command=self.pick, width=10)
        self.pick_btn.grid(row=0, column=1, padx=(6, 0))

        ttk.Label(f, text="Página inicial").grid(row=2, column=0, sticky="w")
        self.index_var = tk.StringVar(value="index.html")
        self.index_entry = ttk.Entry(f, textvariable=self.index_var)
        self.index_entry.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        ttk.Label(
            f, text="Arquivo servido quando o amigo abre a URL na raiz (padrão: index.html)",
            style="Hint.TLabel",
        ).grid(row=4, column=0, sticky="w", pady=(2, 0))

    def pick(self):
        path = filedialog.askdirectory(title="Escolher pasta do projeto")
        if path:
            self.path_var.set(path)

    def lockable(self):
        return [self.path_entry, self.pick_btn, self.index_entry]


class PortView:
    def __init__(self, parent, app: App):
        self.app = app
        self.frame = ttk.Frame(parent)
        f = self.frame
        f.columnconfigure(0, weight=1)

        ttk.Label(f, text="Porta local").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar(value="5173")
        self.port_spin = ttk.Spinbox(
            f, from_=1024, to=65535, textvariable=self.port_var, width=12
        )
        self.port_spin.grid(row=1, column=0, sticky="w", pady=(2, 4))
        ttk.Label(
            f, text="Ex.: Vite 5173 · VSCode Live Server 5500 · WebStorm 63342",
            style="Hint.TLabel",
        ).grid(row=2, column=0, sticky="w")

    def lockable(self):
        return [self.port_spin]


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
