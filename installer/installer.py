"""Asistente gráfico de instalación de GymManager Lite.

Se compila con PyInstaller en un único `GymManagerLite-Setup.exe` que lleva
dentro el programa ya empaquetado (carpeta `payload`). El asistente:

  1. Da la bienvenida.
  2. Muestra el acuerdo de licencia y exige aceptarlo.
  3. Pregunta la carpeta de destino y comprueba el espacio libre.
  4. Ofrece los accesos directos y qué hacer con datos de una instalación previa.
  5. Copia los archivos mostrando cada uno en tiempo real con barra de progreso.
  6. Crea la base de datos limpia (solo el usuario administrador), los accesos
     directos, el desinstalador y la entrada de «Agregar o quitar programas».

No requiere permisos de administrador: instala en el perfil del usuario y solo
escribe en HKEY_CURRENT_USER.
"""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import traceback
import winreg
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

APP_NAME = "GymManager Lite"
APP_VERSION = "1.0.0"
PUBLISHER = "GymManager"
EXE_NAME = "GymManager Lite.exe"
UNINSTALLER_NAME = "Desinstalar GymManager Lite.exe"
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\GymManagerLite"
SHORTCUT_NAME = f"{APP_NAME}.lnk"
START_MENU_FOLDER = APP_NAME

ADMIN_USER = "Admin"
ADMIN_PASSWORD = "Admin.123"

# Paleta: la misma de la aplicación (slate + índigo).
INDIGO = "#4f46e5"
INDIGO_DARK = "#312e81"
SLATE_900 = "#0f172a"
SLATE_600 = "#475569"
SLATE_400 = "#94a3b8"
SLATE_200 = "#e2e8f0"
SLATE_50 = "#f8fafc"
GREEN = "#15803d"
RED = "#b91c1c"
WHITE = "#ffffff"

WINDOW_W, WINDOW_H = 700, 500


