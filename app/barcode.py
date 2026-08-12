"""Códigos de barras Code 128B para los recibos.

Se escribe aquí en vez de usar una librería porque el programa tiene que funcionar sin
internet y sin instalar nada: Code 128 son cien líneas de tabla y una suma de control,
y una dependencia más significaría otros megabytes en el instalador.

## Por qué Code 128 y no Code 39

Code 39 es más simple pero ocupa casi el doble de ancho por carácter. En un rollo de
58 mm el código quedaría tan estrecho de módulo que muchos lectores fallarían. Code 128
es además lo que espera cualquier lector de comercio.

## Qué se codifica

La referencia del recibo tal cual se imprime: `V000009` para una venta, `I000026` para
una inscripción. La letra distingue el tipo y evita que el número 9 de una venta se
confunda con el 9 de una inscripción.

El resultado es un SVG: se imprime nítido a cualquier resolución, que es justo lo que
necesita un lector, y no hace falta generar imágenes ni guardarlas en disco.
"""

from __future__ import annotations

import re

# Patrón de cada valor (0..106): anchos alternados empezando por barra.
# "212222" = barra 2, espacio 1, barra 2, espacio 2, barra 2, espacio 2.
# Es la tabla estándar de Code 128; la última entrada es el patrón de parada.
_PATTERNS = (
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312",
    "132212", "221213", "221312", "231212", "112232", "122132", "122231", "113222",
    "123122", "123221", "223211", "221132", "221231", "213212", "223112", "312131",
    "311222", "321122", "321221", "312212", "322112", "322211", "212123", "212321",
    "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121",
    "313121", "211331", "231131", "213113", "213311", "213131", "311123", "311321",
    "331121", "312113", "312311", "332111", "314111", "221411", "431111", "111224",
    "111422", "121124", "121421", "141122", "141221", "112214", "112412", "122114",
    "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112",
    "421211", "212141", "214121", "412121", "111143", "111341", "131141", "114113",
    "114311", "411113", "411311", "113141", "114131", "311141", "411131", "211412",
    "211214", "211232", "2331112",
)

START_B = 104
STOP = 106

# Referencias válidas: una letra de tipo y dígitos. Se acota a propósito para que un
# lector que lea cualquier otro código de un envase no acabe consultando la base.
REFERENCE_RE = re.compile(r"^([VI])(\d{1,10})$")


class BarcodeError(ValueError):
    """El texto no se puede representar en Code 128B."""


def encode(text: str) -> str:
    """Devuelve el código como cadena de módulos: '1' barra, '0' espacio.

    Code 128B admite los caracteres ASCII imprimibles (espacio a `~`). El valor de cada
    uno es su posición a partir del espacio.
    """
    if not text:
        raise BarcodeError("No hay nada que codificar.")

    valores = []
    for caracter in text:
        codigo = ord(caracter)
        if not 32 <= codigo <= 126:
            raise BarcodeError(f"El carácter «{caracter}» no cabe en un Code 128B.")
        valores.append(codigo - 32)

    # Suma de control: arranque + cada valor por su posición (empezando en 1), módulo 103.
    control = START_B
    for posicion, valor in enumerate(valores, start=1):
        control += posicion * valor
    control %= 103

    secuencia = [START_B, *valores, control, STOP]

    modulos = []
    for valor in secuencia:
        patron = _PATTERNS[valor]
        # Los anchos alternan barra/espacio siempre empezando por barra.
        for indice, ancho in enumerate(patron):
            modulos.append(("1" if indice % 2 == 0 else "0") * int(ancho))
    return "".join(modulos)


def svg(text: str, *, module_width: float = 0.33, height: float = 12.0,
        quiet: int = 10, show_text: bool = True) -> str:
    """Código de barras como SVG, con medidas en milímetros.

    `module_width` es el ancho del módulo más estrecho. 0,33 mm es el mínimo cómodo para
    un lector de mano barato; por debajo de 0,25 mm empiezan las lecturas fallidas.

    `quiet` son los módulos en blanco a cada lado. Sin esa zona muerta el lector no
    encuentra dónde empieza el código, y es el olvido que más veces deja un código
    impreso pero inservible.
    """
    modulos = encode(text)
    total = len(modulos) + quiet * 2
    ancho_mm = total * module_width
    alto_texto = 3.2 if show_text else 0
    alto_mm = height + alto_texto

    barras = []
    inicio = None
    for indice, modulo in enumerate(modulos):
        if modulo == "1" and inicio is None:
            inicio = indice
        elif modulo == "0" and inicio is not None:
            barras.append((inicio, indice - inicio))
            inicio = None
    if inicio is not None:
        barras.append((inicio, len(modulos) - inicio))

    piezas = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho_mm:.2f}mm" '
        f'height="{alto_mm:.2f}mm" viewBox="0 0 {total} {alto_mm / module_width:.2f}" '
        f'role="img" aria-label="Código {text}">',
        f'<rect width="{total}" height="{alto_mm / module_width:.2f}" fill="#fff"/>',
    ]
    altura_barras = height / module_width
    for x, ancho in barras:
        piezas.append(
            f'<rect x="{x + quiet}" y="0" width="{ancho}" height="{altura_barras:.2f}" fill="#000"/>'
        )

    if show_text:
        piezas.append(
            f'<text x="{total / 2:.2f}" y="{(alto_mm / module_width) - 0.8:.2f}" '
            f'text-anchor="middle" font-family="monospace" '
            f'font-size="{2.6 / module_width:.2f}" fill="#000" '
            f'letter-spacing="{0.4 / module_width:.2f}">{text}</text>'
        )

    piezas.append("</svg>")
    return "".join(piezas)


# --- Referencias de recibo ----------------------------------------------------


def reference(kind: str, doc_id: int) -> str:
    """Referencia impresa en el recibo: 'V000009' para venta, 'I000026' para inscripción."""
    letra = "V" if kind == "SALE" else "I"
    return f"{letra}{doc_id:06d}"


def parse_reference(code: str) -> tuple[str, int] | None:
    """Interpreta lo que leyó el lector. None si no es una referencia de este programa.

    Se aceptan minúsculas y espacios sobrantes: algunos lectores añaden un salto de
    línea o cambian la mayúscula según su configuración de teclado, y rechazar el código
    por eso obligaría a teclearlo a mano justo cuando hay un cliente esperando.
    """
    limpio = (code or "").strip().upper().replace("-", "").replace(" ", "")
    match = REFERENCE_RE.match(limpio)
    if not match:
        return None
    letra, numero = match.groups()
    return ("SALE" if letra == "V" else "MEMBERSHIP"), int(numero)
