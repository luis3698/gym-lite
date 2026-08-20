"""Interfaz gráfica para emitir y administrar licencias de GymManager Lite.

Hace exactamente lo mismo que `licensing_cli.py` (de hecho, llama a las mismas
funciones — ver `do_crear`, `do_renovar`, etc. en ese archivo), pero sin terminal:
se abre con doble clic (o mejor, con «Abrir Licencias.vbs», que evita hasta el
problema de qué comando de Python usar) y todo se hace con clics.

Se ejecuta en el equipo del VENDEDOR, nunca en el del cliente — igual que la CLI,
esta carpeta entera queda fuera de lo que empaqueta `installer/build.py`.

La tabla de licencias ES el registro: no hay una base de datos aparte que se pueda
desincronizar. Cada vez que se abre, o al pulsar «Actualizar», se trae la lista
completa y actual directamente de Firestore.
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from version import APP_VERSION  # noqa: E402

import licensing_cli as lic  # noqa: E402

# Paleta: la misma de la aplicación y del instalador (slate + índigo).
INDIGO = "#4f46e5"
INDIGO_DARK = "#312e81"
SLATE_900 = "#0f172a"
SLATE_600 = "#475569"
SLATE_400 = "#94a3b8"
SLATE_200 = "#e2e8f0"
SLATE_100 = "#f1f5f9"
SLATE_50 = "#f8fafc"
GREEN = "#15803d"
GREEN_BG = "#dcfce7"
RED = "#b91c1c"
RED_BG = "#fee2e2"
WHITE = "#ffffff"

FIRESTORE_LINK = (
    "https://console.firebase.google.com/project/{}/settings/serviceaccounts/adminsdk"
)

TIER_ORDER = ("TRIAL", "MONTHLY", "ANNUAL", "PERPETUAL")


def fecha(valor: datetime | None) -> str:
    if valor is None:
        return "No vence"
    return valor.astimezone().strftime("%d/%m/%Y")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("GymManager Lite — Licencias")
        self.geometry("1150x640")
        self.minsize(980, 520)
        self.configure(bg=WHITE)

        self._setup_style()
        self._events: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._rows: list[dict] = []
        self._busy = False

        self._build_layout()
        self.after(150, self._check_service_account)

    # --- Estilo ----------------------------------------------------------

    def _setup_style(self) -> None:
        base = tkfont.nametofont("TkDefaultFont").actual("family")
        family = "Segoe UI" if "Segoe UI" in tkfont.families() else base
        self.font_title = (family, 14, "bold")
        self.font_body = (family, 10)
        self.font_small = (family, 9)
        self.font_bold = (family, 10, "bold")
        self.font_mono = ("Consolas", 11, "bold")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=WHITE)
        style.configure("Card.TFrame", background=SLATE_50)
        style.configure("TLabel", background=WHITE, foreground=SLATE_900, font=self.font_body)
        style.configure("Card.TLabel", background=SLATE_50, foreground=SLATE_900, font=self.font_body)
        style.configure("Muted.TLabel", background=WHITE, foreground=SLATE_600, font=self.font_small)
        style.configure("CardMuted.TLabel", background=SLATE_50, foreground=SLATE_600, font=self.font_small)
        style.configure("Title.TLabel", background=WHITE, font=self.font_title, foreground=SLATE_900)
        style.configure("TButton", font=self.font_body, padding=(12, 6))
        style.configure("Primary.TButton", font=self.font_bold)
        style.map("Primary.TButton", background=[("!disabled", INDIGO)])
        style.configure("TEntry", fieldbackground=WHITE)
        style.configure("TCombobox", fieldbackground=WHITE)
        style.configure(
            "Treeview", font=self.font_small, rowheight=26, fieldbackground=WHITE, background=WHITE
        )
        style.configure("Treeview.Heading", font=self.font_bold)
        style.map("Treeview", background=[("selected", INDIGO)], foreground=[("selected", WHITE)])

    # --- Estructura --------------------------------------------------------

    def _build_layout(self) -> None:
        header = tk.Frame(self, bg=INDIGO_DARK, height=56)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        tk.Label(
            header, text="🔑  Licencias de GymManager Lite", bg=INDIGO_DARK, fg=WHITE,
            font=(self.font_title[0], 13, "bold"), padx=18,
        ).pack(side="left", fill="y")
        self.status_dot = tk.Label(header, text="●", bg=INDIGO_DARK, fg=SLATE_400, font=(self.font_body[0], 12))
        self.status_dot.pack(side="right", padx=(0, 6))
        self.status_label = tk.Label(
            header, text="Conectando con Firebase…", bg=INDIGO_DARK, fg="#c7d2fe", font=self.font_small
        )
        self.status_label.pack(side="right", padx=(0, 4))

        body = tk.Frame(self, bg=WHITE)
        body.pack(fill="both", expand=True, padx=16, pady=14)

        self._build_form(body)
        self._build_table(body)

        footer = tk.Frame(self, bg=SLATE_50, height=30)
        footer.pack(fill="x", side="bottom")
        tk.Frame(self, bg=SLATE_200, height=1).pack(fill="x", side="bottom")
        self.footer_label = tk.Label(
            footer, text="", bg=SLATE_50, fg=SLATE_600, font=self.font_small, anchor="w", padx=12
        )
        self.footer_label.pack(fill="both", expand=True)

    def _build_form(self, parent: tk.Widget) -> None:
        card = tk.LabelFrame(
            parent, text=" Nueva licencia ", bg=SLATE_50, fg=SLATE_900, font=self.font_bold,
            bd=1, relief="solid", padx=16, pady=14,
        )
        card.pack(side="left", fill="y", padx=(0, 14))

        def campo(etiqueta: str) -> tk.Entry:
            ttk.Label(card, text=etiqueta, style="Card.TLabel").pack(anchor="w", pady=(8, 2))
            entrada = tk.Entry(card, font=self.font_body, width=28, relief="solid", bd=1)
            entrada.pack(anchor="w", ipady=3)
            return entrada

        self.entry_cliente = campo("Cliente")

        ttk.Label(card, text="Tipo de licencia", style="Card.TLabel").pack(anchor="w", pady=(8, 2))
        self.tier_var = tk.StringVar(value="Mensual")
        self.combo_tier = ttk.Combobox(
            card, textvariable=self.tier_var, state="readonly", width=26,
            values=[lic.TIER_LABELS[t] for t in TIER_ORDER],
        )
        self.combo_tier.pack(anchor="w")
        self.combo_tier.bind("<<ComboboxSelected>>", lambda e: self._on_tier_change())

        self.days_label = ttk.Label(card, text="Días de prueba", style="Card.TLabel")
        self.days_label.pack(anchor="w", pady=(8, 2))
        self.entry_days = tk.Entry(card, font=self.font_body, width=10, relief="solid", bd=1)
        self.entry_days.insert(0, str(lic.DEFAULT_TRIAL_DAYS))
        self.entry_days.pack(anchor="w", ipady=3)

        self.entry_notas = campo("Notas (opcional)")

        ttk.Button(
            card, text="✚  Crear licencia", style="Primary.TButton", command=self._on_create
        ).pack(anchor="w", pady=(18, 4), fill="x")

        ttk.Label(
            card,
            text="La clave se genera sola y queda\nregistrada en la tabla de la derecha.",
            style="CardMuted.TLabel", justify="left",
        ).pack(anchor="w", pady=(6, 0))

        self._on_tier_change()

    def _build_table(self, parent: tk.Widget) -> None:
        right = tk.Frame(parent, bg=WHITE)
        right.pack(side="left", fill="both", expand=True)

        toolbar = tk.Frame(right, bg=WHITE)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, text="Licencias emitidas", style="Title.TLabel").pack(side="left")
        ttk.Button(toolbar, text="⟳ Actualizar", command=self._refresh).pack(side="right")

        columns = ("cliente", "tipo", "estado", "vence", "equipo", "clave")
        headers = {
            "cliente": "Cliente", "tipo": "Tipo", "estado": "Estado",
            "vence": "Vence", "equipo": "Equipo", "clave": "Clave",
        }
        # "vence" es más ancha que las demás a propósito: una licencia pendiente de
        # activar muestra "Sin activar (N día(s) desde que se active)", más largo
        # que una simple fecha.
        widths = {"cliente": 150, "tipo": 75, "estado": 75, "vence": 210, "equipo": 60, "clave": 170}

        wrap = tk.Frame(right, bg=SLATE_200, bd=1, relief="solid")
        wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(wrap, columns=columns, show="headings", selectmode="browse")
        for c in columns:
            self.tree.heading(c, text=headers[c])
            self.tree.column(c, width=widths[c], anchor="w")
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("revoked", foreground=RED)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._refresh_actions())

        actions = tk.Frame(right, bg=WHITE)
        actions.pack(fill="x", pady=(10, 0))
        self.btn_copy = ttk.Button(actions, text="📋 Copiar clave", command=self._on_copy, state="disabled")
        self.btn_copy.pack(side="left", padx=(0, 6))
        self.btn_detail = ttk.Button(actions, text="🔍 Ver detalle", command=self._on_detail, state="disabled")
        self.btn_detail.pack(side="left", padx=(0, 6))
        self.btn_renew = ttk.Button(actions, text="🗓️ Renovar…", command=self._on_renew, state="disabled")
        self.btn_renew.pack(side="left", padx=(0, 6))
        self.btn_revoke = ttk.Button(actions, text="🚫 Revocar", command=self._on_revoke, state="disabled")
        self.btn_revoke.pack(side="left", padx=(0, 6))
        self.btn_reactivate = ttk.Button(actions, text="✓ Reactivar", command=self._on_reactivate, state="disabled")
        self.btn_reactivate.pack(side="left", padx=(0, 6))
        self.btn_unbind = ttk.Button(actions, text="🔓 Liberar equipo", command=self._on_unbind, state="disabled")
        self.btn_unbind.pack(side="left", padx=(0, 6))
        self.btn_delete = ttk.Button(actions, text="🗑️ Eliminar", command=self._on_delete, state="disabled")
        self.btn_delete.pack(side="left")

    # --- Estado de la cuenta de servicio ------------------------------------

    def _check_service_account(self) -> None:
        if lic.service_account_ready():
            self._set_status(True, "Conectado")
            self._refresh()
            return
        self._set_status(False, "Falta la clave de Firebase")
        self._ask_for_service_account()

    def _ask_for_service_account(self) -> None:
        respuesta = messagebox.askyesno(
            "Falta la clave de administrador",
            "No se encontró serviceAccountKey.json en esta carpeta.\n\n"
            "Se descarga desde Firebase Console → Configuración del proyecto → "
            "Cuentas de servicio → Generar nueva clave privada.\n\n"
            "¿Abrir esa página ahora?",
            parent=self,
        )
        if respuesta:
            webbrowser.open(FIRESTORE_LINK.format("gestor-de-gym"))
        self._offer_file_picker()

    def _offer_file_picker(self) -> None:
        ruta = filedialog.askopenfilename(
            parent=self, title="Seleccione el archivo serviceAccountKey.json descargado",
            filetypes=[("Archivo JSON", "*.json")],
        )
        if not ruta:
            self._set_status(False, "Sin conexión: falta la clave")
            self.footer_label.configure(
                text="No podrás crear ni administrar licencias hasta guardar serviceAccountKey.json en vendor_tools."
            )
            return
        import shutil

        try:
            shutil.copy2(ruta, lic.SERVICE_ACCOUNT_PATH)
        except OSError as exc:
            messagebox.showerror("No se pudo copiar el archivo", str(exc), parent=self)
            self._offer_file_picker()
            return
        self._set_status(True, "Conectado")
        self._refresh()

    def _set_status(self, ok: bool, texto: str) -> None:
        self.status_dot.configure(fg=(GREEN if ok else "#f87171"))
        self.status_label.configure(text=texto)

    # --- Trabajo en segundo plano (no congela la ventana) -------------------

    def _run_async(self, fn: Callable[[], object], on_done: Callable[[object, Exception | None], None]) -> None:
        def trabajar() -> None:
            try:
                resultado = fn()
                self._events.put(("ok", (on_done, resultado)))
            except Exception as exc:  # noqa: BLE001 — se muestra en la interfaz
                self._events.put(("error", (on_done, exc)))

        self._set_busy(True)
        threading.Thread(target=trabajar, daemon=True).start()
        self.after(60, self._drain_events)

    def _drain_events(self) -> None:
        try:
            kind, payload = self._events.get_nowait()
        except queue.Empty:
            self.after(60, self._drain_events)
            return
        self._set_busy(False)
        on_done, valor = payload
        if kind == "ok":
            on_done(valor, None)
        else:
            on_done(None, valor)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.configure(cursor="watch" if busy else "")

    # --- Crear ---------------------------------------------------------------

    def _on_tier_change(self) -> None:
        es_prueba = self.tier_var.get() == lic.TIER_LABELS["TRIAL"]
        estado = "normal" if es_prueba else "disabled"
        self.entry_days.configure(state=estado)
        self.days_label.configure(foreground=(SLATE_900 if es_prueba else SLATE_400))

    def _tier_code(self) -> str:
        etiqueta = self.tier_var.get()
        for codigo, nombre in lic.TIER_LABELS.items():
            if nombre == etiqueta:
                return codigo
        return "MONTHLY"

    def _on_create(self) -> None:
        if self._busy:
            return
        cliente = self.entry_cliente.get().strip()
        if not cliente:
            messagebox.showwarning("Falta el cliente", "Escriba el nombre del cliente o gimnasio.", parent=self)
            return
        tier = self._tier_code()
        days = None
        if tier == "TRIAL":
            texto = self.entry_days.get().strip()
            try:
                days = int(texto) if texto else None
            except ValueError:
                messagebox.showwarning("Días inválidos", "Los días de prueba deben ser un número entero.", parent=self)
                return
        notas = self.entry_notas.get().strip()

        def trabajo():
            return lic.do_crear(cliente, tier, days, notas)

        def terminado(documento, error):
            if error is not None:
                self._show_error("No se pudo crear la licencia", error)
                return
            self._show_new_license(documento)
            self.entry_cliente.delete(0, "end")
            self.entry_notas.delete(0, "end")
            self._refresh()

        self._run_async(trabajo, terminado)

    def _show_new_license(self, documento: dict) -> None:
        top = tk.Toplevel(self)
        top.title("Licencia creada")
        top.configure(bg=WHITE)
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()

        pad = tk.Frame(top, bg=WHITE, padx=26, pady=22)
        pad.pack()
        tk.Label(
            pad, text=f"✓  Licencia creada para «{documento['customer_name']}»",
            bg=WHITE, fg=GREEN, font=self.font_bold,
        ).pack(anchor="w")
        tk.Label(
            pad, text=f"Tipo: {lic.TIER_LABELS[documento['tier']]}   ·   Vence: {lic.vigencia_text(documento)}",
            bg=WHITE, fg=SLATE_600, font=self.font_small,
        ).pack(anchor="w", pady=(2, 14))

        box = tk.Entry(pad, font=self.font_mono, justify="center", width=28, relief="solid", bd=1)
        box.insert(0, documento["license_key"])
        box.configure(state="readonly", readonlybackground=SLATE_50, fg=INDIGO_DARK)
        box.pack(ipady=8)

        def copiar():
            self.clipboard_clear()
            self.clipboard_append(documento["license_key"])
            btn_copiar.configure(text="✓ Copiada")
            top.after(1500, lambda: btn_copiar.configure(text="📋 Copiar clave"))

        btn_copiar = ttk.Button(pad, text="📋 Copiar clave", style="Primary.TButton", command=copiar)
        btn_copiar.pack(fill="x", pady=(12, 4))
        ttk.Button(pad, text="Cerrar", command=top.destroy).pack(fill="x")

        tk.Label(
            pad, text="Entregue esta clave al cliente para que la active dentro del programa.",
            bg=WHITE, fg=SLATE_600, font=self.font_small, wraplength=320, justify="left",
        ).pack(anchor="w", pady=(14, 0))

    # --- Tabla y acciones sobre la selección ---------------------------------

    def _refresh(self) -> None:
        if self._busy:
            return

        def terminado(filas, error):
            if error is not None:
                self._show_error("No se pudo leer la lista de licencias", error)
                self._set_status(False, "Sin conexión")
                return
            self._set_status(True, "Conectado")
            self._rows = filas
            self._populate_table(filas)
            self.footer_label.configure(
                text=f"{len(filas)} licencia(s) · actualizado {datetime.now().strftime('%H:%M:%S')}"
            )

        self._run_async(lic.do_listar, terminado)

    def _populate_table(self, filas: list[dict]) -> None:
        self.tree.delete(*self.tree.get_children())
        for d in filas:
            tags = ("revoked",) if d.get("status") == "REVOKED" else ()
            self.tree.insert(
                "", "end", iid=d["license_key"], tags=tags,
                values=(
                    d.get("customer_name", ""),
                    lic.TIER_LABELS.get(d.get("tier"), d.get("tier")),
                    "Activa" if d.get("status") == "ACTIVE" else "Revocada",
                    lic.vigencia_text(d),
                    "sí" if d.get("device_id_hash") else "no",
                    d["license_key"],
                ),
            )
        self._refresh_actions()

    def _selected(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        clave = sel[0]
        return next((d for d in self._rows if d["license_key"] == clave), None)

    def _refresh_actions(self) -> None:
        d = self._selected()
        for boton in (
            self.btn_copy, self.btn_detail, self.btn_renew, self.btn_revoke,
            self.btn_reactivate, self.btn_unbind, self.btn_delete,
        ):
            boton.configure(state="disabled")
        if d is None:
            return
        self.btn_copy.configure(state="normal")
        self.btn_detail.configure(state="normal")
        if d.get("status") == "ACTIVE":
            self.btn_revoke.configure(state="normal")
            # También sirve para PERPETUAL: renovar ahora permite cambiar el tipo
            # de licencia de paso, incluyendo convertir una perpetua en una con
            # vencimiento (o al revés).
            self.btn_renew.configure(state="normal")
        else:
            self.btn_reactivate.configure(state="normal")
            self.btn_delete.configure(state="normal")
        if d.get("device_id_hash"):
            self.btn_unbind.configure(state="normal")

    def _on_copy(self) -> None:
        d = self._selected()
        if d is None:
            return
        self.clipboard_clear()
        self.clipboard_append(d["license_key"])
        self.footer_label.configure(text=f"Clave {d['license_key']} copiada al portapapeles.")

    def _on_detail(self) -> None:
        d = self._selected()
        if d is None:
            return
        top = tk.Toplevel(self)
        top.title(f"Detalle — {d['license_key']}")
        top.configure(bg=WHITE)
        top.transient(self)
        pad = tk.Frame(top, bg=WHITE, padx=20, pady=16)
        pad.pack()
        campos = (
            ("Clave", d["license_key"]),
            ("Cliente", d.get("customer_name", "")),
            ("Tipo", lic.TIER_LABELS.get(d.get("tier"), d.get("tier"))),
            ("Estado", "Activa" if d.get("status") == "ACTIVE" else "Revocada"),
            ("Emitida", fecha(d.get("issued_at"))),
            ("Vence", lic.vigencia_text(d)),
            ("Activada", fecha(d.get("activated_at"))),
            ("Equipo (huella)", (d.get("device_id_hash") or "—")[:16] + ("…" if d.get("device_id_hash") else "")),
            ("Notas", d.get("notes") or "—"),
        )
        for i, (k, v) in enumerate(campos):
            tk.Label(pad, text=k, bg=WHITE, fg=SLATE_600, font=self.font_small).grid(row=i, column=0, sticky="w", pady=2)
            tk.Label(pad, text=str(v), bg=WHITE, fg=SLATE_900, font=self.font_bold).grid(
                row=i, column=1, sticky="w", padx=(14, 0), pady=2
            )
        ttk.Button(pad, text="Cerrar", command=top.destroy).grid(row=len(campos), column=0, columnspan=2, pady=(14, 0), sticky="ew")

    def _on_renew(self) -> None:
        d = self._selected()
        if d is None:
            return
        top = tk.Toplevel(self)
        top.title("Renovar licencia")
        top.configure(bg=WHITE)
        top.transient(self)
        top.grab_set()
        pad = tk.Frame(top, bg=WHITE, padx=20, pady=16)
        pad.pack()
        tk.Label(pad, text=f"Renovar {d['license_key']}", bg=WHITE, fg=SLATE_900, font=self.font_bold).pack(anchor="w")
        tk.Label(
            pad,
            text=f"Tipo actual: {lic.TIER_LABELS.get(d.get('tier'), d.get('tier'))}   ·   "
                 f"Vence actualmente: {lic.vigencia_text(d)}",
            bg=WHITE, fg=SLATE_600, font=self.font_small,
        ).pack(anchor="w", pady=(2, 12))

        tk.Label(pad, text="Tipo de licencia", bg=WHITE, font=self.font_small).pack(anchor="w", pady=(0, 2))
        tier_var = tk.StringVar(value=lic.TIER_LABELS.get(d.get("tier"), ""))
        combo_tier = ttk.Combobox(
            pad, textvariable=tier_var, state="readonly", width=24,
            values=[lic.TIER_LABELS[t] for t in TIER_ORDER],
        )
        combo_tier.pack(anchor="w", pady=(0, 12))

        fila = tk.Frame(pad, bg=WHITE)
        fila.pack(anchor="w")
        label_meses = tk.Label(fila, text="Meses", bg=WHITE, font=self.font_small)
        label_meses.grid(row=0, column=0, padx=(0, 6))
        meses = tk.Entry(fila, width=6, font=self.font_body, relief="solid", bd=1)
        meses.insert(0, "1")
        meses.grid(row=0, column=1, padx=(0, 16))
        label_anos = tk.Label(fila, text="Años", bg=WHITE, font=self.font_small)
        label_anos.grid(row=0, column=2, padx=(0, 6))
        anos = tk.Entry(fila, width=6, font=self.font_body, relief="solid", bd=1)
        anos.insert(0, "0")
        anos.grid(row=0, column=3)

        nota = tk.Label(
            pad, text="", bg=WHITE, fg=SLATE_600, font=self.font_small, wraplength=280, justify="left",
        )
        nota.pack(anchor="w", pady=(8, 0))

        def tier_codigo_seleccionado() -> str:
            etiqueta = tier_var.get()
            for codigo, nombre in lic.TIER_LABELS.items():
                if nombre == etiqueta:
                    return codigo
            return d.get("tier") or "MONTHLY"

        def on_tier_change(_evt=None) -> None:
            es_perpetua = tier_codigo_seleccionado() == "PERPETUAL"
            estado = "disabled" if es_perpetua else "normal"
            meses.configure(state=estado)
            anos.configure(state=estado)
            label_meses.configure(fg=(SLATE_400 if es_perpetua else SLATE_900))
            label_anos.configure(fg=(SLATE_400 if es_perpetua else SLATE_900))
            nota.configure(
                text="Una licencia perpetua no vence: no hace falta indicar meses ni años."
                if es_perpetua else ""
            )

        combo_tier.bind("<<ComboboxSelected>>", on_tier_change)
        on_tier_change()

        def confirmar():
            tier_codigo = tier_codigo_seleccionado()
            m = a = 0
            if tier_codigo != "PERPETUAL":
                try:
                    m = int(meses.get() or 0)
                    a = int(anos.get() or 0)
                except ValueError:
                    messagebox.showwarning("Valor inválido", "Meses y años deben ser números enteros.", parent=top)
                    return
                if m <= 0 and a <= 0:
                    messagebox.showwarning(
                        "Falta la duración", "Indique al menos un mes o un año a extender.", parent=top
                    )
                    return
            # Solo se manda el tipo si de verdad cambió: así una renovación normal
            # (sin tocar el combo) se comporta exactamente igual que antes.
            tier_a_enviar = tier_codigo if tier_codigo != d.get("tier") else None
            top.destroy()

            def terminado(resultado, error):
                if error is not None:
                    self._show_error("No se pudo renovar la licencia", error)
                    return
                self.footer_label.configure(
                    text=f"{d['license_key']} renovada: {lic.TIER_LABELS.get(resultado['tier'], resultado['tier'])}, "
                         f"vence {lic.vigencia_text(resultado)}."
                )
                self._refresh()

            self._run_async(lambda: lic.do_renovar(d["license_key"], m, a, tier_a_enviar), terminado)

        ttk.Button(pad, text="Renovar", style="Primary.TButton", command=confirmar).pack(fill="x", pady=(16, 4))
        ttk.Button(pad, text="Cancelar", command=top.destroy).pack(fill="x")

    def _on_revoke(self) -> None:
        d = self._selected()
        if d is None:
            return
        if not messagebox.askyesno(
            "Revocar licencia",
            f"¿Revocar la licencia de «{d.get('customer_name', '')}»?\n\n"
            "El programa del cliente dejará de funcionar en cuanto vuelva a conectarse.",
            parent=self,
        ):
            return

        def terminado(_, error):
            if error is not None:
                self._show_error("No se pudo revocar la licencia", error)
                return
            self.footer_label.configure(text=f"{d['license_key']} revocada.")
            self._refresh()

        self._run_async(lambda: lic.do_revocar(d["license_key"]), terminado)

    def _on_reactivate(self) -> None:
        d = self._selected()
        if d is None:
            return

        def terminado(_, error):
            if error is not None:
                self._show_error("No se pudo reactivar la licencia", error)
                return
            self.footer_label.configure(text=f"{d['license_key']} reactivada.")
            self._refresh()

        self._run_async(lambda: lic.do_reactivar(d["license_key"]), terminado)

    def _on_unbind(self) -> None:
        d = self._selected()
        if d is None:
            return
        if not messagebox.askyesno(
            "Liberar equipo",
            f"¿Liberar el equipo asociado a la licencia de «{d.get('customer_name', '')}»?\n\n"
            "Podrá activarse de nuevo en cualquier equipo.",
            parent=self,
        ):
            return

        def terminado(_, error):
            if error is not None:
                self._show_error("No se pudo liberar el equipo", error)
                return
            self.footer_label.configure(text=f"Equipo liberado para {d['license_key']}.")
            self._refresh()

        self._run_async(lambda: lic.do_liberar_equipo(d["license_key"]), terminado)

    def _on_delete(self) -> None:
        d = self._selected()
        if d is None:
            return
        if not messagebox.askyesno(
            "Eliminar licencia",
            f"¿Eliminar PERMANENTEMENTE la licencia revocada de «{d.get('customer_name', '')}»?\n\n"
            "Desaparece del registro para siempre — esto no se puede deshacer.",
            icon="warning",
            parent=self,
        ):
            return

        clave = d["license_key"]

        def terminado(_, error):
            if error is not None:
                self._show_error("No se pudo eliminar la licencia", error)
                return
            self.footer_label.configure(text=f"{clave} eliminada del registro.")
            self._refresh()

        self._run_async(lambda: lic.do_eliminar(clave), terminado)

    # --- Errores ---------------------------------------------------------------

    def _show_error(self, titulo: str, error: Exception) -> None:
        if isinstance(error, lic.LicenseAdminError):
            messagebox.showerror(titulo, str(error), parent=self)
        else:
            messagebox.showerror(
                titulo, f"{error}\n\nDetalle técnico:\n{traceback.format_exc()}", parent=self
            )


def main() -> int:
    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
