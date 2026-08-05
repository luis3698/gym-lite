/* Captura de foto con la cámara y editor para centrar el rostro.
 *
 * Es el único JavaScript real de la aplicación: tomar una foto (getUserMedia) y
 * recortarla arrastrando (canvas) son capacidades del navegador que no tienen
 * equivalente en el servidor. El resultado viaja como data URL en un campo oculto y
 * Python lo decodifica y lo guarda como archivo (ver app/uploads.py).
 *
 * Sin librerías externas.
 */
(function () {
  "use strict";

  var STAGE = 300;   // lado del área de edición en pantalla, en píxeles CSS
  var OUTPUT = 480;  // lado de la imagen final que se guarda

  function init(root) {
    var el = {
      input:    root.querySelector("[data-pc-input]"),
      preview:  root.querySelector("[data-pc-preview]"),
      video:    root.querySelector("[data-pc-video]"),
      canvas:   root.querySelector("[data-pc-canvas]"),
      file:     root.querySelector("[data-pc-file]"),
      error:    root.querySelector("[data-pc-error]"),
      hint:     root.querySelector("[data-pc-hint]"),
      zoom:     root.querySelector("[data-pc-zoom]"),
      stepIdle: root.querySelector("[data-pc-step='idle']"),
      stepCam:  root.querySelector("[data-pc-step='camera']"),
      stepEdit: root.querySelector("[data-pc-step='editor']"),
      btnStart: root.querySelector("[data-pc-action='start']"),
      btnShoot: root.querySelector("[data-pc-action='shoot']"),
      btnCancel:root.querySelector("[data-pc-action='cancel']"),
      btnRetake:root.querySelector("[data-pc-action='retake']"),
      btnApply: root.querySelector("[data-pc-action='apply']"),
      btnClear: root.querySelector("[data-pc-action='clear']")
    };

    var stream = null;
    var image = null;          // Image ya cargada, lista para recortar
    var view = { scale: 1, minScale: 1, x: 0, y: 0 };
    var drag = null;
    var ctx = el.canvas.getContext("2d");

    el.canvas.width = STAGE;
    el.canvas.height = STAGE;

    function show(step) {
      el.stepIdle.hidden = step !== "idle";
      el.stepCam.hidden  = step !== "camera";
      el.stepEdit.hidden = step !== "editor";
    }

    function fail(message) {
      el.error.textContent = message;
      el.error.hidden = false;
    }

    function clearError() {
      el.error.hidden = true;
      el.error.textContent = "";
    }

    function stopCamera() {
      if (stream) {
        stream.getTracks().forEach(function (t) { t.stop(); });
        stream = null;
      }
      el.video.srcObject = null;
    }

    // --- Cámara ---------------------------------------------------------

    async function startCamera() {
      clearError();
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        fail("Este navegador no permite usar la cámara. Suba una imagen desde el equipo.");
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
          audio: false
        });
      } catch (err) {
        var name = err && err.name;
        if (name === "NotAllowedError") {
          fail("Se denegó el permiso de la cámara. Actívelo en la configuración del navegador.");
        } else if (name === "NotFoundError" || name === "OverconstrainedError") {
          fail("No se detectó ninguna cámara conectada. Suba una imagen desde el equipo.");
        } else if (name === "NotReadableError") {
          fail("La cámara está siendo usada por otra aplicación. Ciérrela e intente de nuevo.");
        } else {
          fail("No fue posible acceder a la cámara.");
        }
        return;
      }
      el.video.srcObject = stream;
      await el.video.play();
      show("camera");
    }

    function shoot() {
      var vw = el.video.videoWidth;
      var vh = el.video.videoHeight;
      if (!vw || !vh) { fail("La cámara todavía no está lista. Espere un instante."); return; }

      var tmp = document.createElement("canvas");
      tmp.width = vw;
      tmp.height = vh;
      var tctx = tmp.getContext("2d");
      // La vista previa se muestra en espejo (es lo natural para encuadrarse), así que
      // la captura también se refleja: la foto queda igual a lo que se vio en pantalla.
      tctx.translate(vw, 0);
      tctx.scale(-1, 1);
      tctx.drawImage(el.video, 0, 0, vw, vh);

      stopCamera();
      loadImage(tmp.toDataURL("image/jpeg", 0.92));
    }

    // --- Editor ---------------------------------------------------------

    function loadImage(src) {
      var img = new Image();
      img.onload = function () {
        image = img;
        // Encuadre inicial "cubrir": la imagen llena el área sin dejar huecos.
        view.minScale = Math.max(STAGE / img.width, STAGE / img.height);
        view.scale = view.minScale;
        view.x = (STAGE - img.width * view.scale) / 2;
        view.y = (STAGE - img.height * view.scale) / 2;
        el.zoom.min = "1";
        el.zoom.max = "4";
        el.zoom.step = "0.01";
        el.zoom.value = "1";
        clearError();
        show("editor");
        draw();
      };
      img.onerror = function () { fail("No fue posible leer la imagen."); };
      img.src = src;
    }

    function clampView() {
      // Impide que se vean bordes vacíos: la imagen siempre cubre el área de edición.
      var w = image.width * view.scale;
      var h = image.height * view.scale;
      view.x = Math.min(0, Math.max(STAGE - w, view.x));
      view.y = Math.min(0, Math.max(STAGE - h, view.y));
    }

    function paint(context, size) {
      var k = size / STAGE;
      context.clearRect(0, 0, size, size);
      context.fillStyle = "#0f172a";
      context.fillRect(0, 0, size, size);
      context.save();
      context.translate(view.x * k, view.y * k);
      context.scale(view.scale * k, view.scale * k);
      context.drawImage(image, 0, 0);
      context.restore();
    }

    function draw() {
      if (!image) return;
      clampView();
      paint(ctx, STAGE);

      // Guía circular: oscurece lo que quedará fuera del encuadre del rostro.
      ctx.save();
      ctx.fillStyle = "rgba(15, 23, 42, 0.55)";
      ctx.beginPath();
      ctx.rect(0, 0, STAGE, STAGE);
      ctx.arc(STAGE / 2, STAGE / 2, STAGE / 2 - 6, 0, Math.PI * 2, true);
      ctx.fill("evenodd");
      ctx.strokeStyle = "rgba(255,255,255,.9)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(STAGE / 2, STAGE / 2, STAGE / 2 - 6, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    function zoomTo(factor) {
      if (!image) return;
      var next = view.minScale * factor;
      // Se hace zoom respecto al centro, que es donde el usuario coloca la cara.
      var cx = STAGE / 2, cy = STAGE / 2;
      var ratio = next / view.scale;
      view.x = cx - (cx - view.x) * ratio;
      view.y = cy - (cy - view.y) * ratio;
      view.scale = next;
      draw();
    }

    function pointerDown(ev) {
      if (!image) return;
      var p = ev.touches ? ev.touches[0] : ev;
      drag = { x: p.clientX, y: p.clientY, ox: view.x, oy: view.y };
      if (ev.cancelable) ev.preventDefault();
    }

    function pointerMove(ev) {
      if (!drag || !image) return;
      var p = ev.touches ? ev.touches[0] : ev;
      view.x = drag.ox + (p.clientX - drag.x);
      view.y = drag.oy + (p.clientY - drag.y);
      draw();
      if (ev.cancelable) ev.preventDefault();
    }

    function pointerUp() { drag = null; }

    function apply() {
      if (!image) return;
      var out = document.createElement("canvas");
      out.width = OUTPUT;
      out.height = OUTPUT;
      // Se pinta con la MISMA transformación que se ve en pantalla, escalada: lo que
      // el usuario encuadró es exactamente lo que se guarda.
      paint(out.getContext("2d"), OUTPUT);
      var dataUrl = out.toDataURL("image/jpeg", 0.88);

      el.input.value = dataUrl;
      el.preview.innerHTML = "";
      var img = new Image();
      img.src = dataUrl;
      img.alt = "";
      el.preview.appendChild(img);
      el.btnClear.hidden = false;
      el.hint.textContent = "Foto lista. Se guardará al enviar el formulario.";
      image = null;
      show("idle");
    }

    function cancel() {
      stopCamera();
      image = null;
      clearError();
      show("idle");
    }

    function clearPhoto() {
      el.input.value = "__REMOVE__";  // el servidor lo interpreta como "quitar la foto"
      el.preview.innerHTML = '<span class="pc-empty">Sin foto</span>';
      el.btnClear.hidden = true;
      el.hint.textContent = "";
    }

    // --- Eventos --------------------------------------------------------

    el.btnStart.addEventListener("click", startCamera);
    el.btnShoot.addEventListener("click", shoot);
    el.btnCancel.addEventListener("click", cancel);
    el.btnRetake.addEventListener("click", function () { image = null; startCamera(); });
    el.btnApply.addEventListener("click", apply);
    el.btnClear.addEventListener("click", clearPhoto);

    el.zoom.addEventListener("input", function () { zoomTo(parseFloat(el.zoom.value) || 1); });

    el.file.addEventListener("change", function () {
      var f = el.file.files && el.file.files[0];
      if (!f) return;
      var reader = new FileReader();
      reader.onload = function () { loadImage(reader.result); };
      reader.onerror = function () { fail("No fue posible leer el archivo."); };
      reader.readAsDataURL(f);
      el.file.value = "";
    });

    el.canvas.addEventListener("mousedown", pointerDown);
    window.addEventListener("mousemove", pointerMove);
    window.addEventListener("mouseup", pointerUp);
    el.canvas.addEventListener("touchstart", pointerDown, { passive: false });
    el.canvas.addEventListener("touchmove", pointerMove, { passive: false });
    el.canvas.addEventListener("touchend", pointerUp);

    // Si se abandona la página con la cámara encendida, se apaga: si no, el piloto
    // del equipo se queda iluminado hasta cerrar la pestaña.
    window.addEventListener("pagehide", stopCamera);

    show("idle");
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-photo-capture]").forEach(init);
  });
})();
