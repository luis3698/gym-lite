"""Copias de seguridad: configuración, descarga y restauración.

Restaurar es la única acción del programa que puede borrar todo el trabajo de años de
golpe, así que se trata como tal: se comprueba el archivo antes de tocar nada, se
guarda el estado actual por si acaso y se pide la contraseña de quien lo hace.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from ..backups import (
    BackupError,
    backup_dir,
    create_backup,
    days_since_last_backup,
    list_backups,
    prune_backups,
    resolve_backup,
    restore_backup,
    verify_backup,
)
from ..config import (
    BACKUP_FREQUENCIES,
    MAX_BACKUP_KEEP,
    MAX_BACKUP_UPLOAD_BYTES,
    MIN_BACKUP_KEEP,
)
from ..faces import invalidate_gallery
from ..helpers import optional_string
from ..security import audit, roles_required, verify_password
from ..settings import BACKUP_FREQUENCY, BACKUP_KEEP, backup_keep, get_setting, set_setting

bp = Blueprint("backup", __name__, url_prefix="/copias")


@bp.route("/")
@roles_required("ADMIN")
def index():
    copias = list_backups()
    dias = days_since_last_backup()
    return render_template(
        "backup/index.html",
        copias=copias,
        frecuencia=get_setting(BACKUP_FREQUENCY),
        frecuencias=BACKUP_FREQUENCIES,
        conservar=backup_keep(),
        min_conservar=MIN_BACKUP_KEEP,
        max_conservar=MAX_BACKUP_KEEP,
        carpeta=str(backup_dir()),
        dias_desde_ultima=dias,
        total_bytes=sum(c["size"] for c in copias),
    )


@bp.post("/configurar")
@roles_required("ADMIN")
def configure():
    frecuencia = optional_string(request.form.get("frequency")) or ""
    if frecuencia not in BACKUP_FREQUENCIES:
        flash("Frecuencia inválida.", "error")
        return redirect(url_for("backup.index"))

    bruto = (request.form.get("keep") or "").strip()
    if not bruto.isdigit() or not MIN_BACKUP_KEEP <= int(bruto) <= MAX_BACKUP_KEEP:
        flash(
            f"El número de copias a conservar debe estar entre {MIN_BACKUP_KEEP} y {MAX_BACKUP_KEEP}.",
            "error",
        )
        return redirect(url_for("backup.index"))

    set_setting(BACKUP_FREQUENCY, frecuencia)
    set_setting(BACKUP_KEEP, bruto)
    borradas = prune_backups(int(bruto))

    audit("BACKUP_CONFIGURED", f"{frecuencia}, conservar {bruto}")
    mensaje = f"Copias automáticas: {BACKUP_FREQUENCIES[frecuencia].lower()}. Se conservan {bruto}."
    if borradas:
        mensaje += f" Se eliminaron {borradas} copia(s) antigua(s)."
    flash(mensaje, "success")
    return redirect(url_for("backup.index"))


@bp.post("/crear")
@roles_required("ADMIN")
def create_now():
    try:
        ruta = create_backup()
    except BackupError as exc:
        flash(str(exc), "error")
        return redirect(url_for("backup.index"))

    prune_backups(backup_keep())
    audit("BACKUP_CREATED", ruta.name)
    flash(f"Copia creada: {ruta.name}", "success")
    return redirect(url_for("backup.index"))


@bp.get("/descargar/<path:name>")
@roles_required("ADMIN")
def download(name: str):
    try:
        ruta = resolve_backup(name)
    except BackupError as exc:
        flash(str(exc), "error")
        return redirect(url_for("backup.index"))

    audit("BACKUP_DOWNLOADED", ruta.name)
    return send_from_directory(backup_dir(), ruta.name, as_attachment=True)


@bp.post("/eliminar/<path:name>")
@roles_required("ADMIN")
def delete(name: str):
    try:
        ruta = resolve_backup(name)
    except BackupError as exc:
        flash(str(exc), "error")
        return redirect(url_for("backup.index"))

    ruta.unlink(missing_ok=True)
    audit("BACKUP_DELETED", ruta.name)
    flash(f"Copia «{ruta.name}» eliminada.", "success")
    return redirect(url_for("backup.index"))


# --- Restauración -------------------------------------------------------------


def _confirm_password() -> bool:
    """Restaurar sustituye TODOS los datos: se reconfirma quién lo está pidiendo."""
    password = request.form.get("password") or ""
    if not password:
        flash("Escriba su contraseña para confirmar la restauración.", "error")
        return False
    if not verify_password(g.user["password_hash"], password):
        audit("BACKUP_RESTORE_FAILED", "contraseña incorrecta", success=False)
        flash("Contraseña incorrecta. No se restauró nada.", "error")
        return False
    return True


def _after_restore(resumen: dict, origen: str):
    invalidate_gallery()
    audit("BACKUP_RESTORED", origen)
    flash(
        f"Base restaurada desde «{origen}»: {resumen['clients']} cliente(s), "
        f"{resumen['memberships']} inscripción(es), {resumen['sales']} venta(s), "
        f"{resumen['products']} producto(s) y {resumen['refunds']} devolución(es). "
        "Antes de sustituirla se guardó una copia del estado anterior.",
        "success",
    )
    flash(
        "Cierre sesión y vuelva a entrar: su sesión actual corresponde a la base anterior.",
        "warning",
    )
    return redirect(url_for("backup.index"))


@bp.post("/restaurar/<path:name>")
@roles_required("ADMIN")
def restore_existing(name: str):
    try:
        ruta = resolve_backup(name)
    except BackupError as exc:
        flash(str(exc), "error")
        return redirect(url_for("backup.index"))

    if not _confirm_password():
        return redirect(url_for("backup.index"))

    try:
        resumen = restore_backup(ruta)
    except BackupError as exc:
        flash(str(exc), "error")
        return redirect(url_for("backup.index"))

    return _after_restore(resumen, ruta.name)


@bp.post("/restaurar")
@roles_required("ADMIN")
def restore_upload():
    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        flash("Seleccione el archivo de copia (.db) que quiere restaurar.", "error")
        return redirect(url_for("backup.index"))

    if not _confirm_password():
        return redirect(url_for("backup.index"))

    # Se escribe en un temporal antes de mirarlo: hay que abrirlo como base de datos
    # para saber si sirve, y eso necesita un archivo real en disco.
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            temporal = Path(tmp.name)
            leidos = 0
            while True:
                trozo = archivo.stream.read(1024 * 1024)
                if not trozo:
                    break
                leidos += len(trozo)
                if leidos > MAX_BACKUP_UPLOAD_BYTES:
                    raise BackupError(
                        f"El archivo supera los {MAX_BACKUP_UPLOAD_BYTES // (1024 * 1024)} MB. "
                        "No parece una copia de este programa."
                    )
                tmp.write(trozo)

        if leidos == 0:
            raise BackupError("El archivo está vacío.")

        verify_backup(temporal)
        resumen = restore_backup(temporal)
    except BackupError as exc:
        flash(str(exc), "error")
        return redirect(url_for("backup.index"))
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)

    return _after_restore(resumen, archivo.filename)
