"""Compila GymManager Lite y su instalador.

    py -3 installer/build.py

Deja en `dist/GymManagerLite-Setup.exe` un instalador autónomo: no necesita
Python en el equipo de destino, porque lleva dentro el programa ya compilado.

Encadena tres compilaciones de PyInstaller:

    1. La aplicación         -> carpeta con «GymManager Lite.exe» (sin consola).
    2. El desinstalador      -> «Desinstalar GymManager Lite.exe», que se copia
                                dentro de la carpeta anterior.
    3. El asistente gráfico  -> un único .exe que lleva embebido el resultado de
                                los pasos anteriores como carga útil.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER_DIR = ROOT / "installer"
ASSETS_DIR = INSTALLER_DIR / "assets"
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
VENV_DIR = ROOT / ".venv"

APP_NAME = "GymManager Lite"
APP_VERSION = "1.0.0"
PUBLISHER = "GymManager"
SETUP_NAME = "GymManagerLite-Setup"
UNINSTALLER_NAME = "Desinstalar GymManager Lite"

PYINSTALLER_MIN = "6.11"


def log(message: str) -> None:
    print(f"\n=== {message}", flush=True)


def run(command: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=str(cwd or ROOT))
    if result.returncode != 0:
        raise SystemExit(f"\n[ERROR] Falló el comando:\n  {' '.join(command)}")


# --- Entorno de compilación ---------------------------------------------------


def venv_python() -> Path:
    return VENV_DIR / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def ensure_build_env() -> Path:
    """Crea .venv con Flask y PyInstaller si hace falta y devuelve su intérprete."""
    python = venv_python()
    if not python.exists():
        log("Creando el entorno de compilación (.venv)")
        run([sys.executable, "-m", "venv", str(VENV_DIR)])

    log("Instalando dependencias de compilación")
    run([str(python), "-m", "pip", "install", "--upgrade", "pip", "--quiet",
         "--disable-pip-version-check"])
    run([str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
         "-r", str(ROOT / "requirements.txt"), f"pyinstaller>={PYINSTALLER_MIN}"])
    return python


# --- Recursos -----------------------------------------------------------------


def build_assets() -> tuple[Path, Path]:
    log("Generando el icono")
    sys.path.insert(0, str(INSTALLER_DIR))
    from make_icon import build_icon, build_png  # noqa: PLC0415 — solo se usa aquí

    icon = build_icon(ASSETS_DIR / "gymlite.ico")
    logo = build_png(96, ASSETS_DIR / "gymlite-96.png")
    print(f"  {icon}\n  {logo}")
    return icon, logo


VERSION_TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({v0}, {v1}, {v2}, 0),
    prodvers=({v0}, {v1}, {v2}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('0c0a04b0', [
        StringStruct('CompanyName', '{publisher}'),
        StringStruct('FileDescription', '{description}'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', '{internal}'),
        StringStruct('LegalCopyright', '{publisher}'),
        StringStruct('OriginalFilename', '{filename}'),
        StringStruct('ProductName', '{product}'),
        StringStruct('ProductVersion', '{version}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [0x0c0a, 1200])])
  ]
)
"""


def write_version_file(path: Path, description: str, internal: str, filename: str) -> Path:
    """Propiedades del .exe visibles en Windows (pestaña «Detalles»)."""
    major, minor, patch = (int(part) for part in APP_VERSION.split("."))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        VERSION_TEMPLATE.format(
            v0=major, v1=minor, v2=patch, version=APP_VERSION, publisher=PUBLISHER,
            description=description, internal=internal, filename=filename, product=APP_NAME,
        ),
        encoding="utf-8",
    )
    return path


# --- Compilaciones ------------------------------------------------------------


def pyinstaller(python: Path, args: list[str]) -> None:
    run([str(python), "-m", "PyInstaller", "--noconfirm", "--clean", *args])


def sep() -> str:
    return ";" if sys.platform == "win32" else ":"


