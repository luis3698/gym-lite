"""Activación de la licencia e «Información del software».

Solo el administrador puede activar o ver el detalle de la licencia: es lo mismo
que hace cualquier otra pantalla de configuración de esta aplicación (Datos del
negocio, Copias de seguridad). `licensing.blocked` es la única vista que puede ver
cualquier rol autenticado, porque es a donde `license_gate()` manda a quien no es
administrador cuando la licencia no está en un estado usable.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import licensing
from ..config import APP_VERSION
from ..device_id import device_fingerprint_hash
from ..security import audit, login_required, roles_required

bp = Blueprint("licensing", __name__, url_prefix="/licencia")


@bp.route("/activar", methods=("GET", "POST"))
@roles_required("ADMIN")
def activate():
    status = licensing.evaluate_license()

    if request.method == "POST":
        clave = request.form.get("license_key") or ""
        try:
            status = licensing.activate_license(clave)
        except licensing.LicenseError as exc:
            audit("LICENSE_ACTIVATION_FAILED", f"{clave.strip().upper()}: {exc}", success=False)
            flash(str(exc), "error")
            return render_template("licensing/activate.html", status=status)

        audit("LICENSE_ACTIVATED", f"{status.license_key} ({status.tier_label})")
        flash(
            f"Licencia activada: {status.tier_label}"
            + (f", vence el {licensing.format_display(status.expires_at)}." if status.expires_at else " (sin vencimiento)."),
            "success",
        )
        return redirect(url_for("licensing.info"))

    return render_template("licensing/activate.html", status=status)


@bp.route("/")
@roles_required("ADMIN")
def info():
    status = licensing.evaluate_license()
    return render_template(
        "licensing/info.html",
        status=status,
        app_version=APP_VERSION,
        device_fingerprint=device_fingerprint_hash(),
    )


@bp.route("/bloqueado")
@login_required
def blocked():
    status = licensing.evaluate_license()
    if status.usable:
        return redirect(url_for("dashboard.index"))
    return render_template("licensing/blocked.html", status=status)
