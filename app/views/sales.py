"""Venta de productos: catálogo, carrito, liquidación, recibo e historial.

El carrito vive en la sesión del navegador (no en la base): es un borrador del
usuario, no un dato del negocio, y así no deja filas huérfanas si nunca se liquida.
"""

from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from ..config import MAX_ITEM_QUANTITY, VALID_PAYMENT_METHODS
from ..db import query_all, query_one, query_value, transaction
from ..helpers import now_str, optional_string
from ..security import audit, roles_required
from ..receipts import receipt_barcode
from ..settings import business_info

bp = Blueprint("sales", __name__, url_prefix="/ventas")

CART_KEY = "cart"


def _get_cart() -> dict[str, int]:
    """Carrito como {id_producto (texto): cantidad}.

    Las claves son texto porque la sesión de Flask se serializa a JSON, que no
    admite claves enteras.
    """
    cart = session.get(CART_KEY)
    return dict(cart) if isinstance(cart, dict) else {}


def _save_cart(cart: dict[str, int]) -> None:
    session[CART_KEY] = cart
    session.modified = True


def _cart_lines(cart: dict[str, int]) -> tuple[list[dict], float, list[str]]:
    """Resuelve el carrito contra el catálogo actual.

    Devuelve (líneas, total, avisos). Relee precio y stock en cada carga: si el
    administrador cambió el catálogo mientras el carrito estaba abierto, se cobraría
    el precio antiguo.
    """
    if not cart:
        return [], 0.0, []

    ids = [int(k) for k in cart if str(k).isdigit()]
    if not ids:
        return [], 0.0, []

    placeholders = ",".join("?" * len(ids))
    products = {
        row["id"]: row
        for row in query_all(f"SELECT * FROM products WHERE id IN ({placeholders})", ids)
    }

    lines: list[dict] = []
    notices: list[str] = []
    total = 0.0
    changed = False

    for key in list(cart):
        product = products.get(int(key)) if str(key).isdigit() else None
        quantity = int(cart[key])

        if product is None or not product["active"]:
            name = product["name"] if product else "Un producto"
            notices.append(f"«{name}» ya no está disponible y se quitó del carrito.")
            cart.pop(key)
            changed = True
            continue

        if product["stock"] <= 0:
            notices.append(f"«{product['name']}» quedó sin stock y se quitó del carrito.")
            cart.pop(key)
            changed = True
            continue

        if quantity > product["stock"]:
            notices.append(
                f"Solo quedan {product['stock']} unidad(es) de «{product['name']}»; "
                f"se ajustó la cantidad."
            )
            quantity = product["stock"]
            cart[key] = quantity
            changed = True

        subtotal = product["price"] * quantity
        total += subtotal
        lines.append(
            {
                "id": product["id"],
                "name": product["name"],
                "price": product["price"],
                "stock": product["stock"],
                "quantity": quantity,
                "subtotal": subtotal,
            }
        )

    if changed:
        _save_cart(cart)
    return lines, round(total, 2), notices


@bp.route("/")
@roles_required("ADMIN", "CAJA")
def index():
    products = query_all("SELECT * FROM products WHERE active = 1 ORDER BY name")
    lines, total, notices = _cart_lines(_get_cart())
    for notice in notices:
        flash(notice, "warning")
    return render_template("sales/index.html", products=products, lines=lines, total=total)


@bp.post("/carrito/agregar/<int:product_id>")
@roles_required("ADMIN", "CAJA")
def cart_add(product_id: int):
    product = query_one("SELECT * FROM products WHERE id = ? AND active = 1", (product_id,))
    if product is None:
        flash("El producto ya no está disponible.", "error")
        return redirect(url_for("sales.index"))

    cart = _get_cart()
    key = str(product_id)
    current = int(cart.get(key, 0))

    if current + 1 > product["stock"]:
        flash(f"Solo quedan {product['stock']} unidad(es) de «{product['name']}» en stock.", "warning")
    else:
        cart[key] = current + 1
        _save_cart(cart)
    return redirect(url_for("sales.index"))


@bp.post("/carrito/actualizar/<int:product_id>")
@roles_required("ADMIN", "CAJA")
def cart_update(product_id: int):
    product = query_one("SELECT * FROM products WHERE id = ?", (product_id,))
    cart = _get_cart()
    key = str(product_id)

    raw = (request.form.get("quantity") or "").strip()
    if not raw.isdigit() or int(raw) < 1:
        cart.pop(key, None)
        _save_cart(cart)
        return redirect(url_for("sales.index"))

    quantity = min(int(raw), MAX_ITEM_QUANTITY)
    if product is not None:
        quantity = min(quantity, product["stock"])
    if quantity < 1:
        cart.pop(key, None)
    else:
        cart[key] = quantity
    _save_cart(cart)
    return redirect(url_for("sales.index"))


@bp.post("/carrito/quitar/<int:product_id>")
@roles_required("ADMIN", "CAJA")
def cart_remove(product_id: int):
    cart = _get_cart()
    cart.pop(str(product_id), None)
    _save_cart(cart)
    return redirect(url_for("sales.index"))


@bp.post("/carrito/vaciar")
@roles_required("ADMIN", "CAJA")
def cart_clear():
    _save_cart({})
    return redirect(url_for("sales.index"))


