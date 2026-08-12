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
pequeña y, a continuación, el navegador con **dos pestañas**: el programa y el
**kiosco de acceso** (la pantalla con la cámara para la entrada del gimnasio).

| Campo | Valor |
|---|---|
| Usuario | `Admin` |
| Contraseña | `Admin.123` |

> ⚠️ Cambie esa contraseña la primera vez, desde **Mi cuenta → Cambiar contraseña**.

### Paso 4 — Cargar los socios que ya tenía

Si el gimnasio ya funcionaba antes, entre en **Administración → Migración de datos**.
Hay dos caminos:

- **Importar un listado completo.** Descargue la plantilla, rellénela en Excel con todos
  sus socios y súbala. Antes de guardar nada verá fila por fila lo que se va a hacer y
  qué está mal (documentos repetidos, fechas inválidas, gente que ya existe), para poder
  corregirlo. Se guardan todas de una vez: nunca queda una importación a medias.
- **Registrar un socio.** Un formulario con todos los campos, para casos sueltos.

> Estas inscripciones **no generan recibo** y **no cuentan como ingreso**: ese dinero se
> cobró antes de usar el programa, y contarlo falsearía el informe de ventas. Por lo
> demás funcionan igual que cualquier otra: vencen, se renuevan y dan acceso por el kiosco.

### Paso 5 — Configurar las tarifas

> Las tarifas se cobran por **cantidad**: si fija «1 día» en $10.000, un cliente que
> quiera pagar 5 días paga $50.000. Lo mismo con semanas y quincenas. Las mensualidades
> mantienen su descuento: el primer mes a la tarifa mensual y los siguientes a la de
> «mes adicional». El total se ve en pantalla mientras se arma la inscripción.

La instalación deja la base de datos **limpia**: solo existe el usuario administrador.
Antes de registrar la primera inscripción, entre en **Crear tarifas** y fije los
precios por duración y el valor del mes adicional. Sin tarifas, la aplicación avisa de
que faltan al intentar registrar una mensualidad.

Los productos, los servicios complementarios y los clientes se dan de alta desde sus
respectivos módulos.

---

## Copias de seguridad

Todo el gimnasio vive en un único archivo. **Esto es lo primero que debería configurar.**

En **Administración → Copias de seguridad** elija cada cuánto se hace la copia (por
defecto, una al día al abrir el programa) y cuántas conservar. Las más antiguas se
borran solas para no llenar el disco. También puede crear una a mano cuando quiera.

### Si pierde la base de datos

En esa misma pantalla, **suba el archivo `.db`** que tenga guardado y pulse Restaurar.
Antes de sustituir nada, el programa:

1. Comprueba que el archivo es realmente una copia de GymManager Lite.
2. Guarda una copia del estado actual, por si la restauración era un error.
3. Le pide su contraseña.

Después tendrá que cerrar sesión y volver a entrar.

> **Importante.** Las copias se guardan en la carpeta `data\backups` del propio equipo.
> Eso no protege de que ese disco falle: **copie esa carpeta de vez en cuando a un USB o
> a la nube**. Y recuerde que las fotos de clientes y las imágenes de productos son
> archivos aparte, en `data\uploads`: si va a mudar el programa a otro equipo, lleve
> también esa carpeta.

---

## Recibos en papel térmico

Los recibos salen en formato de **tiquete de caja**, para impresora térmica de 58 u
80 mm. Al pulsar «Imprimir» se abre el diálogo del navegador, donde puede elegir la
impresora térmica o guardar en PDF.

En **Administración → Datos del negocio** se rellena lo que se imprime en cada recibo:
nombre del establecimiento, NIT, dirección, teléfonos, correo, redes, nota tributaria y
el pie con las leyendas legales. La pantalla muestra **una vista previa a tamaño real**:
lo que ve ahí es lo que sale por la impresora.

Viene con un ejemplo relleno para que se vea qué va en cada sitio. Sustitúyalo por los
datos de su gimnasio.

> El programa **imprime lo que usted escriba**: no valida el NIT ni asigna numeración
> fiscal. Si su gimnasio factura electrónicamente o tiene resolución de la DIAN, ponga
> en la nota tributaria y en el pie los textos que le correspondan.

---

## Devoluciones

Cada recibo se imprime con un **código de barras**. Para devolver, entre en
**Devoluciones**, pase el lector por el código —o escriba la referencia, que va impresa
debajo— y aparecerá la compra con:

- lo que se cobró,
- lo que ya se ha devuelto,
- y el **saldo devolvible** que queda.

