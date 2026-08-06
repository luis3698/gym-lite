# Instalación de GymManager Lite

Guía para dejar el programa funcionando en un PC con Windows.

---

## Instalación

### Paso 1 — Ejecutar el instalador

Doble clic en **`GymManagerLite-Setup.exe`**.

Es un único archivo: **no necesita Python, ni internet, ni permisos de administrador**.

> Windows puede mostrar un aviso de SmartScreen porque el archivo no está firmado
> digitalmente. Pulse **«Más información» → «Ejecutar de todas formas»**.

### Paso 2 — Seguir el asistente

| Pantalla | Qué hacer |
|---|---|
| Bienvenida | Pulse «Siguiente». |
| Acuerdo de licencia | Léalo y marque **«Acepto los términos»**. Hasta entonces «Siguiente» está deshabilitado. |
| Carpeta de destino | Acepte la ruta propuesta o pulse «Examinar…». El asistente comprueba el espacio libre. |
| Opciones | Elija los accesos directos (escritorio y menú Inicio) y si abrir el programa al terminar. |
| Todo listo | Revise el resumen y pulse **«Instalar»**. |
| Instalando | Barra de progreso con el nombre de cada archivo que se está copiando. Tarda unos segundos. |
| Completada | Muestra el usuario y la contraseña. Pulse «Finalizar». |

La ruta propuesta por defecto es `C:\Users\<usuario>\AppData\Local\Programs\GymManager Lite`.
Puede elegir otra, incluida una unidad externa.

### Paso 3 — Entrar

Doble clic en **«GymManager Lite»** del escritorio. Se abre una ventana de control
pequeña y, a continuación, el navegador.

| Campo | Valor |
|---|---|
| Usuario | `Admin` |
| Contraseña | `Admin.123` |

> ⚠️ Cambie esa contraseña la primera vez, desde **Mi cuenta → Cambiar contraseña**.

### Paso 4 — Configurar las tarifas

La instalación deja la base de datos **limpia**: solo existe el usuario administrador.
Antes de registrar la primera inscripción, entre en **Crear tarifas** y fije los
precios por duración y el valor del mes adicional. Sin tarifas, la aplicación avisa de
que faltan al intentar registrar una mensualidad.

Los productos, los servicios complementarios y los clientes se dan de alta desde sus
respectivos módulos.

---

## Uso diario

- **Abrir:** doble clic en «GymManager Lite» (escritorio o menú Inicio).
- Aparece una **ventana de control** con la dirección del programa y dos botones:
  - **Abrir en el navegador** — vuelve a abrir la pestaña si la cerró.
  - **Detener y salir** — cierra el programa.
- **Deje esa ventana abierta** mientras trabaja: es el programa en ejecución. Puede
  minimizarla sin problema.

> Si la cierra, el navegador dirá que no puede conectarse. Es normal: vuelva a abrir el
> programa desde el acceso directo.

Si el puerto 5000 está ocupado por otro programa, la aplicación busca automáticamente
el siguiente libre (hasta el 5010) y lo indica en la ventana de control.

---

## Dónde quedan los datos

Todo vive en la subcarpeta **`data`** de la carpeta de instalación:

| Archivo | Contenido |
|---|---|
| `data/gym.db` | Base de datos: clientes, inscripciones, ventas, usuarios, auditoría. |
| `data/uploads/` | Fotos de clientes, personal y productos. |
| `data/secret_key` | Clave con la que se firman las sesiones. |

> Si instala en una carpeta protegida por Windows (por ejemplo «Archivos de programa»),
> los datos se guardan en `%LOCALAPPDATA%\GymManager Lite\data`. La ruta exacta siempre
> aparece en la ventana de control del programa.

### Copia de seguridad

Copie la carpeta `data` completa a una memoria USB o a la nube. Para restaurar,
reemplace esa carpeta y vuelva a abrir el programa.

> Haga la copia con el programa **cerrado**, para no copiar la base a medio escribir.

### Llevar el programa a otro PC

Copie `GymManagerLite-Setup.exe` al otro equipo y ejecútelo: instalará una base limpia.
Si además quiere llevarse los datos, copie encima la carpeta `data` **después** de
instalar, con el programa cerrado.

---

## Reinstalar sobre una instalación existente

Si vuelve a ejecutar el instalador sobre la misma carpeta, el asistente detecta los
datos anteriores y pregunta qué hacer:

- **Empezar con una base de datos limpia** (opción por defecto): borra los datos.
- **Conservar los datos existentes**: actualiza solo el programa.

---

## Desinstalar

Cualquiera de estas dos vías:

- **Configuración de Windows → Aplicaciones → Aplicaciones instaladas →
  GymManager Lite → Desinstalar.**
- Doble clic en **«Desinstalar GymManager Lite.exe»** dentro de la carpeta del programa.

El desinstalador quita los archivos, los accesos directos y la entrada de Windows.
Los datos del gimnasio **se conservan** salvo que marque expresamente la casilla para
borrarlos, que pide una confirmación adicional.

---

## Problemas frecuentes

| Síntoma | Solución |
|---|---|
| SmartScreen bloquea el instalador | «Más información» → «Ejecutar de todas formas». El archivo no está firmado digitalmente. |
| «No se pudo escribir …» durante la instalación | El programa estaba abierto. Ciérrelo desde su ventana de control y reinstale. |
| «No hay espacio suficiente en la unidad» | Elija otra carpeta de destino o libere espacio. Hacen falta unos 45 MB. |
| El navegador dice que no puede conectarse | La ventana de control está cerrada. Abra el programa con el acceso directo. |
| No aparece el acceso directo en el escritorio | Vuelva a ejecutar el instalador y marque la casilla correspondiente, o cree el acceso a mano al `.exe`. |
| «No hay tarifa configurada para esta duración» | Es lo esperado en una instalación nueva: fije las tarifas en «Crear tarifas». |
| La cámara no funciona al tomar la foto | Debe permitir el acceso a la cámara en el navegador. Solo funciona en `localhost` o con HTTPS: es una restricción del navegador. |
| Olvidé la contraseña de administrador | No hay recuperación por correo. Cierre el programa, borre `data\gym.db` y vuelva a abrirlo: se recrea con `Admin` / `Admin.123`, pero **se pierden todos los datos**. |

Si algo falla al arrancar, el detalle técnico queda en `data\error.log`.

---

## Requisitos

- Windows 10 u 11 (64 bits).
- Navegador moderno: Chrome, Edge o Firefox.
- Cámara web, únicamente si quiere tomar la foto de los clientes desde el programa.
- Espacio en disco: unos 45 MB, más lo que ocupen las fotos.

No requiere Python, ni conexión a internet, ni permisos de administrador.

---

## Instalación desde el código fuente

Para desarrollo, o en macOS y Linux:

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

En ese modo los datos van a la carpeta `instance/` del proyecto.

### Regenerar el instalador

```bash
py -3 installer/build.py
```

Compila la aplicación, el desinstalador y el asistente, y deja el resultado en
`dist\GymManagerLite-Setup.exe`.
