"""Devoluciones: qué se cobró, cuánto se ha devuelto y cuánto queda.

El saldo devolvible **no se guarda en ninguna columna**. Se calcula siempre como el
total del recibo menos la suma de sus devoluciones. Un saldo almacenado se desincroniza
en cuanto una escritura falla a medias o alguien toca la base, y entonces el programa
deja devolver dinero que ya se devolvió. La suma, en cambio, siempre dice la verdad.

Aquí solo vive el cálculo y la validación; el registro va en `views/refunds.py` dentro
de una transacción.
"""

from __future__ import annotations

from .db import query_all, query_one, query_value
from .helpers import duration_label, format_datetime

# Los importes se comparan con dos decimales. Sin redondear, un total de 127000.00000001
# haría que una devolución del importe completo se rechazara por un céntimo invisible.
CENTS = 2


def _round(value: float) -> float:
    return round(float(value or 0), CENTS)


def refunded_total(doc_type: str, doc_id: int) -> float:
    """Cuánto se ha devuelto ya de este recibo."""
    return _round(query_value(
        "SELECT COALESCE(SUM(amount), 0) FROM refunds WHERE doc_type = ? AND doc_id = ?",
        (doc_type, doc_id), 0,
    ))


def history(doc_type: str, doc_id: int) -> list:
    """Todas las devoluciones de un recibo, de la más reciente a la más antigua."""
    return query_all(
        """SELECT r.*, u.first_name, u.last_name
             FROM refunds r JOIN users u ON u.id = r.created_by_id
            WHERE r.doc_type = ? AND r.doc_id = ?
            ORDER BY r.created_at DESC, r.id DESC""",
        (doc_type, doc_id),
    )


def load_document(doc_type: str, doc_id: int) -> dict | None:
    """Datos del recibo con su saldo devolvible, o None si no existe.

    Devuelve siempre la misma forma para ventas e inscripciones, de modo que la pantalla
    de devoluciones no tenga que distinguirlas.
    """
    if doc_type == "SALE":
        fila = query_one(
            """SELECT s.*, u.first_name AS staff_first, u.last_name AS staff_last
                 FROM sales s JOIN users u ON u.id = s.seller_id
                WHERE s.id = ?""",
            (doc_id,),
        )
        if fila is None:
            return None
        lineas = [
            {"concepto": f"{r['name']} x{r['quantity']}",
             "importe": _round(r["unit_price"] * r["quantity"])}
            for r in query_all(
                """SELECT p.name, si.quantity, si.unit_price
                     FROM sale_items si JOIN products p ON p.id = si.product_id
                    WHERE si.sale_id = ?""",
                (doc_id,),
            )
        ]
        persona = fila["buyer_name"]
        documento = fila["buyer_document"]
        titulo = "Venta de productos"
        migrado = False
    elif doc_type == "MEMBERSHIP":
        fila = query_one(
            """SELECT m.*, c.first_name AS client_first, c.last_name AS client_last,
                      c.document_id AS client_document,
                      u.first_name AS staff_first, u.last_name AS staff_last
                 FROM memberships m
                 JOIN clients c ON c.id = m.client_id
                 JOIN users   u ON u.id = m.sold_by_id
                WHERE m.id = ?""",
            (doc_id,),
        )
        if fila is None:
            return None
        lineas = [{
            "concepto": duration_label(fila["duration_type"], fila["quantity"]),
            "importe": _round(fila["base_price"]),
        }]
        lineas += [
            {"concepto": r["name"], "importe": _round(r["price"])}
            for r in query_all(
                """SELECT s.name, ms.price
                     FROM membership_services ms JOIN services s ON s.id = ms.service_id
                    WHERE ms.membership_id = ?""",
                (doc_id,),
            )
        ]
        persona = f"{fila['client_first']} {fila['client_last']}"
        documento = fila["client_document"]
        titulo = "Inscripción de gimnasio"
        migrado = bool(fila["is_migrated"])
    else:
        return None

    total = _round(fila["total"])
    devuelto = refunded_total(doc_type, doc_id)

    return {
        "type": doc_type,
        "id": doc_id,
        "reference": ("V" if doc_type == "SALE" else "I") + f"{doc_id:06d}",
        "title": titulo,
        "person": persona,
        "document": documento,
        "staff": f"{fila['staff_first']} {fila['staff_last']}",
        "created_at": format_datetime(fila["created_at"]),
        "payment_method": fila["payment_method"],
        "lines": lineas,
        "total": total,
        "refunded": devuelto,
        "available": _round(total - devuelto),
        "is_migrated": migrado,
        "history": history(doc_type, doc_id),
    }


class RefundError(ValueError):
    """La devolución no se puede registrar."""


def validate(document: dict, amount: float) -> float:
    """Comprueba el importe contra el saldo del recibo y lo devuelve redondeado.

    Se vuelve a leer el saldo aquí, en el momento de guardar, y no se confía en el que
    vio el navegador: entre que se abrió la pantalla y se pulsó el botón, otra caja pudo
    registrar una devolución del mismo recibo.
    """
    importe = _round(amount)
    if importe <= 0:
        raise RefundError("El importe a devolver debe ser mayor que cero.")

    disponible = _round(document["total"] - refunded_total(document["type"], document["id"]))

    if disponible <= 0:
        raise RefundError(
            f"Este recibo ya se devolvió por completo ({document['total']:.2f}). "
            "No queda saldo."
        )
    if importe > disponible:
        raise RefundError(
            f"No se puede devolver {importe:.2f}: del recibo solo quedan "
            f"{disponible:.2f} por devolver."
        )
    return importe
