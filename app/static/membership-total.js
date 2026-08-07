/* Resumen en vivo de la inscripción.
 *
 * Recalcula duración, vigencia y total cada vez que se toca algo del formulario, para
 * que el importe se vea ANTES de guardar y no solo en el recibo.
 *
 * Esto es solo para mostrar: al enviar, el servidor vuelve a calcularlo todo con las
 * tarifas leídas de la base. Si alguien manipulara este cálculo no se cobraría de
 * menos; simplemente vería un número que no coincide con su recibo.
 */
(function () {
  'use strict';

  var form = document.querySelector('[data-membership-form]');
  if (!form) return;

  var datos = JSON.parse(form.querySelector('[data-tariffs]').textContent);

  // Debe coincidir con helpers.DURATION_DAYS del servidor.
  var DIAS = { DAY_1: 1, DAY_7: 7, DAY_15: 15 };
  var UNIDADES = {
    DAY_1: ['día', 'días'],
    DAY_7: ['semana', 'semanas'],
    DAY_15: ['quincena', 'quincenas'],
    MONTH: ['mes', 'meses']
  };

  var el = {
    quantity: form.querySelector('[data-quantity]'),
    quantityUnit: form.querySelector('[data-quantity-unit]'),
    quantityHint: form.querySelector('[data-quantity-hint]'),
    startDate: form.querySelector('[data-start-date]'),
    duration: form.querySelector('[data-sum-duration]'),
    period: form.querySelector('[data-sum-period]'),
    baseLabel: form.querySelector('[data-sum-base-label]'),
    base: form.querySelector('[data-sum-base]'),
    services: form.querySelector('[data-sum-services]'),
    total: form.querySelector('[data-sum-total]'),
    warning: form.querySelector('[data-sum-warning]')
  };

  // --- Formato, igual que el filtro `money` del servidor --------------------

  function money(valor) {
    var n = Math.round((valor || 0) * 100) / 100;
    var signo = n < 0 ? '-' : '';
    n = Math.abs(n);
    var entero = Math.floor(n);
    var centavos = Math.round((n - entero) * 100);
    var texto = String(entero).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return '$' + signo + texto + (centavos ? ',' + String(centavos).padStart(2, '0') : '');
  }

  var MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
               'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

  function fecha(d) {
    return String(d.getDate()).padStart(2, '0') + ' ' + MESES[d.getMonth()] + ' ' + d.getFullYear();
  }

  // --- Fechas ---------------------------------------------------------------

  function sumarMeses(inicio, meses) {
    /* Mismo recorte que add_months() en el servidor: sumar un mes al 31 de enero da
       28 (o 29) de febrero, no el 3 de marzo. */
    var total = inicio.getMonth() + meses;
    var anio = inicio.getFullYear() + Math.floor(total / 12);
    var mes = ((total % 12) + 12) % 12;
    var ultimoDia = new Date(anio, mes + 1, 0).getDate();
    return new Date(anio, mes, Math.min(inicio.getDate(), ultimoDia));
  }

  function vencimiento(inicio, duracion, cantidad) {
    if (DIAS[duracion]) {
      var fin = new Date(inicio.getTime());
      fin.setDate(fin.getDate() + DIAS[duracion] * cantidad);
      return fin;
    }
    return sumarMeses(inicio, cantidad);
  }

  // --- Cálculo --------------------------------------------------------------

  function precioBase(duracion, cantidad) {
    var tarifa = datos.inscription[duracion];
    if (tarifa === undefined || tarifa === null) return null;
    if (duracion === 'MONTH') return tarifa + datos.extra_month * (cantidad - 1);
    return tarifa * cantidad;
  }

  function leer() {
    var radio = form.querySelector('input[name="duration_type"]:checked');
    var cantidad = parseInt(el.quantity.value, 10);
    if (!(cantidad >= 1)) cantidad = 1;
    if (cantidad > datos.max_quantity) cantidad = datos.max_quantity;
    return {
      duracion: radio ? radio.value : null,
      cantidad: cantidad,
      inicio: el.startDate.value ? new Date(el.startDate.value + 'T00:00:00') : null,
      servicios: Array.prototype.map.call(
        form.querySelectorAll('input[name="service_ids"]:checked'),
        function (input) {
          return datos.services.filter(function (s) { return String(s.id) === input.value; })[0];
        }
      ).filter(Boolean)
    };
  }

  function linea(nombre, importe) {
    var fila = document.createElement('div');
    fila.className = 'summary-line';
    var izq = document.createElement('span');
    izq.textContent = nombre;
    var der = document.createElement('span');
    der.className = 'bold';
    der.textContent = money(importe);
    fila.appendChild(izq);
    fila.appendChild(der);
    return fila;
  }

  function pintar() {
    var v = leer();
    if (!v.duracion) return;

    var unidad = UNIDADES[v.duracion] || ['vez', 'veces'];
    el.quantityUnit.textContent = '(' + (v.cantidad === 1 ? unidad[0] : unidad[1]) + ')';

    // Duración
    var etiqueta = datos.labels[v.duracion] + (v.cantidad > 1 ? ' x ' + v.cantidad : '');
    el.duration.textContent = etiqueta;

    // Vigencia y pista de cuántos días son en total
    if (v.inicio && !isNaN(v.inicio.getTime())) {
      var fin = vencimiento(v.inicio, v.duracion, v.cantidad);
      var dias = Math.round((fin - v.inicio) / 86400000);
      el.period.textContent = fecha(v.inicio) + ' → ' + fecha(fin);
      el.quantityHint.textContent = v.cantidad + ' ' +
        (v.cantidad === 1 ? unidad[0] : unidad[1]) + ' = ' + dias + ' día(s) de vigencia';
    } else {
      el.period.textContent = 'indique la fecha de inicio';
      el.quantityHint.textContent = '';
    }

    // Importes
    var base = precioBase(v.duracion, v.cantidad);
    var faltaTarifa = base === null;
    el.baseLabel.textContent = 'Inscripción (' + etiqueta + ')';
    el.base.textContent = faltaTarifa ? 'sin tarifa' : money(base);

    el.services.textContent = '';
    var serviciosTotal = 0;
    v.servicios.forEach(function (s) {
      serviciosTotal += s.price;
      el.services.appendChild(linea(s.name, s.price));
    });

    el.total.textContent = faltaTarifa ? '—' : money(base + serviciosTotal);

    if (faltaTarifa) {
      el.warning.textContent =
        'No hay tarifa configurada para «' + datos.labels[v.duracion] + '». ' +
        'Configúrela en «Crear tarifas» antes de registrar.';
      el.warning.hidden = false;
    } else if (v.duracion === 'MONTH' && v.cantidad > 1) {
      el.warning.textContent =
        'El primer mes va a la tarifa mensual y los ' + (v.cantidad - 1) +
        ' siguientes a la de mes adicional (' + money(datos.extra_month) + ' cada uno).';
      el.warning.hidden = false;
    } else if (v.cantidad > 1) {
      el.warning.textContent = datos.labels[v.duracion] + ' × ' + v.cantidad +
        ' a ' + money(datos.inscription[v.duracion]) + ' cada uno.';
      el.warning.hidden = false;
    } else {
      el.warning.hidden = true;
    }
  }

  // `input` cubre teclado y flechas del número; `change` cubre radios y casillas.
  form.addEventListener('input', pintar);
  form.addEventListener('change', pintar);
  pintar();
})();
