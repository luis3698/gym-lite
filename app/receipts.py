"""Código de barras de un recibo, según esté activado o no.

Un solo sitio decide si se imprime: las dos vistas de recibo y la vista previa de los
datos del negocio llaman aquí, de modo que apagar el interruptor los apaga todos.
"""

from __future__ import annotations

from .barcode import BarcodeError, reference, svg
from .settings import barcode_enabled


def receipt_barcode(kind: str, doc_id: int) -> str | None:
    """SVG del código de barras del recibo, o None si están desactivados.

    Un fallo generando el código no puede impedir que se imprima el recibo: el cliente
    está esperando su comprobante y el código es un extra para las devoluciones.
    """
    if not barcode_enabled():
        return None
    try:
        return svg(reference(kind, doc_id))
    except BarcodeError:
        return None