Escriba cuánto se devuelve. Puede ser **todo o una parte**, y se puede devolver varias
veces hasta agotar el saldo. Mientras escribe, el programa avisa si el importe se pasa y
no deja registrarlo. El motivo es obligatorio: es lo que explica después por qué la caja
no cuadra con lo vendido.

> **Qué no hace.** Devolver el dinero de una inscripción **no la cancela**: si además
> quiere que el socio deje de tener acceso, cancélela desde su ficha. Son dos cosas
> distintas a propósito, porque una devolución parcial no debería quitarle el acceso.

Cada devolución queda guardada con su importe, motivo, forma de pago, fecha y **quién la
autorizó**. El recibo original nunca se modifica ni se borra. En
**Devoluciones → Ver histórico** están todas, con filtros por tipo, forma de pago, fecha
y motivo.

### En ventas e ingresos

Las devoluciones aparecen en el informe **en negativo**, así que el total que ve es el
**neto**: lo cobrado menos lo devuelto. La tarjeta de arriba muestra las dos cifras, y el
CSV exporta el desglose completo y el total neto.

### Desactivar los códigos de barras

En **Datos del negocio → Código de barras en los recibos** se puede apagar, **escribiendo
su contraseña**. Los recibos ya impresos siguen funcionando: solo dejan de imprimirse los
nuevos, y se pueden seguir leyendo para devoluciones.

---

## Pausar una inscripción

Cuando un socio se va de viaje, se lesiona o quiere congelar su mensualidad, entre en
**Inscripción de gym → el cliente → «⏸️ Pausar inscripción»**.

- Se guardan **los días que le quedaban**.
- Mientras esté en pausa **no cuenta como vigente** y el kiosco no le dará acceso, pero
  tampoco aparece como moroso en el panel: no es lo mismo deber que estar congelado.
- Al pulsar **«▶️ Reanudar»**, el vencimiento se recalcula desde ese día con los días
  guardados. Si le quedaban 12 días y vuelve tres meses después, sigue teniendo 12.

En el tablero de inscripciones hay un filtro **«Solo inscripciones en pausa»** para
verlos de un vistazo.

---

## Ficha deportiva e índices corporales

En la ficha de cada cliente (**Registro de usuarios → el cliente**) puede anotar altura,
peso, tipo de sangre, objetivo, alergias y **once perímetros corporales**: cuello,
hombros, pecho, bíceps relajado y en tensión, antebrazo, cintura, cadera, muslo superior
y medio, y pantorrilla. Todo es opcional.

Con esos datos el programa calcula automáticamente:

| Índice | Qué necesita |
|---|---|
| Índice de masa corporal (IMC) | altura y peso |
| Porcentaje de grasa corporal | altura, cuello y cintura (en mujeres además cadera) y sexo |
| Índice cintura/cadera | cintura y cadera |
| Índice cintura/estatura | cintura y altura |

Si falta algún dato no se inventa un número: la ficha dice qué falta para poder calcularlo.

### Ajustar la interpretación

En **Administración → Índices corporales** decide qué índices se muestran y, sobre todo,
**cómo se interpreta cada valor**. Cada índice tiene una tabla de rangos con su etiqueta
y su color, y cada fila puede aplicarse solo a un sexo o a una franja de edad.

Vienen cargados los valores habituales (OMS para el IMC, etc.), y siempre puede volver a
ellos con **«Restaurar valores de fábrica»**.

> Cada rango incluye el mínimo y excluye el máximo, de modo que 18,5–25 y 25–30 encajan
> sin huecos. Cuando varias filas encajan gana la más específica: puede dejar un rango
> general y añadir excepciones por edad o sexo encima.
>
> La **fórmula** de cada índice no se puede editar, a propósito: un error en una fórmula
> daría un dato de salud equivocado sin que nada avisara, y estos números se le enseñan
> al socio.

---

## Reconocimiento facial (kiosco de acceso)

Viene **activado** de fábrica. Se enciende y se apaga desde
**Administración → Control de acceso**, y ahí mismo se ve el histórico de entradas.

### Cómo se pone en marcha

1. **Registrar el rostro del cliente.** Se hace durante la inscripción: entre en
   **Inscripción de gym → el cliente → «Registrar rostro»**. Se toman las **5 muestras
   seguidas**, sin pulsar nada entre una y otra: la pantalla va pidiendo que mire de
   frente, gire un poco a un lado, al otro, levante la barbilla. Cada muestra se acepta
   sola cuando el encuadre es bueno (una sola persona, de frente, lo bastante cerca).
   Varias tomas con ángulos y luces distintas es lo que hace que la puerta acierte.