@bp.route("/liquidar", methods=("GET", "POST"))
@roles_required("ADMIN", "CAJA")
def checkout():
    lines, total, notices = _cart_lines(_get_cart())
    for notice in notices:
        flash(notice, "warning")
    if not lines:
        flash("El carrito está vacío.", "error")
        return redirect(url_for("sales.index"))

    if request.method == "POST":
        try:
            sale_id = _register_sale(lines, request.form)
            _save_cart({})
            flash("Venta registrada correctamente.", "success")
            return redirect(url_for("sales.receipt", sale_id=sale_id))
        except ValueError as exc:
            flash(str(exc), "error")

    # Autocompletado del comprador por número de identidad.
    buyer = {}
    document = optional_string(request.values.get("buyer_document"))
    if document:
        client = query_one(
            "SELECT first_name, last_name, phone, document_id FROM clients WHERE document_id = ?",
            (document,),
        )
        if client:
            buyer = {
                "buyer_document": client["document_id"],
                "buyer_name": f"{client['first_name']} {client['last_name']}",
                "buyer_phone": client["phone"] or "",
            }
            if request.method == "GET":
                flash("Cliente encontrado, datos autocompletados.", "success")
        else:
            buyer = {"buyer_document": document}
            if request.method == "GET":
                flash(
                    "No se encontró un cliente registrado con ese documento; "
                    "diligencie los datos manualmente.",
                    "warning",
                )

    if request.method == "POST":
        buyer = dict(request.form)

    return render_template("sales/checkout.html", lines=lines, total=total, buyer=buyer)


def _register_sale(lines: list[dict], form) -> int:
    document = optional_string(form.get("buyer_document"))
    name = optional_string(form.get("buyer_name"))
    if not document or not name:
        raise ValueError("El número de identidad y el nombre del comprador son obligatorios.")

    payment_method = optional_string(form.get("payment_method")) or "EFECTIVO"
    if payment_method not in VALID_PAYMENT_METHODS:
        raise ValueError("Método de pago inválido.")

    client = query_one("SELECT id FROM clients WHERE document_id = ?", (document,))
    now = now_str()

    with transaction() as db:
        total = 0.0
        prepared: list[tuple[int, int, float]] = []

        for line in lines:
            # El precio se relee dentro de la transacción: el de `lines` pudo quedar
            # obsoleto entre que se pintó la pantalla y se pulsó "Confirmar".
            product = db.execute(
                "SELECT id, name, price, stock, active FROM products WHERE id = ?", (line["id"],)
            ).fetchone()
            if product is None or not product["active"]:
                raise ValueError("Uno de los productos ya no está disponible.")

            quantity = int(line["quantity"])
            # El descuento va con la condición dentro del propio UPDATE. Comprobar el
            # stock y descontarlo en dos pasos permitiría que dos ventas simultáneas
            # de la última unidad pasaran ambas y dejaran el stock en negativo.
            cur = db.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ? AND active = 1 AND stock >= ?",
                (quantity, product["id"], quantity),
            )
            if cur.rowcount == 0:
                raise ValueError(
                    f"Stock insuficiente para «{product['name']}». Disponible: {product['stock']}."
                )

            total += product["price"] * quantity
            prepared.append((product["id"], quantity, product["price"]))

        total = round(total, 2)
        cur = db.execute(
            """INSERT INTO sales (seller_id, client_id, buyer_document, buyer_name, buyer_phone,
                                  total, payment_method, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user["id"], client["id"] if client else None, document, name,
                optional_string(form.get("buyer_phone")), total, payment_method, now,
            ),
        )
        sale_id = int(cur.lastrowid or 0)
        for product_id, quantity, unit_price in prepared:
            db.execute(
                "INSERT INTO sale_items (sale_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                (sale_id, product_id, quantity, unit_price),
            )

    audit("SALE_CREATED", f"venta a {document} por {total}")
    return sale_id


@bp.route("/recibo/<int:sale_id>")
@roles_required("ADMIN", "CAJA")
def receipt(sale_id: int):
    sale = query_one(
        """SELECT s.*, u.first_name AS seller_first, u.last_name AS seller_last
             FROM sales s JOIN users u ON u.id = s.seller_id
            WHERE s.id = ?""",
        (sale_id,),
    )
    if sale is None:
        flash("Venta no encontrada.", "error")
        return redirect(url_for("sales.index"))

    items = query_all(
        """SELECT si.quantity, si.unit_price, p.name
             FROM sale_items si JOIN products p ON p.id = si.product_id
            WHERE si.sale_id = ?""",
        (sale_id,),
    )
    return render_template(
        "sales/receipt.html",
        sale=sale,
        items=items,
        negocio=business_info(),
        codigo=receipt_barcode("SALE", sale_id),
    )


HISTORY_MAX_ROWS = 300


@bp.route("/historial")
@roles_required("ADMIN", "CAJA")
def history():
    sales = query_all(
        """SELECT s.*, u.first_name AS seller_first, u.last_name AS seller_last,
                  (SELECT GROUP_CONCAT(p.name || ' x' || si.quantity, ', ')
                     FROM sale_items si JOIN products p ON p.id = si.product_id
                    WHERE si.sale_id = s.id) AS items_summary
             FROM sales s JOIN users u ON u.id = s.seller_id
            ORDER BY s.created_at DESC, s.id DESC LIMIT ?""",
        (HISTORY_MAX_ROWS,),
    )
    # El conteo y el total se calculan aparte, con una consulta de agregación sobre
    # TODAS las ventas, no sumando las filas mostradas: si no, en cuanto hubiera más
    # de HISTORY_MAX_ROWS ventas el total mostrado quedaría por debajo del real sin
    # que nada lo advirtiera (el mismo error que evita app/views/income.py).
    resumen = query_one("SELECT COUNT(*) AS n, COALESCE(SUM(total), 0) AS total FROM sales")
    total_count = resumen["n"] if resumen else 0
    total = resumen["total"] if resumen else 0
    return render_template(
        "sales/history.html",
        sales=sales,
        total=total,
        total_count=total_count,
        max_rows=HISTORY_MAX_ROWS,
    )
