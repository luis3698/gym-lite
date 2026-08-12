/* Carrito: la cantidad se guarda sola, sin botón de confirmar.
 *
 * El envío se retrasa un momento tras la última tecla. Sin esa espera, escribir «12»
 * mandaría primero un 1 y después un 12: dos recargas de página, y la segunda pisando
 * a la primera. Con las flechas del campo pasa lo mismo al pulsarlas varias veces
 * seguidas.
 */
(function () {
  'use strict';

  // Suficiente para terminar de teclear un número de dos cifras sin que se note espera.
  var ESPERA_MS = 600;

  document.querySelectorAll('[data-cart-line]').forEach(function (form) {
    var campo = form.querySelector('[data-cart-quantity]');
    if (!campo) return;

    var temporizador = null;
    var enviado = false;

    function enviar() {
      if (enviado) return;         // el formulario ya va camino del servidor
      var valor = parseInt(campo.value, 10);
      var minimo = parseInt(campo.min, 10) || 1;
      var maximo = parseInt(campo.max, 10);

      // Un campo vacío o a medio escribir no debe mandarse: el servidor lo rechazaría
      // y el usuario perdería lo que estaba tecleando.
      if (isNaN(valor)) return;
      if (valor < minimo) campo.value = minimo;
      if (!isNaN(maximo) && valor > maximo) campo.value = maximo;

      enviado = true;
      form.submit();
    }

    function programar() {
      clearTimeout(temporizador);
      temporizador = setTimeout(enviar, ESPERA_MS);
    }

    campo.addEventListener('input', programar);
    // Al salir del campo se guarda ya, sin esperar.
    campo.addEventListener('blur', function () {
      clearTimeout(temporizador);
      enviar();
    });
    // Enter guardaría igualmente por ser un formulario, pero así no se duplica el envío.
    campo.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        clearTimeout(temporizador);
        enviar();
      }
    });
  });
})();