2. **Dejar abierta la pestaña del kiosco** en el PC de recepción, con la cámara apuntando
   a la puerta.

### Qué hace en la entrada

| Situación | Qué muestra |
|---|---|
| Socio con inscripción vigente | **ACCESO PERMITIDO** en verde, con su foto, documento, vencimiento y teléfono |
| Socio con inscripción vencida | **ACCESO DENEGADO**, indicando desde cuándo está vencida |
| Cliente sin ninguna inscripción | **ACCESO DENEGADO**, «sin inscripción registrada» |
| Rostro que no está registrado | «Rostro no reconocido. Diríjase a recepción» |
| Parecido dudoso | «Acérquese un poco más» — nunca adivina a quién enseñar |
| Varias personas a la vez | «Pasen de uno en uno», salvo que una esté claramente al frente |
| Rostro demasiado lejos | «Acérquese a la cámara» |

Quien se queda parado delante de la cámara **no genera entradas repetidas**: se le
sigue mostrando su ficha marcada como «ya se registró su entrada hace X». El tiempo que
dura ese bloqueo (el **antirrebote**) se cambia en **Control de acceso**: 90 segundos de
fábrica, 4 horas si quiere contar como mucho dos entradas al día, 12 horas para una sola.

> Mientras trabaja en el programa no hace falta cambiar de pestaña para saber quién
> acaba de entrar: cuando alguien pasa por la cámara aparece un **aviso abajo a la
> derecha** con su nombre y si se le permitió el paso. Se desvanece solo a los **10
> segundos** —el resto del tiempo no ocupa nada de la pantalla— y se puede cerrar antes
> con la «×». Solo avisa de lo que acaba de ocurrir: al abrir una pantalla no salta el
> aviso de alguien que entró hace rato.
>
> Si entra **gente en fila**, no se pierde ninguno: se anuncian uno tras otro, cada uno
> unos segundos, con un contador de cuántos quedan por mostrar («+3»). El último de la
> tanda se queda los 10 segundos completos.

> **Privacidad.** No se guarda ninguna imagen de la cámara. De cada rostro se almacenan
> 128 números que lo describen, con los que **no se puede reconstruir la cara**. La
> comparación ocurre dentro de este equipo: nada sale a internet.

### Si no lo quiere usar

Entre en **Control de acceso** y pulse **Desactivar**. La pestaña del kiosco deja de
abrirse sola y de pedir la cámara, y la inscripción deja de pedir el rostro. Los rostros
ya registrados se conservan por si vuelve a activarlo.

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
| «No hay espacio suficiente en la unidad» | Elija otra carpeta de destino o libere espacio. Hacen falta unos 55 MB. |
| El navegador dice que no puede conectarse | La ventana de control está cerrada. Abra el programa con el acceso directo. |
| No aparece el acceso directo en el escritorio | Vuelva a ejecutar el instalador y marque la casilla correspondiente, o cree el acceso a mano al `.exe`. |
| «No hay tarifa configurada para esta duración» | Es lo esperado en una instalación nueva: fije las tarifas en «Crear tarifas». |
| La cámara no funciona al tomar la foto | Debe permitir el acceso a la cámara en el navegador. Solo funciona en `localhost` o con HTTPS: es una restricción del navegador. |
| El kiosco dice «Otro programa está usando la cámara» | Ciérrelo (videollamadas, o el propio kiosco abierto en dos pestañas) y recargue. |
| El kiosco no reconoce a un socio que sí está registrado | Añada otra muestra de su rostro desde la inscripción, con la luz y las gafas del día a día. Compruebe que la cámara no esté a contraluz. |
| El kiosco no se abre solo al arrancar | El reconocimiento facial está desactivado. Actívelo en **Control de acceso**. |
| Olvidé la contraseña de administrador | No hay recuperación por correo. Cierre el programa, borre `data\gym.db` y vuelva a abrirlo: se recrea con `Admin` / `Admin.123`, pero **se pierden todos los datos**. |

Si algo falla al arrancar, el detalle técnico queda en `data\error.log`.

---

## Requisitos

- Windows 10 u 11 (64 bits).
- Navegador moderno: Chrome, Edge o Firefox.
- Cámara web, si quiere tomar la foto de los clientes desde el programa o usar el
  reconocimiento facial en la entrada.
- Espacio en disco: unos 55 MB, más lo que ocupen las fotos.

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
