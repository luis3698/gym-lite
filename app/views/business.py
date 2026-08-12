"""Datos del establecimiento que se imprimen en los recibos.

Todo lo de esta pantalla acaba en el papel: la cabecera con el nombre y el NIT, y el
pie con las leyendas legales. Viene con un ejemplo relleno para que el primer recibo ya
salga con la forma correcta y se vea qué va en cada sitio.
"""

from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..config import RECEIPT_WIDTHS
from ..helpers import optional_string
from ..receipts import receipt_barcode
from ..security import audit, roles_required, verify_password
from ..settings import BARCODE_ENABLED, barcode_enabled, business_info, get_setting, set_flag, set_setting

bp = Blueprint("business", __name__, url_prefix="/negocio")

# (clave, etiqueta, pista, ¿varias líneas?)
CAMPOS = (
    ("business_name", "Nombre del establecimiento", "Sale en grande en la cabecera", False),
    ("business_nit", "NIT o identificación tributaria", "Con dígito de verificación", False),
    ("business_address", "Dirección", "Calle, número y local", False),
    ("business_city", "Ciudad y país", "", False),
    ("business_phone", "Teléfonos", "Fijo y celular, separados como quiera", False),
    ("business_email", "Correo electrónico", "", False),
    ("business_extra", "Web y redes sociales", "Se imprime debajo de los contactos", False),
    ("business_tax_note", "Nota tributaria",
     "Por ejemplo «No responsable de IVA» o el número de resolución de facturación", False),
    ("business_footer", "Pie del recibo",
     "Leyendas legales, política de cambios y despedida. Una línea por renglón.", True),
)


@bp.route("/", methods=("GET", "POST"))
@roles_required("ADMIN")
def index():
    if request.method == "POST":
        # Dos formularios distintos llegan aquí; `accion` los separa para que guardar
        # uno no pise lo del otro.
        if request.form.get("accion") == "barcode":
            return _toggle_barcode()

        ancho = optional_string(request.form.get("receipt_width")) or ""
        if ancho not in RECEIPT_WIDTHS:
            flash("Ancho de papel inválido.", "error")
            return redirect(url_for("business.index"))

        if not optional_string(request.form.get("business_name")):
            flash("El nombre del establecimiento no puede quedar vacío: encabeza cada recibo.", "error")
            return redirect(url_for("business.index"))

        for clave, _etiqueta, _pista, _multi in CAMPOS:
            # Los campos vacíos se guardan vacíos y simplemente no se imprimen: un
            # gimnasio sin NIT no debe ver un hueco con la palabra NIT al lado.
            set_setting(clave, (request.form.get(clave) or "").strip())
        set_setting("receipt_width", ancho)

        audit("BUSINESS_UPDATED", request.form.get("business_name", ""))
        flash("Datos del negocio actualizados. Los próximos recibos ya salen con ellos.", "success")
        return redirect(url_for("business.index"))

    return render_template(
        "business/index.html",
        campos=CAMPOS,
        valores={clave: get_setting(clave) for clave, _e, _p, _m in CAMPOS},
        ancho=get_setting("receipt_width"),
        anchos=RECEIPT_WIDTHS,
        negocio=business_info(),
        codigos=barcode_enabled(),
        ejemplo=receipt_barcode("SALE", 123),
    )


def _toggle_barcode():
    """Activa o desactiva el código de barras de los recibos.

    Se pide la contraseña porque apagarlo deja sin poder leer los recibos nuevos en el
    módulo de devoluciones, y eso no debería poder hacerse por descuido.
    """
    activar = request.form.get("enabled") == "1"
    password = request.form.get("password") or ""

    if not password:
        flash("Escriba su contraseña para cambiar esta opción.", "error")
        return redirect(url_for("business.index"))
    if not verify_password(g.user["password_hash"], password):
        audit("BARCODE_TOGGLED", "contraseña incorrecta", success=False)
        flash("Contraseña incorrecta. No se cambió nada.", "error")
        return redirect(url_for("business.index"))

    set_flag(BARCODE_ENABLED, activar)
    audit("BARCODE_TOGGLED", "activados" if activar else "desactivados")
    flash(
        "Los recibos volverán a llevar código de barras."
        if activar else
        "Los recibos dejarán de llevar código de barras. Los ya impresos siguen "
        "siendo válidos y se pueden seguir leyendo para devoluciones.",
        "success",
    )
    return redirect(url_for("business.index"))
