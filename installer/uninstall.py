"""Desinstalador gráfico de GymManager Lite.

Se compila junto al programa y se copia en la carpeta de instalación, de donde
deduce qué tiene que borrar. Los datos del gimnasio se conservan salvo que se
marque explícitamente la casilla correspondiente.
"""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import font as tkfont, messagebox, ttk

APP_NAME = "GymManager Lite"
EXE_NAME = "GymManager Lite.exe"
UNINSTALLER_NAME = "Desinstalar GymManager Lite.exe"
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\GymManagerLite"
SHORTCUT_NAME = f"{APP_NAME}.lnk"
START_MENU_FOLDER = APP_NAME

INDIGO = "#4f46e5"
SLATE_900 = "#0f172a"
SLATE_600 = "#475569"
SLATE_200 = "#e2e8f0"
SLATE_50 = "#f8fafc"
RED = "#b91c1c"
GREEN = "#15803d"
WHITE = "#ffffff"


def resource(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _known_folder(name: str, fallback: Path) -> Path:
    key_name = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name) as key:
            value, _ = winreg.QueryValueEx(key, name)
            expanded = Path(os.path.expandvars(value))
            if expanded.is_dir():
                return expanded
    except OSError:
        pass
    return fallback


class UninstallWorker(threading.Thread):
    def __init__(
        self, target: Path, remove_data: bool, events: "queue.Queue[tuple[str, object]]"
    ) -> None:
        super().__init__(daemon=True)
        self.target = target
        self.remove_data = remove_data
        self.events = events

    def run(self) -> None:
        try:
            self._remove_shortcuts()
            self._remove_registry()
            self._remove_files()
            self.events.put(("done", None))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("error", str(exc)))

    def _remove_shortcuts(self) -> None:
        self.events.put(("step", "Quitando accesos directos…"))
        desktop = _known_folder("Desktop", Path.home() / "Desktop")
        link = desktop / SHORTCUT_NAME
        if link.exists():
            link.unlink(missing_ok=True)
            self.events.put(("log", f"Escritorio\\{SHORTCUT_NAME}"))

        programs = _known_folder(
            "Programs", Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
        )
        folder = programs / START_MENU_FOLDER
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
            self.events.put(("log", f"Menú Inicio\\{START_MENU_FOLDER}"))
        self.events.put(("progress", 25))

    def _remove_registry(self) -> None:
        self.events.put(("step", "Quitando el registro de Windows…"))
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
            self.events.put(("log", "Entrada de «Agregar o quitar programas»"))
        except OSError:
            pass
        self.events.put(("progress", 40))

    def _remove_files(self) -> None:
        self.events.put(("step", "Eliminando los archivos del programa…"))
        me = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None

        entries = [p for p in self.target.iterdir()]
        keep_data = not self.remove_data
        total = max(1, len(entries))

        for index, item in enumerate(entries, start=1):
            if keep_data and item.name == "data":
                self.events.put(("log", "data (conservada)"))
                continue
            if me is not None and item.resolve() == me:
                continue  # el propio desinstalador se borra al final
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
                self.events.put(("log", item.name))
            except OSError:
                self.events.put(("log", f"{item.name} (no se pudo eliminar)"))
            self.events.put(("progress", 40 + 55 * index / total))

        self.events.put(("progress", 100))
        self.events.put(("step", "Desinstalación completada."))


