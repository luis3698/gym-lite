# Instalación de GymManager Lite

Guía para dejar el programa funcionando en un PC con Windows.

---

## Instalación rápida (recomendada)

### Paso 1 — Instalar Python (solo la primera vez)

Si el equipo ya tiene Python 3.9 o superior, salte al paso 2.

1. Descargue Python desde <https://www.python.org/downloads/>
2. Ejecute el instalador.
3. **Marque la casilla «Add Python to PATH»** en la primera pantalla. Es el error
   más común: sin esa casilla, el instalador del programa no encontrará Python.
4. Pulse «Install Now» y espere a que termine.

### Paso 2 — Instalar GymManager Lite

Doble clic en **`instalar.bat`**.

El instalador hace todo solo:

1. Comprueba que Python esté instalado y sea una versión compatible.
2. Crea un entorno aislado (`.venv`) dentro de la carpeta del programa.
3. Descarga e instala las dependencias.
4. Crea la base de datos con los datos iniciales.
5. Deja un acceso directo **«GymManager Lite»** en el escritorio.

Tarda alrededor de un minuto. Al final pregunta si quiere abrir el programa.

> Windows puede mostrar un aviso de SmartScreen porque el archivo no está firmado
> digitalmente. Pulse **«Más información» → «Ejecutar de todas formas»**.

### Paso 3 — Entrar

Doble clic en **«GymManager Lite»** del escritorio. Se abre el navegador solo.

| Campo | Valor |
|---|---|
| Usuario | `Admin` |
| Contraseña | `Admin.123` |

> ⚠️ Cambie esa contraseña la primera vez, desde **Mi cuenta → Cambiar contraseña**.

---

## Uso diario

- **Abrir:** doble clic en «GymManager Lite» (escritorio) o en `iniciar.bat`.
- Se abre **una ventana negra de consola**: es el servidor del programa.
  **Déjela abierta** mientras trabaja.
- **Cerrar:** cierre esa ventana negra o pulse `Ctrl+C` en ella.

> Si cierra la ventana negra, la aplicación deja de responder y el navegador dirá
> que no puede conectarse. Es normal: vuelva a abrirla con el acceso directo.

---

## Instalación manual (sin el .bat)

Si prefiere hacerlo a mano, o está en macOS o Linux:

```bash
cd "gym lite"
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
python run.py
```

---

## Llevar el programa a otro PC

1. Ejecute **`crear-paquete.bat`**: genera un `.zip` con todo lo necesario,
   **sin incluir sus datos** (clientes, ventas y fotos se quedan en este equipo).
2. Copie el `.zip` al otro PC y descomprímalo.
3. En el otro PC, ejecute `instalar.bat`.

Si además quiere llevarse los datos, copie la carpeta `instance` completa dentro de
la carpeta del programa en el equipo de destino, **después** de instalar.

---

## Dónde quedan los datos

Todo vive en la carpeta **`instance`**, dentro de la carpeta del programa:

| Archivo | Contenido |
|---|---|
| `instance/gym.db` | Base de datos: clientes, inscripciones, ventas, usuarios, auditoría. |
| `instance/uploads/` | Fotos de clientes, personal y productos. |
| `instance/secret_key` | Clave con la que se firman las sesiones. |

### Copia de seguridad

Copie la carpeta `instance` completa a una memoria USB o a la nube. Para restaurar,
reemplace esa carpeta y vuelva a abrir el programa.

> Haga la copia con el programa **cerrado**, para no copiar la base a medio escribir.

---

## Desinstalar

Doble clic en **`desinstalar.bat`**. Quita el entorno y el acceso directo, y pregunta
aparte si quiere borrar también los datos (por defecto **no** los borra).

Para eliminarlo todo a mano, basta con borrar la carpeta del programa: no escribe
nada en el registro de Windows ni en otras carpetas del sistema.

---

## Problemas frecuentes

| Síntoma | Solución |
|---|---|
| «No se encontró Python en este equipo» | Reinstale Python marcando **«Add Python to PATH»**. |
| «El programa no está instalado todavía» | Ejecute primero `instalar.bat`. |
| El navegador dice que no puede conectarse | La ventana negra del servidor está cerrada. Ábrala con el acceso directo. |
| «El puerto 5000 ya está en uso» | Otro programa lo ocupa. Abra la carpeta y ejecute `iniciar.bat --port 5001`, luego entre en `http://localhost:5001`. |
| Falla la instalación de dependencias | Sin internet o con proxy. Compruebe la conexión e intente de nuevo. |
| La cámara no funciona al tomar la foto | Debe permitir el acceso a la cámara en el navegador. Solo funciona en `localhost` o con HTTPS: es una restricción del navegador. |
| Olvidé la contraseña de administrador | No hay recuperación por correo. Cierre el programa, borre `instance/gym.db` y vuelva a abrirlo: se recrea con `Admin` / `Admin.123`, pero **se pierden todos los datos**. |

---

## Requisitos

- Windows 10 u 11 (los `.bat`). En macOS y Linux, use la instalación manual.
- Python 3.9 o superior.
- Conexión a internet **solo durante la instalación** (para descargar Flask).
- Navegador moderno: Chrome, Edge o Firefox.
- Cámara web, únicamente si quiere tomar la foto de los clientes desde el programa.

Espacio en disco: unos 30 MB, más lo que ocupen las fotos.
