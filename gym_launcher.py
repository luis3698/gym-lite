"""Punto de entrada de la versión instalada de GymManager Lite.

A diferencia de `run.py` (pensado para desarrollo, con consola), aquí el servidor
vive dentro de una pequeña ventana de control: se ve el estado, se abre el
navegador con un botón y se detiene cerrando la ventana. Así el usuario final no
tiene que convivir con una consola negra que no debe cerrar.

Opciones:
    --init-db       crea la base de datos limpia y termina (lo usa el instalador)
    --no-browser    abre la ventana de control sin lanzar el navegador
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

APP_NAME = "GymManager Lite"
FIRST_PORT = 5000
LAST_PORT = 5010
HOST = "127.0.0.1"


def _resource(name: str) -> Path:
    """Ruta de un recurso empaquetado (funciona congelado y desde el código)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


class _NullStream:
    """Sustituto de stdout/stderr en modo ventana, donde valen None."""

    def write(self, _data: str) -> int:
        return 0

    def flush(self) -> None:
        pass


def _prepare_streams() -> None:
    """Evita que un print() rompa la aplicación al compilarla sin consola."""
    if sys.stdout is None:
        sys.stdout = _NullStream()  # type: ignore[assignment]
    if sys.stderr is None:
        sys.stderr = _NullStream()  # type: ignore[assignment]


def _free_port() -> int | None:
    for port in range(FIRST_PORT, LAST_PORT + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((HOST, port))
            except OSError:
                continue
        return port
    return None


def _log_crash(exc: BaseException) -> Path | None:
    """Deja el detalle del fallo en un archivo junto a los datos."""
    try:
        from app.config import INSTANCE_DIR

        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        path = INSTANCE_DIR / "error.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write("".join(traceback.format_exception(exc)) + "\n")
        return path
    except Exception:  # el registro nunca debe tapar el error original
        return None


# --- Modo consola: preparar la base de datos ---------------------------------


def init_database() -> int:
    """Crea el esquema y el usuario administrador. Lo usa el instalador."""
    from app import create_app

    app = create_app()
    print(f"Base de datos lista: {app.config['DATABASE']}")
    return 0


# --- Modo ventana ------------------------------------------------------------


def run_window() -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    from werkzeug.serving import make_server

    root = tk.Tk()
    root.withdraw()

    port = _free_port()
    if port is None:
        messagebox.showerror(
            APP_NAME,
            f"No hay puertos libres entre {FIRST_PORT} y {LAST_PORT}.\n\n"
            "Cierre el programa que los está ocupando y vuelva a intentarlo.",
        )
        return 1

    try:
        from app import create_app

        flask_app = create_app()
        server = make_server(HOST, port, flask_app, threaded=True)
    except Exception as exc:  # noqa: BLE001 — se muestra al usuario, no se traga
        log = _log_crash(exc)
        messagebox.showerror(
            APP_NAME,
            f"No se pudo iniciar el programa.\n\n{exc}\n\n"
            + (f"Detalle técnico en:\n{log}" if log else ""),
        )
        return 1

    url = f"http://localhost:{port}"
    kiosk_url = f"{url}/acceso/"
    data_dir = Path(flask_app.config["DATABASE"]).parent

    # El kiosco solo se abre solo si el reconocimiento facial está activado. Si el
    # gimnasio no lo usa, una pestaña con la cámara apagada es solo un estorbo.
    try:
        with flask_app.app_context():
            from app.settings import face_recognition_enabled

            kiosk_enabled = face_recognition_enabled()
    except Exception:  # noqa: BLE001 — un ajuste ilegible no puede impedir arrancar
        kiosk_enabled = False

    threading.Thread(target=server.serve_forever, daemon=True).start()

    # --- Ventana de control --------------------------------------------------
    root.title(APP_NAME)
    root.resizable(False, False)
    try:
        root.iconbitmap(str(_resource("gymlite.ico")))
    except Exception:  # sin icono la ventana sigue siendo válida
        pass

    frame = ttk.Frame(root, padding=(24, 20))
    frame.grid(sticky="nsew")

    ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 16, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w"
    )
    ttk.Label(
        frame,
        text="El programa está en ejecución.",
        foreground="#15803d",
        font=("Segoe UI", 10),
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 14))

    ttk.Label(frame, text="Dirección:", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w")
    ttk.Label(frame, text=url, font=("Segoe UI", 9)).grid(row=2, column=1, sticky="w", padx=(10, 0))

    ttk.Label(frame, text="Datos:", font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky="nw")
    ttk.Label(frame, text=str(data_dir), font=("Segoe UI", 9), wraplength=320, justify="left").grid(
        row=3, column=1, sticky="w", padx=(10, 0)
    )

    ttk.Separator(frame).grid(row=4, column=0, columnspan=2, sticky="ew", pady=14)

    buttons = ttk.Frame(frame)
    buttons.grid(row=5, column=0, columnspan=2, sticky="e")

    def open_browser() -> None:
        webbrowser.open(url)

    def open_kiosk() -> None:
        webbrowser.open_new_tab(kiosk_url)

    def quit_app() -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()
        root.after(400, root.destroy)

    ttk.Button(buttons, text="Abrir en el navegador", command=open_browser).grid(row=0, column=0)
    if kiosk_enabled:
        ttk.Button(buttons, text="Abrir el kiosco", command=open_kiosk).grid(row=0, column=1, padx=(8, 0))
    ttk.Button(buttons, text="Detener y salir", command=quit_app).grid(row=0, column=2, padx=(8, 0))

    root.protocol("WM_DELETE_WINDOW", quit_app)

    root.deiconify()
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_width()) // 2
    y = (root.winfo_screenheight() - root.winfo_height()) // 3
    root.geometry(f"+{x}+{y}")

    # Un pequeño retraso evita que el navegador cargue antes de que el servidor
    # acepte conexiones. El kiosco va después, en su propia pestaña: abrir los dos a
    # la vez hace que el navegador decida el orden y a veces el kiosco queda delante.
    if "--no-browser" not in sys.argv[1:]:
        root.after(600, open_browser)
        if kiosk_enabled:
            root.after(1800, open_kiosk)
    root.mainloop()
    return 0


def main() -> int:
    _prepare_streams()
    os.chdir(Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent)

    if "--init-db" in sys.argv[1:]:
        return init_database()
    return run_window()


if __name__ == "__main__":
    raise SystemExit(main())
