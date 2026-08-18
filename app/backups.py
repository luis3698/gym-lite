"""Copias de seguridad de la base de datos.

Todo el gimnasio vive en un único archivo `gym.db`. Un disco que falla, un borrado por
error o un ransomware se lo llevan entero: clientes, inscripciones, ventas e histórico.
Este módulo es el seguro.

## Qué entra en la copia

La copia es un `.zip` con dos cosas: `gym.db` (toda la caja, las transacciones, los
usuarios, los clientes, las devoluciones y el registro de actividad — los recibos no
se guardan como archivo aparte, se generan al vuelo a partir de estos mismos datos, así
que quedan cubiertos con solo copiar la base) y la carpeta `uploads/` completa (fotos de
clientes, de personal y de productos). Sin la carpeta, restaurar en otro equipo dejaba
fichas con fotos rotas aunque el resto de los datos volviera intacto.

La licencia (`license.dat`, `license_key.bin`) se queda fuera a propósito: vive en
`INSTANCE_DIR` junto a la base, pero es la licencia DE ESTE EQUIPO. Si viajara dentro de
la copia, restaurar una base en otro equipo le regalaría la licencia de quien la hizo
—ver `contexto.md`—.

## Por qué no se copia el archivo con `shutil.copy`

La base funciona en modo WAL: lo escrito hace un momento puede estar todavía en
`gym.db-wal` y no en `gym.db`. Copiar solo el archivo principal daría una copia
silenciosamente incompleta —el peor tipo de copia, la que parece buena hasta el día que
hace falta—. Se usa `sqlite3.Connection.backup()`, que es la API pensada para esto:
produce una copia coherente aunque haya escrituras en curso. Esa copia coherente es la
que después se mete en el `.zip`.

## Copias antiguas

Antes de que este módulo empaquetara la carpeta de fotos, una copia era directamente el
archivo `.db`. Esas copias siguen siendo válidas: se pueden seguir viendo, descargando,
borrando y restaurando —solo que, al no llevar `uploads/`, restaurarlas no trae las
fotos—.

## Restaurar

También va por `backup()`, pero al revés: del archivo elegido hacia la base en uso. Así
se sustituye el CONTENIDO sin tocar el archivo del disco, y no hace falta cerrar el
programa ni pelearse con Windows por un archivo bloqueado. Las fotos del `.zip` se
copian encima de `uploads/` (se añaden y se sobrescriben las que coincidan en nombre; no
se borra nada que no esté en la copia, para no perder fotos por una copia parcial).

Antes de restaurar nada se guarda una copia del estado actual. Restaurar es destructivo
y a veces se descubre tarde que era el archivo equivocado.
"""

from __future__ import annotations

import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from .config import (
    BACKUP_DIR,
    BACKUP_FREQUENCY_DAYS,
    DATABASE_PATH,
    MAX_BACKUP_KEEP,
    MIN_BACKUP_KEEP,
    UPLOAD_DIR,
)

# Tablas que tiene que traer un archivo para considerarlo una base de este programa.
# Sin esta comprobación se podría restaurar cualquier SQLite —o cualquier archivo— y
# dejar el gimnasio sin datos y sin manera de volver atrás.
REQUIRED_TABLES = {"users", "clients", "memberships", "sales", "products"}

# Nombre con el que la base viaja dentro del .zip, y prefijo de las fotos.
DB_ARCNAME = "gym.db"
UPLOADS_PREFIX = "uploads/"

# gymlite-2026-08-11_1645.zip / -auto.zip / -previa-2.db (copias antiguas)
BACKUP_PATTERN = re.compile(
    r"^gymlite-\d{4}-\d{2}-\d{2}_\d{4}(-[a-z]+)?(-\d+)?\.(zip|db)$"
)


class BackupError(RuntimeError):
    """La copia o la restauración no se pudo completar."""


