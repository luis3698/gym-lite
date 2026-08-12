/* Devoluciones: validación del importe mientras se escribe.
 *
 * El servidor vuelve a comprobar el saldo dentro de una transacción antes de guardar,
 * así que esto no es la defensa: es para que quien está en el mostrador vea el error
 * ANTES de decírselo al cliente, no después de pulsar el botón.
 *
 * El saldo se relee del servidor al escribir porque otra caja puede haber devuelto
 * sobre el mismo recibo mientras esta pantalla estaba abierta.
 */
(function () {
  'use strict';

  // --- El lector de códigos escribe y confirma solo -------------------------
  // Si el campo queda con el foco, cada lectura busca directamente sin tocar nada.
  var entrada = document.querySelector('[data-scan-input]');
  if (entrada && !entrada.value) entrada.focus();

  var panel = document.querySelector('[data-refund-panel]');
  if (!panel) return;

  var form = panel.querySelector('[data-refund-form]');
  if (!form) return;

  var el = {
    amount: form.querySelector('[data-amount]'),
    msg: form.querySelector('[data-amount-msg]'),
    submit: form.querySelector('[data-submit]'),
    fillAll: form.querySelector('[data-fill-all]'),
    available: panel.querySelector('[data-available-label]'),
    refunded: panel.querySelector('[data-refunded]')
  };

  var disponible = parseFloat(panel.dataset.available) || 0;
  var enviando = false;

  function money(v) {
    var n = Math.round((v || 0) * 100) / 100;
    var entero = Math.floor(Math.abs(n));
    var centavos = Math.round((Math.abs(n) - entero) * 100);
    var texto = String(entero).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return '$' + (n < 0 ? '-' : '') + texto + (centavos ? ',' + String(centavos).padStart(2, '0') : '');
  }

  function revisar() {
    var valor = parseFloat(el.amount.value);

    if (el.amount.value === '' || isNaN(valor)) {
      el.msg.textContent = '';
      el.msg.className = 'tiny muted';
      el.submit.disabled = true;
      return;
    }
    if (valor <= 0) {
      el.msg.textContent = 'El importe debe ser mayor que cero.';
      el.msg.className = 'tiny';
      el.msg.style.color = 'var(--red-600)';
      el.submit.disabled = true;
      return;
    }
    // Se compara con dos decimales: sin redondear, «devolver todo» fallaba por una
    // milésima invisible arrastrada del cálculo en coma flotante.
    if (Math.round(valor * 100) > Math.round(disponible * 100)) {
      el.msg.textContent = 'Supera el saldo devolvible (' + money(disponible) + ').';
      el.msg.className = 'tiny';
      el.msg.style.color = 'var(--red-600)';
      el.submit.disabled = true;
      return;
    }

    var resto = Math.round((disponible - valor) * 100) / 100;
    el.msg.textContent = resto > 0
      ? 'Quedarían ' + money(resto) + ' por devolver.'
      : 'Devuelve el saldo completo del recibo.';
    el.msg.className = 'tiny';
    el.msg.style.color = 'var(--slate-500)';
    el.submit.disabled = false;
  }

  function refrescarSaldo() {
    fetch(panel.dataset.balanceUrl, { headers: { 'Accept': 'application/json' } })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (datos) {
        if (!datos || !datos.ok) return;
        if (Math.round(datos.available * 100) === Math.round(disponible * 100)) return;

        // Otra caja devolvió sobre este recibo mientras la pantalla estaba abierta.
        disponible = datos.available;
        panel.dataset.available = String(disponible);
        el.available.textContent = money(datos.available);
        el.refunded.textContent = money(datos.refunded);
        el.amount.max = String(disponible);
        if (el.fillAll) el.fillAll.textContent = 'Devolver todo (' + money(disponible) + ')';
        revisar();
      })
      .catch(function () { /* sin conexión: el servidor validará igualmente */ });
  }

  el.amount.addEventListener('input', revisar);
  el.amount.addEventListener('blur', refrescarSaldo);

  if (el.fillAll) {
    el.fillAll.addEventListener('click', function () {
      el.amount.value = disponible.toFixed(2);
      revisar();
    });
  }

  // Doble clic en el botón = dos devoluciones. Se bloquea al enviar.
  form.addEventListener('submit', function (event) {
    if (enviando) {
      event.preventDefault();
      return;
    }
    enviando = true;
    el.submit.disabled = true;
    el.submit.textContent = 'Registrando…';
  });

  revisar();
  refrescarSaldo();
})();
