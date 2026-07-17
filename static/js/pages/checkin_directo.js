(() => {
    const entrada = document.getElementById('walkin').dataset.fechaEntrada;
    const salida = document.getElementById('id_fecha_salida');
    const adultos = document.getElementById('id_num_adultos');
    const tipo = document.getElementById('filtro-tipo');
    const habitacion = document.getElementById('id_habitacion');
    const promocion = document.getElementById('id_promocion');
    const estado = document.getElementById('estado-disponibilidad');
    const detalle = document.getElementById('detalle-habitacion');
    const detalleTitulo = document.getElementById('detalle-titulo');
    const detalleTexto = document.getElementById('detalle-texto');
    const detalleTarifa = document.getElementById('detalle-tarifa');
    const boton = document.getElementById('btn-checkin');
    const seleccionInicial = habitacion.value;
    let habitaciones = new Map();
    let solicitudActual = 0;

    function mostrarEstado(mensaje, clase = 'secondary') {
        estado.className = `alert alert-${clase} mb-3`;
        estado.textContent = mensaje;
    }

    function limpiarHabitaciones(mensaje) {
        habitaciones = new Map();
        habitacion.innerHTML = '<option value="">---------</option>';
        habitacion.disabled = true;
        boton.disabled = true;
        detalle.classList.add('d-none');
        if (mensaje) mostrarEstado(mensaje);
    }

    async function cotizarSeleccion(actualizarPromociones = true) {
        const item = habitaciones.get(String(habitacion.value));
        detalleTarifa.textContent = '';
        if (!item) {
            detalle.classList.add('d-none');
            boton.disabled = true;
            return;
        }

        detalleTitulo.textContent = `Habitación ${item.numero}`;
        detalleTexto.textContent = `${item.tipo.nombre} · Piso ${item.piso} · Capacidad ${item.tipo.capacidad}`;
        detalle.classList.remove('d-none');
        boton.disabled = true;

        const params = new URLSearchParams({
            habitacion: item.id,
            fecha_entrada: entrada,
            fecha_salida: salida.value,
            num_personas: adultos.value,
        });
        if (promocion.value) params.set('promocion', promocion.value);
        try {
            const respuesta = await fetch(`/api/reservas/cotizar/?${params}`, {
                headers: {'Accept': 'application/json'},
            });
            const data = await respuesta.json();
            if (!respuesta.ok) throw new Error(data.detail || 'No se pudo calcular la tarifa.');
            if (actualizarPromociones) {
                const seleccion = promocion.value;
                promocion.replaceChildren(new Option('Aplicar mejor promoción automáticamente', ''));
                data.promociones_disponibles.forEach(item => {
                    const alcance = item.tipo_habitacion_id ? 'Tipo seleccionado' : 'Todas las habitaciones';
                    promocion.add(new Option(`${item.nombre} · ${item.porcentaje_descuento}% · ${alcance}`, item.id));
                });
                if ([...promocion.options].some(opcion => opcion.value === seleccion)) {
                    promocion.value = seleccion;
                }
            }
            const promociones = data.promociones_aplicadas.map(
                promo => `${promo.nombre} (-${promo.porcentaje_descuento}%)`
            ).join(', ');
            detalleTarifa.textContent = Number(data.descuento_total) > 0
                ? `${data.noches} noche(s) · Antes S/ ${data.precio_sin_descuento} · ${promociones} · Ahorro S/ ${data.descuento_total} · Total S/ ${data.precio_total}`
                : `${data.noches} noche(s) · Total habitación: S/ ${data.precio_total}`;
            detalleTarifa.textContent += ` · Salida anticipada: ${data.politica_cobro.nombre}`;
            boton.disabled = false;
        } catch (error) {
            detalleTarifa.textContent = error.message;
            mostrarEstado('La disponibilidad cambió. Actualiza la búsqueda.', 'warning');
        }
    }

    async function buscarHabitaciones(conservarSeleccion = false) {
        const numeroSolicitud = ++solicitudActual;
        if (!salida.value || salida.value <= entrada || !adultos.value || Number(adultos.value) < 1) {
            limpiarHabitaciones('Selecciona una salida posterior a hoy y la cantidad de adultos.');
            return;
        }

        limpiarHabitaciones();
        mostrarEstado('Consultando habitaciones para toda la estancia…', 'info');
        const params = new URLSearchParams({
            fecha_entrada: entrada,
            fecha_salida: salida.value,
            num_personas: adultos.value,
        });
        if (tipo.value) params.set('tipo', tipo.value);

        try {
            const respuesta = await fetch(`/api/habitaciones/disponibles/?${params}`, {
                headers: {'Accept': 'application/json'},
            });
            const data = await respuesta.json();
            if (numeroSolicitud !== solicitudActual) return;
            if (!respuesta.ok) throw new Error('No se pudo consultar la disponibilidad.');

            habitaciones = new Map(data.map(item => [String(item.id), item]));
            habitacion.innerHTML = '<option value="">Selecciona una habitación</option>';
            data.forEach(item => {
                const opcion = document.createElement('option');
                opcion.value = item.id;
                opcion.textContent = `Hab. ${item.numero} · ${item.tipo.nombre} · Piso ${item.piso} · Cap. ${item.tipo.capacidad}`;
                habitacion.appendChild(opcion);
            });
            habitacion.disabled = data.length === 0;
            mostrarEstado(
                data.length ? `${data.length} habitación(es) disponible(s) durante todo el rango.` : 'No hay habitaciones libres durante todo el rango solicitado.',
                data.length ? 'success' : 'warning'
            );
            const anterior = conservarSeleccion ? seleccionInicial : '';
            if (anterior && habitaciones.has(String(anterior))) {
                habitacion.value = anterior;
                cotizarSeleccion();
            }
        } catch (error) {
            if (numeroSolicitud !== solicitudActual) return;
            limpiarHabitaciones(error.message);
            mostrarEstado(error.message, 'danger');
        }
    }

    salida.addEventListener('change', () => buscarHabitaciones());
    adultos.addEventListener('change', () => buscarHabitaciones());
    tipo.addEventListener('change', () => buscarHabitaciones());
    habitacion.addEventListener('change', cotizarSeleccion);
    promocion.addEventListener('change', () => cotizarSeleccion(false));
    limpiarHabitaciones();
    if (salida.value) buscarHabitaciones(true);
})();
