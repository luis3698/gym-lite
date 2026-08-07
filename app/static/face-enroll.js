/* Registro del rostro de un cliente durante la inscripción.
 *
 * Un solo botón toma las muestras que falten, seguidas, guiando al cliente entre una
 * y otra. No se pide un clic por muestra: quien atiende el mostrador está a la vez
 * cobrando, y una tarea de cinco clics acaba haciéndose a medias —con lo que el
 * kiosco reconoce mal y nadie sabe por qué—.
 *
 * La calidad de lo que se guarda aquí decide si el kiosco acierta después, así que
 * ninguna muestra se acepta hasta que la imagen cumple unos mínimos, y en pantalla se
 * dice en cada momento qué falta para llegar a ellos.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-face-enroll]');
  if (!root) return;

  var CFG = {
    CHECK_MS: 200,
    INPUT_SIZE: 320,
    SCORE_MIN: 0.5,

    // Para dar de alta se exige más cerca que para reconocer: estas muestras son la
    // referencia de todas las comparaciones futuras.
    MIN_FACE_RATIO: 0.22,

    // Fotogramas seguidos que deben cumplir todo antes de aceptar una muestra.
    STABLE_FRAMES: 3,

    // Dos muestras casi idénticas no aportan nada: la segunda no cubre ningún caso
    // que la primera no cubriera ya. Se exige una diferencia mínima.
    MIN_VARIATION: 0.06,

    // Si el cliente se queda quieto, se acepta igualmente pasado este tiempo en vez
    // de esperar indefinidamente a una variación que no va a llegar.
    VARIATION_TIMEOUT_MS: 4000,

    // Pausa entre muestras, para que dé tiempo a leer la indicación y moverse.
    BETWEEN_MS: 900
  };

  /* Cada muestra pide una pose distinta. La red reconoce mejor de frente, así que las
     variaciones son suaves: lo que se busca es cubrir la luz y el ángulo del día a
     día, no rostros de perfil que después no casarían. */
  var POSES = [
    { texto: 'Mire de frente a la cámara.', maxYaw: 1.8 },
    { texto: 'Gire la cabeza un poco a su derecha.', maxYaw: 2.6 },
    { texto: 'Gire la cabeza un poco a su izquierda.', maxYaw: 2.6 },
    { texto: 'Levante ligeramente la barbilla.', maxYaw: 2.2 },
    { texto: 'Otra vez de frente, con expresión neutra.', maxYaw: 1.8 }
  ];

  var el = {
    form: root.querySelector('[data-face-form]'),
    input: root.querySelector('[data-face-input]'),
    video: root.querySelector('[data-face-video]'),
    overlay: root.querySelector('[data-face-overlay]'),
    hint: root.querySelector('[data-face-hint]'),
    pose: root.querySelector('[data-face-pose]'),
    progress: root.querySelector('[data-face-progress]'),
    bar: root.querySelector('[data-face-bar]'),
    error: root.querySelector('[data-face-error]'),
    start: root.querySelector('[data-face-action="start"]'),
    steps: {
      idle: root.querySelector('[data-face-step="idle"]'),
      camera: root.querySelector('[data-face-step="camera"]')
    }
  };

  var objetivo = parseInt(root.dataset.pending, 10) || 0;

  var state = {
    stream: null,
    timer: null,
    busy: false,
    options: null,
    loaded: false,
    stable: 0,
    capturadas: [],
    indice: 0,
    esperandoDesde: 0,
    pausa: false
  };

  // --- Presentación --------------------------------------------------------

  function showStep(name) {
    Object.keys(el.steps).forEach(function (key) {
      el.steps[key].hidden = key !== name;
    });
  }

  function fail(mensaje) {
    el.error.textContent = mensaje;
    el.error.hidden = false;
  }

  function hint(texto, listo) {
    el.hint.textContent = texto;
    el.hint.className = listo ? 'flash success' : 'notice';
  }

  function progreso() {
    var hechas = state.capturadas.length;
    el.progress.textContent = 'Muestra ' + Math.min(hechas + 1, objetivo) + ' de ' + objetivo;
    el.bar.style.width = Math.round((hechas / objetivo) * 100) + '%';
    el.pose.textContent = POSES[state.indice % POSES.length].texto;
  }

  // --- Cámara --------------------------------------------------------------

  function stopCamera() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    if (state.stream) {
      state.stream.getTracks().forEach(function (t) { t.stop(); });
      state.stream = null;
    }
    el.video.srcObject = null;
    state.stable = 0;
  }

  function loadModels() {
    if (state.loaded) return Promise.resolve();
    hint('Cargando el motor de reconocimiento…', false);
    return Promise.all([
      faceapi.nets.tinyFaceDetector.loadFromUri(root.dataset.modelsUrl),
      faceapi.nets.faceLandmark68Net.loadFromUri(root.dataset.modelsUrl),
      faceapi.nets.faceRecognitionNet.loadFromUri(root.dataset.modelsUrl)
    ]).then(function () {
      state.options = new faceapi.TinyFaceDetectorOptions({
        inputSize: CFG.INPUT_SIZE,
        scoreThreshold: CFG.SCORE_MIN
      });
      state.loaded = true;
    });
  }

  function start() {
    el.error.hidden = true;
    state.capturadas = [];
    state.indice = 0;
    state.stable = 0;
    state.pausa = false;
    state.esperandoDesde = Date.now();
    showStep('camera');
    progreso();
    hint('Iniciando la cámara…', false);

    loadModels()
      .then(function () {
        return navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 720 }, height: { ideal: 720 }, facingMode: 'user' }
        });
      })
      .then(function (stream) {
        state.stream = stream;
        el.video.srcObject = stream;
        return el.video.play();
      })
      .then(function () {
        state.timer = setInterval(check, CFG.CHECK_MS);
      })
      .catch(function (err) {
        stopCamera();
        showStep('idle');
        if (err && err.name === 'NotAllowedError') {
          fail('El navegador bloqueó la cámara. Permita el acceso y vuelva a intentarlo.');
        } else if (err && err.name === 'NotFoundError') {
          fail('No se encontró ninguna cámara conectada.');
        } else if (err && err.name === 'NotReadableError') {
          fail('Otro programa está usando la cámara. Ciérrelo e intente de nuevo.');
        } else {
          fail('No se pudo iniciar la cámara: ' + (err && err.message ? err.message : err));
        }
      });
  }

  function cancel() {
    stopCamera();
    showStep('idle');
    el.error.hidden = true;
  }

  // --- Comprobación de calidad ---------------------------------------------

  function distancia(a, b) {
    var total = 0;
    for (var i = 0; i < a.length; i++) { var d = a[i] - b[i]; total += d * d; }
    return Math.sqrt(total);
  }

  function centro(puntos) {
    var s = puntos.reduce(function (acc, p) { return { x: acc.x + p.x, y: acc.y + p.y }; }, { x: 0, y: 0 });
    return { x: s.x / puntos.length, y: s.y / puntos.length };
  }

  function desvioLateral(landmarks) {
    /* Cuánto está girada la cabeza, comparando la distancia de la nariz a cada ojo.
       1 es perfectamente de frente; cuanto mayor, más girada. */
    try {
      var izq = centro(landmarks.getLeftEye());
      var der = centro(landmarks.getRightEye());
      var nariz = centro(landmarks.getNose());
      var di = Math.abs(nariz.x - izq.x);
      var dd = Math.abs(nariz.x - der.x);
      if (di === 0 || dd === 0) return 1;
      return di > dd ? di / dd : dd / di;
    } catch (e) {
      return 1;  // si los puntos no vienen, no se bloquea por esto
    }
  }

  function drawBox(box, ok) {
    var ctx = el.overlay.getContext('2d');
    if (el.overlay.width !== el.video.videoWidth) {
      el.overlay.width = el.video.videoWidth;
      el.overlay.height = el.video.videoHeight;
    }
    ctx.clearRect(0, 0, el.overlay.width, el.overlay.height);
    if (!box) return;
    ctx.lineWidth = 3;
    ctx.strokeStyle = ok ? '#22c55e' : '#f59e0b';
    ctx.strokeRect(box.x, box.y, box.width, box.height);
  }

  function rechazar(mensaje) {
    state.stable = 0;
    hint(mensaje, false);
  }

  function aceptar(descriptor) {
    state.capturadas.push(Array.from(descriptor));
    state.stable = 0;
    state.indice += 1;
    progreso();

    if (state.capturadas.length >= objetivo) {
      enviar();
      return;
    }

    // Pausa breve: sin ella las cinco muestras salen del mismo instante y del mismo
    // gesto, que es justo lo que se quería evitar.
    state.pausa = true;
    hint('Muestra ' + state.capturadas.length + ' guardada. ' +
         POSES[state.indice % POSES.length].texto, true);
    setTimeout(function () {
      state.pausa = false;
      state.esperandoDesde = Date.now();
    }, CFG.BETWEEN_MS);
  }

  function check() {
    if (state.busy || state.pausa || !el.video.videoWidth) return;
    state.busy = true;

    faceapi
      .detectAllFaces(el.video, state.options)
      .then(function (faces) {
        if (faces.length === 0) {
          drawBox(null);
          rechazar('No se detecta ningún rostro. Colóquese frente a la cámara.');
          return null;
        }
        if (faces.length > 1) {
          drawBox(null);
          rechazar('Se ven ' + faces.length + ' rostros. Debe quedar solo el del cliente.');
          return null;
        }
        var box = faces[0].box;
        if (box.width < el.video.videoWidth * CFG.MIN_FACE_RATIO) {
          drawBox(box, false);
          rechazar('Acérquese más a la cámara: el rostro se ve pequeño.');
          return null;
        }
        drawBox(box, true);

        return faceapi
          .detectSingleFace(el.video, state.options)
          .withFaceLandmarks()
          .withFaceDescriptor();
      })
      .then(function (result) {
        if (!result || !result.descriptor) return;

        var pose = POSES[state.indice % POSES.length];
        if (desvioLateral(result.landmarks) > pose.maxYaw) {
          rechazar('Demasiado girado. ' + pose.texto);
          return;
        }

        // Que la muestra aporte algo respecto a la anterior.
        var previa = state.capturadas[state.capturadas.length - 1];
        var esperando = Date.now() - state.esperandoDesde;
        if (previa && distancia(Array.from(result.descriptor), previa) < CFG.MIN_VARIATION &&
            esperando < CFG.VARIATION_TIMEOUT_MS) {
          rechazar(pose.texto + ' (cambie un poco la postura)');
          return;
        }

        state.stable += 1;
        if (state.stable < CFG.STABLE_FRAMES) {
          hint('Quieto un momento… ' + pose.texto, false);
          return;
        }
        aceptar(result.descriptor);
      })
      .catch(function (err) {
        console.error('[rostro] fallo al analizar', err);
      })
      .then(function () {
        state.busy = false;
      });
  }

  // --- Envío ---------------------------------------------------------------

  function enviar() {
    el.input.value = JSON.stringify(state.capturadas);
    hint('Guardando las ' + state.capturadas.length + ' muestras…', true);
    // La cámara se apaga antes de enviar: si no, el piloto de la webcam se queda
    // encendido durante toda la recarga de la página.
    stopCamera();
    el.form.submit();
  }

  // --- Enganches -----------------------------------------------------------

  root.addEventListener('click', function (event) {
    var accion = event.target.closest('[data-face-action]');
    if (!accion) return;
    if (accion.dataset.faceAction === 'start') start();
    if (accion.dataset.faceAction === 'cancel') cancel();
  });

  // Salir de la página con la cámara abierta deja el piloto encendido en algunos
  // equipos hasta que se cierra el navegador.
  window.addEventListener('pagehide', stopCamera);

  if (typeof faceapi === 'undefined') {
    if (el.start) el.start.disabled = true;
    fail('No se pudo cargar el motor de reconocimiento facial. Reinstale el programa.');
  }
})();