def _copy_database(origen: Path, destino: Path) -> None:
    """Copia el contenido de una base a otra con la API `backup` de SQLite.

    Las conexiones se cierran a mano y no con `with`: en sqlite3, `with conexión`
    confirma o deshace la transacción, pero **no cierra la conexión**. Dejarlas
    abiertas mantenía el archivo bloqueado por Windows, y entonces las copias
    antiguas no se podían borrar nunca —la carpeta crecía sin freno sin que nada
    avisara—.
    """
    src = sqlite3.connect(str(origen))
    try:
        dst = sqlite3.connect(str(destino))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _write_zip_backup(db_snapshot: Path, destino: Path) -> None:
    """Empaqueta la foto de la base y la carpeta de imágenes en un .zip."""
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_snapshot, DB_ARCNAME)
        if UPLOAD_DIR.is_dir():
            for archivo in UPLOAD_DIR.iterdir():
                if archivo.is_file():
                    zf.write(archivo, UPLOADS_PREFIX + archivo.name)


def backup_dir() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def create_backup(database_path: str | Path | None = None, *, suffix: str = "") -> Path:
    """Crea una copia (.zip: base + fotos) y devuelve su ruta.

    `suffix` distingue las automáticas (`auto`) y las de seguridad antes de
    restaurar (`previa`).
    """
    origen = Path(database_path or DATABASE_PATH)
    if not origen.exists():
        raise BackupError("No se encontró la base de datos que se quería copiar.")

    marca = datetime.now().strftime("%Y-%m-%d_%H%M")
    nombre = f"gymlite-{marca}{('-' + suffix) if suffix else ''}.zip"
    destino = backup_dir() / nombre

    # Dos copias en el mismo minuto: se añade un contador en vez de pisar la anterior.
    contador = 2
    while destino.exists():
        destino = backup_dir() / f"gymlite-{marca}{('-' + suffix) if suffix else ''}-{contador}.zip"
        contador += 1

    with tempfile.TemporaryDirectory(prefix="gymlite-backup-") as carpeta_temp:
        snapshot = Path(carpeta_temp) / "gym.db"
        try:
            _copy_database(origen, snapshot)
        except sqlite3.Error as exc:
            raise BackupError(f"No se pudo crear la copia: {exc}") from exc

        try:
            _write_zip_backup(snapshot, destino)
        except OSError as exc:
            destino.unlink(missing_ok=True)
            raise BackupError(f"No se pudo crear la copia: {exc}") from exc

    return destino


def list_backups() -> list[dict]:
    """Copias existentes, de la más reciente a la más antigua."""
    carpeta = backup_dir()
    copias = []
    for archivo in list(carpeta.glob("*.zip")) + list(carpeta.glob("*.db")):
        try:
            info = archivo.stat()
        except OSError:
            continue
        copias.append({
            "name": archivo.name,
            "size": info.st_size,
            "created": datetime.fromtimestamp(info.st_mtime),
            "auto": "-auto" in archivo.name,
            "safety": "-previa" in archivo.name,
            # Copia de antes de empaquetar uploads/: restaurarla no trae fotos.
            "legacy": archivo.suffix == ".db",
        })
    copias.sort(key=lambda c: c["created"], reverse=True)
    return copias


def prune_backups(keep: int) -> int:
    """Borra las copias más viejas y devuelve cuántas se eliminaron.

    Las copias de seguridad que se hacen ANTES de restaurar no se tocan: son
    precisamente las que se van a necesitar si la restauración salió mal.
    """
    keep = max(MIN_BACKUP_KEEP, min(MAX_BACKUP_KEEP, keep))
    borrables = [c for c in list_backups() if not c["safety"]]
    borradas = 0
    for copia in borrables[keep:]:
        try:
            (backup_dir() / copia["name"]).unlink()
            borradas += 1
        except OSError:
            continue
    return borradas


def resolve_backup(name: str) -> Path:
    """Ruta de una copia a partir de su nombre, rechazando cualquier cosa rara.

    Solo se acepta un nombre que encaje exactamente con el patrón de las copias que
    genera este programa: así no se puede pedir `../../otra/cosa`, un archivo de
    fuera de la carpeta de copias, ni nada que no sea una copia real.
    """
    limpio = Path(name or "").name
    if limpio != (name or "") or not BACKUP_PATTERN.match(limpio):
        raise BackupError("Nombre de copia inválido.")
    ruta = backup_dir() / limpio
    if not ruta.exists():
        raise BackupError("Esa copia ya no existe.")
    return ruta