def resource(name: str) -> Path:
    """Ruta de un recurso empaquetado por PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def payload_dir() -> Path:
    return resource("payload")


def read_license() -> str:
    try:
        return resource("license.txt").read_text(encoding="utf-8")
    except OSError:
        return "No se pudo cargar el acuerdo de licencia."


def default_install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Programs" / APP_NAME


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


# --- Estado compartido entre páginas -----------------------------------------


@dataclass
class InstallOptions:
    target: Path = field(default_factory=default_install_dir)
    desktop_shortcut: bool = True
    start_menu_shortcut: bool = True
    launch_after: bool = True
    reset_existing_data: bool = True


# --- Trabajo de instalación (hilo aparte) ------------------------------------


class InstallWorker(threading.Thread):
    """Ejecuta la instalación y va publicando eventos en una cola.

    Eventos: ("file", ruta_relativa), ("progress", 0..100), ("step", texto),
    ("done", None) y ("error", mensaje).
    """

    def __init__(self, options: InstallOptions, events: "queue.Queue[tuple[str, object]]") -> None:
        super().__init__(daemon=True)
        self.options = options
        self.events = events

    # Cada fase ocupa un tramo de la barra: copiar 0-80, base de datos 80-90,
    # accesos directos y registro 90-100.
    def run(self) -> None:
        try:
            self._install()
            self.events.put(("done", None))
        except Exception as exc:  # noqa: BLE001 — el mensaje va a la interfaz
            self.events.put(("error", f"{exc}\n\n{traceback.format_exc()}"))

    # --- Fases ---------------------------------------------------------------

    def _install(self) -> None:
        target = self.options.target
        source = payload_dir()
        if not source.is_dir():
            raise RuntimeError(
                "El instalador está incompleto: no se encontró el contenido del programa."
            )

        self.events.put(("step", "Preparando la carpeta de destino…"))
        target.mkdir(parents=True, exist_ok=True)
        self._clean_previous(target)

        files = sorted(p for p in source.rglob("*") if p.is_file())
        total = sum(p.stat().st_size for p in files) or 1
        copied = 0

        self.events.put(("step", "Copiando archivos del programa…"))
        for item in files:
            relative = item.relative_to(source)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(item, destination)
            except PermissionError as exc:
                raise RuntimeError(
                    f"No se pudo escribir «{relative}».\n\n"
                    f"Si {APP_NAME} está abierto, ciérrelo y vuelva a ejecutar el "
                    "instalador. Si el problema continúa, elija otra carpeta de destino."
                ) from exc
            copied += item.stat().st_size
            self.events.put(("file", str(relative)))
            self.events.put(("progress", 80 * copied / total))

        self._write_database(target)
        self._write_shortcuts(target)
        self._register_uninstall(target, copied)
        self.events.put(("progress", 100))
        self.events.put(("step", "Instalación completada."))

    def _clean_previous(self, target: Path) -> None:
        """Quita los archivos de programa de una instalación anterior.

        La carpeta `data` se conserva o se borra según lo elegido en el asistente,
        nunca por accidente al sobrescribir.
        """
        data_dir = target / "data"
        if data_dir.exists() and self.options.reset_existing_data:
            self.events.put(("step", "Eliminando la base de datos anterior…"))
            shutil.rmtree(data_dir, ignore_errors=True)

        for item in target.iterdir():
            if item.name == "data":
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink()
            except OSError:
                # Un archivo bloqueado no debe abortar la instalación: se sobrescribe
                # después con copy2.
                pass

    def _write_database(self, target: Path) -> None:
        self.events.put(("step", "Creando la base de datos…"))
        self.events.put(("progress", 84))
        exe = target / EXE_NAME
        if not exe.exists():
            raise RuntimeError("No se copió el ejecutable principal del programa.")

        result = subprocess.run(
            [str(exe), "--init-db"],
            cwd=str(target),
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or b"").decode("utf-8", "replace").strip()
            raise RuntimeError(f"No se pudo crear la base de datos.\n{detail}")

        self.events.put(("file", "data\\gym.db"))
        self.events.put(("progress", 90))

    def _write_shortcuts(self, target: Path) -> None:
        self.events.put(("step", "Creando accesos directos…"))
        exe = target / EXE_NAME
        icon = target / EXE_NAME

        if self.options.desktop_shortcut:
            desktop = Path(os.path.expanduser("~")) / "Desktop"
            desktop = _known_folder("Desktop", desktop)
            self._make_shortcut(desktop / SHORTCUT_NAME, exe, target, icon)
            self.events.put(("file", f"Escritorio\\{SHORTCUT_NAME}"))

        if self.options.start_menu_shortcut:
            programs = _known_folder(
                "Programs",
                Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            )
            folder = programs / START_MENU_FOLDER
            folder.mkdir(parents=True, exist_ok=True)
            self._make_shortcut(folder / SHORTCUT_NAME, exe, target, icon)
            self._make_shortcut(
                folder / "Desinstalar.lnk", target / UNINSTALLER_NAME, target, target / UNINSTALLER_NAME
            )
            self.events.put(("file", f"Menú Inicio\\{START_MENU_FOLDER}"))

        self.events.put(("progress", 96))

    def _make_shortcut(self, link: Path, target_exe: Path, workdir: Path, icon: Path) -> None:
        """Crea un .lnk con WScript.Shell.

        Se hace con un VBScript temporal en vez de PowerShell porque `cscript` no
        depende de la política de ejecución del equipo.
        """
        script = (
            'Set s = CreateObject("WScript.Shell")\n'
            f'Set l = s.CreateShortcut("{link}")\n'
            f'l.TargetPath = "{target_exe}"\n'
            f'l.WorkingDirectory = "{workdir}"\n'
            f'l.IconLocation = "{icon},0"\n'
            f'l.Description = "{APP_NAME}"\n'
            "l.Save\n"
        )
        temp = Path(os.environ.get("TEMP", ".")) / f"gymlite_link_{os.getpid()}.vbs"
        try:
            temp.write_text(script, encoding="utf-8")
            subprocess.run(
                ["cscript", "//nologo", str(temp)],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            # Sin acceso directo la instalación sigue siendo válida.
            pass
        finally:
            temp.unlink(missing_ok=True)

    def _register_uninstall(self, target: Path, size_bytes: int) -> None:
        """Entrada en «Agregar o quitar programas» (solo para este usuario)."""
        self.events.put(("step", "Registrando el programa en Windows…"))
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
                values = {
                    "DisplayName": APP_NAME,
                    "DisplayVersion": APP_VERSION,
                    "Publisher": PUBLISHER,
                    "InstallLocation": str(target),
                    "DisplayIcon": str(target / EXE_NAME),
                    "UninstallString": f'"{target / UNINSTALLER_NAME}"',
                }
                for name, value in values.items():
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
                for name, value in (
                    ("NoModify", 1),
                    ("NoRepair", 1),
                    ("EstimatedSize", max(1, size_bytes // 1024)),
                ):
                    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
        except OSError:
            # No poder registrar no invalida la instalación; el desinstalador
            # sigue estando en la carpeta del programa.
            pass


def _known_folder(name: str, fallback: Path) -> Path:
    """Carpeta especial de Windows leída del registro (respeta OneDrive y rutas movidas)."""
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


# --- Interfaz ----------------------------------------------------------------


class Wizard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.options = InstallOptions()
        self.events: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.installing = False
        self.finished = False

        self.title(f"Instalación de {APP_NAME}")
        self.resizable(False, False)
        self.configure(bg=WHITE)
        try:
            self.iconbitmap(str(resource("gymlite.ico")))
        except tk.TclError:
            pass

        self._logo: tk.PhotoImage | None = None
        self._setup_style()
        self._build_layout()

        self.pages = [
            WelcomePage(self.body, self),
            LicensePage(self.body, self),
            LocationPage(self.body, self),
            OptionsPage(self.body, self),
            SummaryPage(self.body, self),
            ProgressPage(self.body, self),
            FinishPage(self.body, self),
        ]
        # Las dos últimas páginas se muestran fuera del orden normal (al pulsar
        # «Instalar» y al terminar), así que se localizan por clase y no por número.
        self.index_of = {type(page): i for i, page in enumerate(self.pages)}
        self.index = 0
        self._show(0)

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self._center()

    # --- Estructura ----------------------------------------------------------

    def _setup_style(self) -> None:
        base = tkfont.nametofont("TkDefaultFont").actual("family")
        family = "Segoe UI" if "Segoe UI" in tkfont.families() else base
        self.font_title = (family, 14, "bold")
        self.font_body = (family, 10)
        self.font_small = (family, 9)
        self.font_bold = (family, 10, "bold")
        self.font_mono = ("Consolas", 9)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=WHITE)
        style.configure("TLabel", background=WHITE, foreground=SLATE_900, font=self.font_body)
        style.configure("Title.TLabel", font=self.font_title, foreground=SLATE_900)
        style.configure("Muted.TLabel", foreground=SLATE_600, font=self.font_small)
        style.configure("TCheckbutton", background=WHITE, font=self.font_body)
        style.configure("TRadiobutton", background=WHITE, font=self.font_body)
        style.map("TCheckbutton", background=[("active", WHITE)])
        style.map("TRadiobutton", background=[("active", WHITE)])
        style.configure("TButton", font=self.font_body, padding=(14, 6))
        style.configure("TEntry", fieldbackground=WHITE)
        style.configure(
            "Gym.Horizontal.TProgressbar",
            troughcolor=SLATE_200,
            background=INDIGO,
            bordercolor=SLATE_200,
            lightcolor=INDIGO,
            darkcolor=INDIGO,
            thickness=18,
        )
        style.configure("Bar.TFrame", background=SLATE_50)

    def _build_layout(self) -> None:
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")

        container = tk.Frame(self, bg=WHITE)
        container.pack(fill="both", expand=True)

        self.banner = tk.Canvas(
            container, width=180, height=WINDOW_H - 60, highlightthickness=0, bd=0
        )
        self.banner.pack(side="left", fill="y")
        self._paint_banner()

        self.body = tk.Frame(container, bg=WHITE)
        self.body.pack(side="left", fill="both", expand=True)

        footer = tk.Frame(self, bg=SLATE_50, height=60)
        footer.pack(fill="x", side="bottom")
        tk.Frame(self, bg=SLATE_200, height=1).pack(fill="x", side="bottom")

        self.btn_cancel = ttk.Button(footer, text="Cancelar", command=self.on_cancel)
        self.btn_cancel.pack(side="right", padx=(0, 20), pady=14)
        self.btn_next = ttk.Button(footer, text="Siguiente", command=self.on_next)
        self.btn_next.pack(side="right", padx=(0, 8), pady=14)
        self.btn_back = ttk.Button(footer, text="Atrás", command=self.on_back)
        self.btn_back.pack(side="right", padx=(0, 8), pady=14)

    def _paint_banner(self) -> None:
        height = WINDOW_H - 60
        # Degradado vertical dibujado línea a línea: Tk no tiene degradados nativos.
        top = (0x4F, 0x46, 0xE5)
        bottom = (0x31, 0x2E, 0x81)
        for y in range(height):
            t = y / max(1, height - 1)
            colour = "#%02x%02x%02x" % tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
            self.banner.create_line(0, y, 180, y, fill=colour)

        try:
            self._logo = tk.PhotoImage(file=str(resource("gymlite-96.png")))
            self.banner.create_image(90, 120, image=self._logo)
        except tk.TclError:
            self._logo = None

        self.banner.create_text(
            90, 210, text=APP_NAME, fill=WHITE, font=("Segoe UI", 13, "bold"), justify="center"
        )
        self.banner.create_text(
            90, 232, text=f"Versión {APP_VERSION}", fill="#c7d2fe", font=("Segoe UI", 9)
        )
        self.banner.create_text(
            90,
            height - 24,
            text="Gestión de gimnasio",
            fill="#a5b4fc",
            font=("Segoe UI", 8),
        )

    def _center(self) -> None:
        self.update_idletasks()
        x = (self.winfo_screenwidth() - WINDOW_W) // 2
        y = (self.winfo_screenheight() - WINDOW_H) // 3
        self.geometry(f"{WINDOW_W}x{WINDOW_H}+{max(0, x)}+{max(0, y)}")

    # --- Navegación ----------------------------------------------------------

    def _show(self, index: int) -> None:
        for page in self.pages:
            page.pack_forget()
        self.index = index
        page = self.pages[index]
        page.pack(fill="both", expand=True)
        page.on_show()
        self.refresh_buttons()

    def refresh_buttons(self) -> None:
        page = self.pages[self.index]
        self.btn_back.configure(state="normal" if page.allow_back else "disabled")
        self.btn_next.configure(
            text=page.next_label, state="normal" if page.allow_next() else "disabled"
        )
        self.btn_cancel.configure(state="disabled" if self.finished else "normal")

    def on_next(self) -> None:
        page = self.pages[self.index]
        if not page.on_next():
            return
        if self.index + 1 < len(self.pages):
            self._show(self.index + 1)

    def on_back(self) -> None:
        if self.index > 0:
            self._show(self.index - 1)

    def on_cancel(self) -> None:
        if self.finished:
            self.destroy()
            return
        if self.installing:
            messagebox.showwarning(
                APP_NAME,
                "La instalación está en curso. Espere a que termine.",
                parent=self,
            )
            return
        if messagebox.askyesno(
            APP_NAME, "¿Seguro que desea cancelar la instalación?", parent=self, default="no"
        ):
            self.destroy()

    # --- Ejecución -----------------------------------------------------------

    def begin_installation(self) -> None:
        """Salta a la página de progreso y lanza el hilo que copia los archivos."""
        self._show(self.index_of[ProgressPage])
        self.installing = True
        self.btn_back.configure(state="disabled")
        self.btn_next.configure(state="disabled")
        InstallWorker(self.options, self.events).start()
        self.after(40, self._drain_events)

    def _drain_events(self) -> None:
        progress: ProgressPage = self.pages[self.index_of[ProgressPage]]  # type: ignore[assignment]
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "file":
                    progress.log_file(str(payload))
                elif kind == "progress":
                    progress.set_progress(float(payload))  # type: ignore[arg-type]
                elif kind == "step":
                    progress.set_step(str(payload))
                elif kind == "done":
                    self.installing = False
                    self._show(self.index_of[FinishPage])
                    return
                elif kind == "error":
                    self.installing = False
                    progress.set_step("La instalación falló.")
                    messagebox.showerror(
                        APP_NAME,
                        f"No se pudo completar la instalación.\n\n{payload}",
                        parent=self,
                    )
                    self.btn_cancel.configure(text="Cerrar", state="normal")
                    self.btn_back.configure(state="normal")
                    return
        except queue.Empty:
            pass
        self.after(40, self._drain_events)


# --- Páginas ------------------------------------------------------------------


class Page(tk.Frame):
    title_text = ""
    subtitle_text = ""
    next_label = "Siguiente"
    allow_back = True

    def __init__(self, master: tk.Misc, wizard: Wizard) -> None:
        super().__init__(master, bg=WHITE)
        self.wizard = wizard
        self.inner = tk.Frame(self, bg=WHITE)
        self.inner.pack(fill="both", expand=True, padx=28, pady=24)
        if self.title_text:
            ttk.Label(self.inner, text=self.title_text, style="Title.TLabel").pack(anchor="w")
        if self.subtitle_text:
            ttk.Label(
                self.inner, text=self.subtitle_text, style="Muted.TLabel", wraplength=440,
                justify="left",
            ).pack(anchor="w", pady=(4, 16))
        self.build()

    def build(self) -> None:
        """Contenido propio de la página."""

    def on_show(self) -> None:
        """Se ejecuta cada vez que la página se hace visible."""

    def allow_next(self) -> bool:
        return True

    def on_next(self) -> bool:
        """Devuelve False para quedarse en la página."""
        return True


class WelcomePage(Page):
    title_text = f"Bienvenido a la instalación de {APP_NAME}"
    allow_back = False

    def build(self) -> None:
        text = (
            f"Este asistente instalará {APP_NAME} {APP_VERSION} en su equipo.\n\n"
            "El programa gestiona clientes, inscripciones, inventario y ventas de un "
            "gimnasio. Funciona de forma local: no necesita internet ni servidores "
            "externos, y todos los datos se quedan en este equipo.\n\n"
            "La instalación crea una base de datos limpia con una única cuenta de "
            "administrador. No hace falta tener Python instalado ni permisos de "
            "administrador de Windows.\n\n"
            "Cierre el resto de aplicaciones antes de continuar y pulse «Siguiente»."
        )
        ttk.Label(self.inner, text=text, wraplength=440, justify="left").pack(
            anchor="w", pady=(14, 0)
        )


class LicensePage(Page):
    title_text = "Acuerdo de licencia"
    subtitle_text = "Lea con atención los términos antes de continuar con la instalación."

    def build(self) -> None:
        box = tk.Frame(self.inner, bg=SLATE_200, bd=0)
        box.pack(fill="both", expand=True)

        self.text = tk.Text(
            box,
            wrap="word",
            font=self.wizard.font_small,
            bg=SLATE_50,
            fg=SLATE_900,
            relief="flat",
            padx=12,
            pady=10,
            height=12,
        )
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", padx=(0, 1), pady=1)
        self.text.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)

        self.text.insert("1.0", read_license())
        self.text.configure(state="disabled")

        self.accepted = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.inner,
            text="Acepto los términos del acuerdo de licencia",
            variable=self.accepted,
            command=self.wizard.refresh_buttons,
        ).pack(anchor="w", pady=(14, 0))

    def allow_next(self) -> bool:
        return bool(self.accepted.get())


class LocationPage(Page):
    title_text = "Carpeta de destino"
    subtitle_text = "Elija dónde se instalará el programa. Puede escribir la ruta o buscarla."

    def build(self) -> None:
        self.path_var = tk.StringVar(value=str(self.wizard.options.target))
        self.path_var.trace_add("write", lambda *_: self._update_space())

        row = tk.Frame(self.inner, bg=WHITE)
        row.pack(fill="x", pady=(6, 0))
        entry = ttk.Entry(row, textvariable=self.path_var, font=self.wizard.font_body)
        entry.pack(side="left", fill="x", expand=True, ipady=4)
        ttk.Button(row, text="Examinar…", command=self._browse).pack(side="left", padx=(8, 0))

        self.space_label = ttk.Label(self.inner, text="", style="Muted.TLabel", justify="left")
        self.space_label.pack(anchor="w", pady=(14, 0))

        self.warning = ttk.Label(
            self.inner, text="", style="Muted.TLabel", foreground=RED, wraplength=440,
            justify="left",
        )
        self.warning.pack(anchor="w", pady=(10, 0))

        ttk.Label(
            self.inner,
            text=(
                "Los datos del programa (base de datos y fotos) se guardarán en la "
                "subcarpeta «data» de esta ruta."
            ),
            style="Muted.TLabel",
            wraplength=440,
            justify="left",
        ).pack(anchor="w", side="bottom")

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(
            parent=self.wizard, title="Seleccione la carpeta de instalación", mustexist=False
        )
        if not chosen:
            return
        path = Path(chosen)
        # Si eligen una carpeta contenedora, se crea dentro una con el nombre del
        # programa, para no desparramar archivos en, por ejemplo, el escritorio.
        if path.name.lower() != APP_NAME.lower():
            path = path / APP_NAME
        self.path_var.set(str(path))

    def on_show(self) -> None:
        self._update_space()

    def _payload_size(self) -> int:
        source = payload_dir()
        if not source.is_dir():
            return 0
        return sum(p.stat().st_size for p in source.rglob("*") if p.is_file())

    def _update_space(self) -> None:
        raw = self.path_var.get().strip()
        needed = self._payload_size()
        text = f"Espacio necesario:  {human_size(needed)}"

        free: int | None = None
        try:
            anchor = Path(raw or ".")
            while not anchor.exists() and anchor.parent != anchor:
                anchor = anchor.parent
            free = shutil.disk_usage(str(anchor)).free
            text += f"\nEspacio disponible: {human_size(free)}"
        except (OSError, ValueError):
            text += "\nEspacio disponible: no se pudo calcular"
        self.space_label.configure(text=text)

        error = self._validate(raw, needed, free)
        if error:
            self.warning.configure(text=error, foreground=RED)
        elif raw and (Path(raw) / EXE_NAME).exists():
            self.warning.configure(
                text="Ya hay una instalación en esta carpeta: se reemplazará.", foreground="#b45309"
            )
        else:
            self.warning.configure(text="")

        self._valid = error is None
        self.wizard.refresh_buttons()

    def _validate(self, raw: str, needed: int, free: int | None) -> str | None:
        """Devuelve el motivo por el que la ruta no sirve, o None si es válida."""
        if not raw:
            return "Indique una carpeta de destino."
        try:
            target = Path(raw)
        except ValueError:
            return "La ruta indicada no es válida."
        if not target.is_absolute():
            return "Escriba una ruta completa, por ejemplo C:\\Programas\\GymManager Lite."
        if target.exists() and not target.is_dir():
            return "Ya existe un archivo con ese nombre. Elija otra carpeta."
        # Margen: los archivos copiados más la base de datos y las fotos futuras.
        if free is not None and free < needed * 1.5:
            return "No hay espacio suficiente en la unidad seleccionada."
        return None

    def allow_next(self) -> bool:
        return getattr(self, "_valid", False)

    def on_next(self) -> bool:
        self.wizard.options.target = Path(self.path_var.get()).expanduser()
        return True


class OptionsPage(Page):
    title_text = "Opciones de instalación"
    subtitle_text = "Seleccione los accesos directos que desea crear."

    def build(self) -> None:
        self.desktop = tk.BooleanVar(value=True)
        self.start_menu = tk.BooleanVar(value=True)
        self.launch = tk.BooleanVar(value=True)
        self.reset_data = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            self.inner, text="Crear un acceso directo en el escritorio", variable=self.desktop
        ).pack(anchor="w", pady=3)
        ttk.Checkbutton(
            self.inner, text="Crear un acceso directo en el menú Inicio", variable=self.start_menu
        ).pack(anchor="w", pady=3)
        ttk.Checkbutton(
            self.inner, text=f"Abrir {APP_NAME} al terminar la instalación", variable=self.launch
        ).pack(anchor="w", pady=3)

        # Solo aparece si la carpeta de destino ya tiene datos de una instalación
        # anterior: es la única situación en la que hay algo que perder.
        self.data_box = tk.LabelFrame(
            self.inner,
            text=" Datos de una instalación anterior ",
            bg=WHITE,
            fg=SLATE_900,
            font=self.wizard.font_bold,
            bd=1,
            relief="solid",
            padx=12,
            pady=10,
        )
        ttk.Label(
            self.data_box,
            text=(
                "La carpeta elegida ya contiene una base de datos con clientes, "
                "inscripciones y ventas."
            ),
            wraplength=400,
            justify="left",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        ttk.Radiobutton(
            self.data_box,
            text="Empezar con una base de datos limpia (se borran los datos actuales)",
            variable=self.reset_data,
            value=True,
        ).pack(anchor="w")
        ttk.Radiobutton(
            self.data_box,
            text="Conservar los datos existentes",
            variable=self.reset_data,
            value=False,
        ).pack(anchor="w", pady=(2, 0))

    def on_show(self) -> None:
        has_data = (self.wizard.options.target / "data" / "gym.db").exists()
        if has_data:
            self.data_box.pack(anchor="w", fill="x", pady=(20, 0))
        else:
            self.data_box.pack_forget()

    def on_next(self) -> bool:
        options = self.wizard.options
        options.desktop_shortcut = bool(self.desktop.get())
        options.start_menu_shortcut = bool(self.start_menu.get())
        options.launch_after = bool(self.launch.get())
        options.reset_existing_data = bool(self.reset_data.get())
        return True


class SummaryPage(Page):
    title_text = "Todo listo para instalar"
    subtitle_text = "Revise las opciones. Pulse «Instalar» para comenzar la copia de archivos."
    next_label = "Instalar"

    def build(self) -> None:
        self.summary = tk.Text(
            self.inner,
            wrap="word",
            font=self.wizard.font_small,
            bg=SLATE_50,
            fg=SLATE_900,
            relief="solid",
            bd=1,
            padx=12,
            pady=10,
            height=11,
        )
        self.summary.pack(fill="both", expand=True)

    def on_show(self) -> None:
        options = self.wizard.options
        lines = [
            "Carpeta de destino:",
            f"   {options.target}",
            "",
            "Carpeta de datos:",
            f"   {options.target / 'data'}",
            "",
            "Accesos directos:",
            f"   Escritorio:   {'sí' if options.desktop_shortcut else 'no'}",
            f"   Menú Inicio:  {'sí' if options.start_menu_shortcut else 'no'}",
            "",
            "Base de datos:",
            "   Limpia, con un único usuario administrador.",
        ]
        if (options.target / "data" / "gym.db").exists() and not options.reset_existing_data:
            lines[-1] = "   Se conservarán los datos de la instalación anterior."

        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", "\n".join(lines))
        self.summary.configure(state="disabled")

    def on_next(self) -> bool:
        self.wizard.begin_installation()
        return False  # la navegación pasa a manos de la instalación


class ProgressPage(Page):
    title_text = "Instalando"
    subtitle_text = "Espere mientras se copian los archivos del programa."
    allow_back = False

    def build(self) -> None:
        self.step_var = tk.StringVar(value="Preparando…")
        self.percent_var = tk.StringVar(value="0 %")
        self.file_var = tk.StringVar(value="")

        ttk.Label(self.inner, textvariable=self.step_var, font=self.wizard.font_bold).pack(anchor="w")

        self.bar = ttk.Progressbar(
            self.inner, style="Gym.Horizontal.TProgressbar", maximum=100, mode="determinate"
        )
        self.bar.pack(fill="x", pady=(10, 4))

        row = tk.Frame(self.inner, bg=WHITE)
        row.pack(fill="x")
        ttk.Label(row, textvariable=self.file_var, style="Muted.TLabel").pack(side="left")
        ttk.Label(row, textvariable=self.percent_var, style="Muted.TLabel").pack(side="right")

        holder = tk.Frame(self.inner, bg=SLATE_200)
        holder.pack(fill="both", expand=True, pady=(16, 0))
        self.log = tk.Text(
            holder,
            wrap="none",
            font=self.wizard.font_mono,
            bg=SLATE_900,
            fg="#cbd5e1",
            relief="flat",
            padx=10,
            pady=8,
            height=9,
            state="disabled",
        )
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", padx=(0, 1), pady=1)
        self.log.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)

    def set_step(self, text: str) -> None:
        self.step_var.set(text)

    def set_progress(self, value: float) -> None:
        self.bar["value"] = value
        self.percent_var.set(f"{value:.0f} %")

    def log_file(self, relative: str) -> None:
        # Se recorta por la izquierda: el final de la ruta es lo que identifica el archivo.
        shown = relative if len(relative) <= 52 else f"…{relative[-51:]}"
        self.file_var.set(f"Instalando: {shown}")
        self.log.configure(state="normal")
        self.log.insert("end", f"  {relative}\n")
        self.log.see("end")
        self.log.configure(state="disabled")


class FinishPage(Page):
    title_text = "Instalación completada"
    next_label = "Finalizar"
    allow_back = False

    def build(self) -> None:
        ttk.Label(
            self.inner,
            text=f"{APP_NAME} se instaló correctamente en este equipo.",
            foreground=GREEN,
            font=self.wizard.font_bold,
        ).pack(anchor="w", pady=(10, 16))

        creds = tk.LabelFrame(
            self.inner,
            text=" Datos de acceso ",
            bg=WHITE,
            fg=SLATE_900,
            font=self.wizard.font_bold,
            bd=1,
            relief="solid",
            padx=14,
            pady=10,
        )
        creds.pack(fill="x")
        for row, (label, value) in enumerate(
            (("Usuario:", ADMIN_USER), ("Contraseña:", ADMIN_PASSWORD))
        ):
            ttk.Label(creds, text=label, font=self.wizard.font_body).grid(row=row, column=0, sticky="w")
            ttk.Label(creds, text=value, font=("Consolas", 10, "bold")).grid(
                row=row, column=1, sticky="w", padx=(12, 0)
            )
        ttk.Label(
            creds,
            text="Cambie esta contraseña la primera vez que entre, desde «Mi cuenta».",
            style="Muted.TLabel",
            foreground=RED,
            wraplength=380,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.location = ttk.Label(self.inner, text="", style="Muted.TLabel", wraplength=440, justify="left")
        self.location.pack(anchor="w", pady=(16, 0))

    def on_show(self) -> None:
        self.wizard.finished = True
        options = self.wizard.options
        self.location.configure(
            text=(
                f"Instalado en:\n{options.target}\n\n"
                "Para desinstalarlo, use «Agregar o quitar programas» de Windows o el "
                "acceso «Desinstalar» dentro de la carpeta del programa."
            )
        )

    def on_next(self) -> bool:
        options = self.wizard.options
        if options.launch_after:
            exe = options.target / EXE_NAME
            if exe.exists():
                try:
                    subprocess.Popen([str(exe)], cwd=str(options.target))
                except OSError:
                    pass
        self.wizard.destroy()
        return False


def main() -> int:
    if os.name != "nt":
        print("Este instalador solo funciona en Windows.", file=sys.stderr)
        return 1
    Wizard().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