def _schedule_self_removal(target: Path, remove_folder: bool) -> None:
    """Borra el desinstalador (y la carpeta, si quedó vacía) tras cerrarse.

    Un ejecutable en uso no se puede borrar a sí mismo, así que se deja un
    comando que espera unos segundos y lo hace después.
    """
    uninstaller = target / UNINSTALLER_NAME
    parts = [f'del /f /q "{uninstaller}"']
    if remove_folder:
        parts.append(f'rmdir /s /q "{target}"')
    command = "ping 127.0.0.1 -n 4 >nul & " + " & ".join(parts)
    try:
        subprocess.Popen(
            ["cmd", "/c", command],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    except OSError:
        pass


class UninstallWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.target = install_dir()
        self.events: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.done = False

        self.title(f"Desinstalar {APP_NAME}")
        self.resizable(False, False)
        self.configure(bg=WHITE)
        try:
            self.iconbitmap(str(resource("gymlite.ico")))
        except tk.TclError:
            pass

        self._style()
        self._build()
        self._center()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _style(self) -> None:
        base = tkfont.nametofont("TkDefaultFont").actual("family")
        family = "Segoe UI" if "Segoe UI" in tkfont.families() else base
        self.font_body = (family, 10)
        self.font_bold = (family, 10, "bold")
        self.font_small = (family, 9)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=WHITE)
        style.configure("TLabel", background=WHITE, foreground=SLATE_900, font=self.font_body)
        style.configure("Muted.TLabel", foreground=SLATE_600, font=self.font_small)
        style.configure("TCheckbutton", background=WHITE, font=self.font_body)
        style.map("TCheckbutton", background=[("active", WHITE)])
        style.configure("TButton", font=self.font_body, padding=(14, 6))
        style.configure(
            "Gym.Horizontal.TProgressbar",
            troughcolor=SLATE_200,
            background=INDIGO,
            bordercolor=SLATE_200,
            lightcolor=INDIGO,
            darkcolor=INDIGO,
            thickness=16,
        )

    def _build(self) -> None:
        frame = tk.Frame(self, bg=WHITE, padx=26, pady=22)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=f"Desinstalar {APP_NAME}", font=(self.font_bold[0], 14, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            frame,
            text=f"Se eliminarán los archivos del programa de:\n{self.target}",
            style="Muted.TLabel",
            justify="left",
            wraplength=430,
        ).pack(anchor="w", pady=(6, 16))

        self.remove_data = tk.BooleanVar(value=False)
        self.data_check = ttk.Checkbutton(
            frame,
            text="Eliminar también los datos (clientes, inscripciones, ventas y fotos)",
            variable=self.remove_data,
        )
        self.data_check.pack(anchor="w")
        ttk.Label(
            frame,
            text="Si no la marca, la carpeta «data» se conserva y podrá reutilizarla más adelante.",
            style="Muted.TLabel",
            wraplength=430,
            justify="left",
        ).pack(anchor="w", pady=(2, 16))

        self.step_var = tk.StringVar(value="")
        self.step_label = ttk.Label(frame, textvariable=self.step_var, font=self.font_bold)
        self.bar = ttk.Progressbar(
            frame, style="Gym.Horizontal.TProgressbar", maximum=100, mode="determinate", length=430
        )

        holder = tk.Frame(frame, bg=SLATE_200)
        self.log = tk.Text(
            holder,
            wrap="none",
            font=("Consolas", 9),
            bg=SLATE_900,
            fg="#cbd5e1",
            relief="flat",
            padx=10,
            pady=8,
            height=7,
            width=52,
            state="disabled",
        )
        self.log.pack(padx=1, pady=1)
        self.progress_widgets = (self.step_label, self.bar, holder)

        buttons = tk.Frame(frame, bg=WHITE)
        buttons.pack(fill="x", side="bottom", pady=(18, 0))
        self.btn_cancel = ttk.Button(buttons, text="Cancelar", command=self._on_close)
        self.btn_cancel.pack(side="right")
        self.btn_go = ttk.Button(buttons, text="Desinstalar", command=self._start)
        self.btn_go.pack(side="right", padx=(0, 8))

    def _center(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _on_close(self) -> None:
        if self.done:
            self.destroy()
            return
        if self.btn_go["state"] == "disabled":
            return  # desinstalación en curso
        self.destroy()

    def _start(self) -> None:
        if self.remove_data.get() and not messagebox.askyesno(
            APP_NAME,
            "Se borrarán TODOS los datos del gimnasio: clientes, inscripciones, "
            "ventas y fotos.\n\nEsta acción no se puede deshacer. ¿Continuar?",
            parent=self,
            default="no",
            icon="warning",
        ):
            return

        self.btn_go.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")
        self.data_check.configure(state="disabled")
        for widget in self.progress_widgets:
            widget.pack(anchor="w", fill="x", pady=(0, 8))

        UninstallWorker(self.target, bool(self.remove_data.get()), self.events).start()
        self.after(40, self._drain)

    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "step":
                    self.step_var.set(str(payload))
                elif kind == "progress":
                    self.bar["value"] = float(payload)  # type: ignore[arg-type]
                elif kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", f"  {payload}\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "done":
                    self._finish()
                    return
                elif kind == "error":
                    messagebox.showerror(APP_NAME, str(payload), parent=self)
                    self.btn_cancel.configure(state="normal", text="Cerrar")
                    return
        except queue.Empty:
            pass
        self.after(40, self._drain)

    def _finish(self) -> None:
        self.done = True
        self.step_var.set("Desinstalación completada.")
        self.step_label.configure(foreground=GREEN)
        self.btn_cancel.configure(state="normal", text="Cerrar", command=self._close_and_clean)
        self.btn_go.pack_forget()

    def _close_and_clean(self) -> None:
        _schedule_self_removal(self.target, remove_folder=bool(self.remove_data.get()))
        self.destroy()


def main() -> int:
    if os.name != "nt":
        print("Este desinstalador solo funciona en Windows.", file=sys.stderr)
        return 1

    target = install_dir()
    if not (target / EXE_NAME).exists():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            APP_NAME,
            f"No se encontró {APP_NAME} en:\n{target}\n\n"
            "Ejecute el desinstalador desde la carpeta donde está instalado el programa.",
        )
        return 1

    UninstallWindow().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