def _verify_sqlite(path: Path) -> dict:
    """Comprueba que un archivo SQLite es una base de este programa y la resume."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise BackupError(f"El archivo no se pudo abrir como base de datos: {exc}") from exc

    try:
        tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        faltan = REQUIRED_TABLES - tablas
        if faltan:
            raise BackupError(
                "El archivo no es una copia de GymManager Lite: le faltan las tablas "
                + ", ".join(sorted(faltan)) + "."
            )

        resumen = {}
        for tabla in ("clients", "memberships", "sales", "users", "products", "refunds"):
            try:
                resumen[tabla] = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
            except sqlite3.Error:
                resumen[tabla] = 0

        # Una base con cero usuarios no permitiría entrar al programa después.
        if resumen["users"] == 0:
            raise BackupError(
                "La copia no tiene ningún usuario del sistema: al restaurarla nadie "
                "podría iniciar sesión."
            )
        return resumen
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"El archivo está dañado o no es una base de datos: {exc}") from exc
    finally:
        conn.close()


def verify_backup(path: Path) -> dict:
    """Comprueba que el archivo es una copia de este programa y resume su contenido.

    Acepta tanto el formato nuevo (`.zip` con `gym.db` y `uploads/`) como las copias
    antiguas (el archivo SQLite suelto). Se hace ANTES de tocar nada: restaurar un
    archivo que no era deja el gimnasio sin datos, y a esas alturas el error ya
    cuesta caro.
    """
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            if DB_ARCNAME not in zf.namelist():
                raise BackupError(
                    "El archivo no es una copia de GymManager Lite: no contiene la base de datos."
                )
            with tempfile.TemporaryDirectory(prefix="gymlite-restore-") as carpeta_temp:
                extraido = Path(carpeta_temp) / "gym.db"
                extraido.write_bytes(zf.read(DB_ARCNAME))
                return _verify_sqlite(extraido)

    return _verify_sqlite(path)


def restore_backup(path: Path, database_path: str | Path | None = None) -> dict:
    """Sustituye el contenido de la base en uso (y las fotos) por los de la copia.

    Devuelve el resumen de lo restaurado. Antes guarda una copia del estado actual.
    """
    destino = Path(database_path or DATABASE_PATH)
    resumen = verify_backup(path)

    # Red de seguridad: si esto era un error, el estado anterior sigue estando.
    create_backup(destino, suffix="previa")

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            with tempfile.TemporaryDirectory(prefix="gymlite-restore-") as carpeta_temp:
                extraido = Path(carpeta_temp) / "gym.db"
                extraido.write_bytes(zf.read(DB_ARCNAME))
                try:
                    _copy_database(extraido, destino)
                except sqlite3.Error as exc:
                    raise BackupError(f"No se pudo restaurar: {exc}") from exc

            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            for miembro in zf.namelist():
                if not miembro.startswith(UPLOADS_PREFIX) or miembro.endswith("/"):
                    continue
                nombre_archivo = Path(miembro).name
                if not nombre_archivo:
                    continue
                (UPLOAD_DIR / nombre_archivo).write_bytes(zf.read(miembro))
    else:
        try:
            _copy_database(path, destino)
        except sqlite3.Error as exc:
            raise BackupError(f"No se pudo restaurar: {exc}") from exc

    return resumen


# --- Copia automática ---------------------------------------------------------


def days_since_last_backup() -> float | None:
    """Días desde la última copia automática, o None si no hay ninguna."""
    automaticas = [c for c in list_backups() if c["auto"]]
    if not automaticas:
        return None
    return (datetime.now() - automaticas[0]["created"]).total_seconds() / 86400


def due(frequency: str) -> bool:
    """¿Toca copia automática con esta frecuencia?"""
    if frequency not in BACKUP_FREQUENCY_DAYS:
        return False
    if frequency == "STARTUP":
        return True
    ultima = days_since_last_backup()
    return ultima is None or ultima >= BACKUP_FREQUENCY_DAYS[frequency]
