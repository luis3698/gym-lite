"""Administración del catálogo de productos (solo Administrador)."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..config import MAX_STOCK
from ..db import execute, insert, query_all, query_one
from ..helpers import InvalidNumber, now_str, optional_string, parse_optional_int, parse_price
from ..security import audit, roles_required
from ..uploads import UploadError, delete_image, resolve_captured_photo

bp = Blueprint("products", __name__, url_prefix="/productos")


@bp.route("/")
@roles_required("ADMIN")
def index():
    return render_template(
        "products/index.html",
        products=query_all("SELECT * FROM products WHERE active = 1 ORDER BY name"),
        max_stock=MAX_STOCK,
    )


@bp.post("/nuevo")
@roles_required("ADMIN")
def create():
    try:
        name = optional_string(request.form.get("name"))
        if not name:
            raise ValueError("El producto requiere un nombre.")
        price = parse_price(request.form.get("price"), field="El precio")
        stock = parse_optional_int(request.form.get("stock"), minimum=0, maximum=MAX_STOCK) or 0
        # La imagen llega del editor del navegador como data URL, ya recortada.
        image, _ = resolve_captured_photo(None, request.form.get("image_data"))

        insert(
            "INSERT INTO products (name, price, stock, category, image, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, price, stock, optional_string(request.form.get("category")), image, now_str()),
        )
        audit("PRODUCT_CREATED", name)
        flash(f"Producto «{name}» agregado al catálogo.", "success")
    except (ValueError, InvalidNumber, UploadError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("products.index"))


@bp.post("/<int:product_id>/editar")
@roles_required("ADMIN")
def edit(product_id: int):
    product = query_one("SELECT * FROM products WHERE id = ?", (product_id,))
    if product is None:
        flash("Producto no encontrado.", "error")
        return redirect(url_for("products.index"))

    try:
        name = optional_string(request.form.get("name"))
        if not name:
            raise ValueError("El nombre del producto no puede quedar vacío.")
        price = parse_price(request.form.get("price"), field="El precio")
        # Un stock negativo dejaría "vender" unidades inexistentes en el siguiente pedido.
        stock = parse_optional_int(request.form.get("stock"), minimum=0, maximum=MAX_STOCK)
        if stock is None:
            raise ValueError("El stock debe ser un número entero mayor o igual a cero.")
        image, to_delete = resolve_captured_photo(
            product["image"], request.form.get("image_data")
        )

        execute(
            "UPDATE products SET name = ?, price = ?, stock = ?, category = ?, image = ? WHERE id = ?",
            (name, price, stock, optional_string(request.form.get("category")), image, product_id),
        )
        delete_image(to_delete)
        audit("PRODUCT_UPDATED", name)
        flash(f"Producto «{name}» actualizado.", "success")
    except (ValueError, InvalidNumber, UploadError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("products.index"))


@bp.post("/<int:product_id>/eliminar")
@roles_required("ADMIN")
def delete(product_id: int):
    """Baja lógica: el producto sigue en las ventas ya registradas."""
    product = query_one("SELECT * FROM products WHERE id = ?", (product_id,))
    if product is None:
        flash("Producto no encontrado.", "error")
        return redirect(url_for("products.index"))

    execute("UPDATE products SET active = 0 WHERE id = ?", (product_id,))
    audit("PRODUCT_DELETED", product["name"])
    flash(
        f"«{product['name']}» ya no está disponible en el catálogo. "
        f"Las ventas registradas con este producto se conservan.",
        "success",
    )
    return redirect(url_for("products.index"))
