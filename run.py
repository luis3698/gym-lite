"""Punto de entrada de GymManager Lite.

Uso:
    python run.py

Crea la base de datos y los datos iniciales la primera vez, y luego levanta el
servidor en http://localhost:5000.
"""

from __future__ import annotations

import argparse
import socket
import sys
import webbrowser
from threading import Timer

from app import create_app
from app.config import DEFAULT_HOST, DEFAULT_PORT


def _port_is_free(host: str, port: int) -> bool:
    """Comprueba el puerto antes de arrancar.

    Sin esto, Flask falla con un OSError de WinError 10048 que no dice qué hacer.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="GymManager Lite")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"por defecto {DEFAULT_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"por defecto {DEFAULT_PORT}")
    parser.add_argument("--debug", action="store_true", help="recarga automática al editar el código")
    parser.add_argument("--no-browser", action="store_true", help="no abrir el navegador al arrancar")
    args = parser.parse_args()

    if not _port_is_free(args.host, args.port):
        print(
            f"\n[GymManager Lite] El puerto {args.port} ya está en uso.\n"
            f"Cierre el programa que lo ocupa o use otro puerto:\n"
            f"    python run.py --port 5001\n",
            file=sys.stderr,
        )
        return 1

    app = create_app()
    url = f"http://{'localhost' if args.host == '0.0.0.0' else args.host}:{args.port}"

    print("\n" + "=" * 58)
    print("  GymManager Lite")
    print("=" * 58)
    print(f"  Abra en el navegador:  {url}")
    print(f"  Base de datos:         {app.config['DATABASE']}")
    print("  Detener el servidor:   Ctrl+C")
    print("=" * 58 + "\n")

    # El recargador de Flask ejecuta el proceso dos veces; abrir el navegador solo
    # en la pasada real evita que se abran dos pestañas.
    if not args.no_browser and not args.debug:
        Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