def build_app(python: Path, icon: Path) -> Path:
    """La aplicación, en carpeta (arranca más rápido que en archivo único)."""
    log("Compilando la aplicación")
    out = BUILD_DIR / "app-dist"
    version = write_version_file(
        BUILD_DIR / "version_app.txt",
        description=f"{APP_NAME} - sistema de gestión de gimnasio",
        internal=APP_NAME,
        filename=f"{APP_NAME}.exe",
    )
    pyinstaller(
        python,
        [
            "--name", APP_NAME,
            "--windowed",
            "--icon", str(icon),
            "--version-file", str(version),
            "--distpath", str(out),
            "--workpath", str(BUILD_DIR / "work-app"),
            "--specpath", str(BUILD_DIR / "spec"),
            "--add-data", f"{ROOT / 'app' / 'templates'}{sep()}app/templates",
            "--add-data", f"{ROOT / 'app' / 'static'}{sep()}app/static",
            "--add-data", f"{ROOT / 'app' / 'schema.sql'}{sep()}app",
            "--add-data", f"{icon}{sep()}.",
            str(ROOT / "gym_launcher.py"),
        ],
    )
    payload = out / APP_NAME
    if not (payload / f"{APP_NAME}.exe").exists():
        raise SystemExit("[ERROR] No se generó el ejecutable de la aplicación.")

    # Si alguien ejecutó el .exe recién compilado para probarlo, habrá dejado una
    # base de datos aquí. Nunca debe viajar dentro del instalador: la instalación
    # tiene que crearla limpia en el equipo de destino.
    stray = payload / "data"
    if stray.exists():
        shutil.rmtree(stray, ignore_errors=True)
        print(f"  [limpieza] eliminada {stray}")
    return payload


def build_uninstaller(python: Path, icon: Path, payload: Path) -> None:
    """El desinstalador vive dentro de la carpeta instalada, así que va en la carga útil."""
    log("Compilando el desinstalador")
    out = BUILD_DIR / "unins-dist"
    version = write_version_file(
        BUILD_DIR / "version_unins.txt",
        description=f"Desinstalador de {APP_NAME}",
        internal=UNINSTALLER_NAME,
        filename=f"{UNINSTALLER_NAME}.exe",
    )
    pyinstaller(
        python,
        [
            "--name", UNINSTALLER_NAME,
            "--onefile",
            "--windowed",
            "--icon", str(icon),
            "--version-file", str(version),
            "--distpath", str(out),
            "--workpath", str(BUILD_DIR / "work-unins"),
            "--specpath", str(BUILD_DIR / "spec"),
            "--add-data", f"{icon}{sep()}.",
            str(INSTALLER_DIR / "uninstall.py"),
        ],
    )
    built = out / f"{UNINSTALLER_NAME}.exe"
    if not built.exists():
        raise SystemExit("[ERROR] No se generó el desinstalador.")
    shutil.copy2(built, payload / built.name)


def build_setup(python: Path, icon: Path, logo: Path, payload: Path) -> Path:
    log("Compilando el instalador")
    version = write_version_file(
        BUILD_DIR / "version_setup.txt",
        description=f"Instalador de {APP_NAME}",
        internal=SETUP_NAME,
        filename=f"{SETUP_NAME}.exe",
    )
    pyinstaller(
        python,
        [
            "--name", SETUP_NAME,
            "--onefile",
            "--windowed",
            "--icon", str(icon),
            "--version-file", str(version),
            "--distpath", str(DIST_DIR),
            "--workpath", str(BUILD_DIR / "work-setup"),
            "--specpath", str(BUILD_DIR / "spec"),
            "--add-data", f"{payload}{sep()}payload",
            "--add-data", f"{INSTALLER_DIR / 'license.txt'}{sep()}.",
            "--add-data", f"{icon}{sep()}.",
            "--add-data", f"{logo}{sep()}.",
            str(INSTALLER_DIR / "installer.py"),
        ],
    )
    setup = DIST_DIR / f"{SETUP_NAME}.exe"
    if not setup.exists():
        raise SystemExit("[ERROR] No se generó el instalador.")
    return setup


def main() -> int:
    if sys.platform != "win32":
        print("El instalador está pensado para Windows.", file=sys.stderr)
        return 1

    python = ensure_build_env()
    icon, logo = build_assets()

    payload = build_app(python, icon)
    build_uninstaller(python, icon, payload)
    setup = build_setup(python, icon, logo, payload)

    size_mb = setup.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 62)
    print("  COMPILACIÓN COMPLETADA")
    print("=" * 62)
    print(f"  Instalador: {setup}")
    print(f"  Tamaño:     {size_mb:.1f} MB")
    print("=" * 62)
    print("\n  Distribuya ese único archivo: no necesita Python ni internet.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
