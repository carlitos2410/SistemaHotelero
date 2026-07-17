document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('reserva-form');
    const entrada = document.getElementById('id_fecha_entrada');
    const salida = document.getElementById('id_fecha_salida');
    const adultos = document.getElementById('id_num_adultos');
    const tipo = document.getElementById('tipo-habitacion');
    const habitacionSelect = document.getElementById('habitacion-disponible');
    const habitacionInput = document.getElementById('id_habitacion');
    const promocion = document.getElementById('id_promocion');
    const guardar = document.getElementById('guardar-reserva');
    const disponibilidadEstado = document.getElementById('resultado-disponibilidad');
    const cotizacion = document.getElementById('cotizacion');
    let consultaActual = 0;

    const parametrosBase = () => {
        const params = new URLSearchParams({
            fecha_entrada: entrada.value,
            fecha_salida: salida.value,
            num_personas: adultos.value || '1'
        });
        if (tipo.value) params.set('tipo', tipo.value);
        return params;
    };

    const mostrarError = (elemento, mensaje) => {
        elemento.textContent = mensaje;
        elemento.classList.remove('text-muted', 'text-success');
        elemento.classList.add('text-danger');
    };

    async function cargarDisponibilidad(conservarSeleccion = false) {
        const anterior = conservarSeleccion ? habitacionInput.value : '';
        guardar.disabled = true;
        habitacionInput.value = '';
        cotizacion.textContent = 'Selecciona una habitación para calcular la tarifa.';
        if (!entrada.value || !salida.value || !adultos.value || salida.value <= entrada.value) {
            habitacionSelect.replaceChildren(new Option('Completa un rango de fechas válido', ''));
            mostrarError(disponibilidadEstado, 'La salida debe ser posterior a la entrada.');
            return;
        }

        const idConsulta = ++consultaActual;
        disponibilidadEstado.textContent = 'Consultando habitaciones...';
        disponibilidadEstado.className = 'form-text text-muted';
        try {
            const response = await fetch(`/api/habitaciones/disponibles/?${parametrosBase()}`);
            const data = await response.json();
            if (idConsulta !== consultaActual) return;
            if (!response.ok) throw new Error(data.detail || 'No se pudo consultar la disponibilidad.');

            habitacionSelect.replaceChildren(new Option(data.length ? 'Selecciona una habitación' : 'No hay habitaciones disponibles', ''));
            data.forEach(habitacion => {
                const texto = `Hab. ${habitacion.numero} · Piso ${habitacion.piso} · ${habitacion.tipo.nombre} · S/ ${habitacion.tipo.precio_base}`;
                habitacionSelect.add(new Option(texto, habitacion.id));
            });
            disponibilidadEstado.textContent = `${data.length} habitación(es) disponible(s).`;
            disponibilidadEstado.className = 'form-text text-success';
            if (anterior && data.some(item => String(item.id) === String(anterior))) {
                habitacionSelect.value = anterior;
                habitacionInput.value = anterior;
                await cargarCotizacion();
            }
        } catch (error) {
            habitacionSelect.replaceChildren(new Option('Error al consultar', ''));
            mostrarError(disponibilidadEstado, error.message);
        }
    }

    async function cargarCotizacion(actualizarPromociones = true) {
        const habitacion = habitacionSelect.value;
        habitacionInput.value = habitacion;
        guardar.disabled = true;
        if (!habitacion) {
            cotizacion.textContent = 'Selecciona una habitación para calcular la tarifa.';
            return;
        }
        const params = parametrosBase();
        params.set('habitacion', habitacion);
        if (promocion.value) params.set('promocion', promocion.value);
        try {
            const response = await fetch(`/api/reservas/cotizar/?${params}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'No se pudo calcular la tarifa.');
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
            const detalle = data.desglose.map(item => {
                const promo = item.promocion_nombre
                    ? ` · ${item.promocion_nombre} (-${item.porcentaje_descuento}%)`
                    : '';
                return `${item.fecha}: ${item.tarifa_nombre}${promo} (S/ ${item.precio_noche})`;
            }).join(' · ');
            const ahorro = Number(data.descuento_total) > 0
                ? ` Antes: S/ ${data.precio_sin_descuento} · Descuento: S/ ${data.descuento_total} ·`
                : '';
            const politica = data.politica_cobro.codigo === 'ESTADIA_REAL_PENALIDAD'
                ? `${data.politica_cobro.nombre} (${data.politica_cobro.porcentaje_penalidad}% sobre noches no usadas)`
                : data.politica_cobro.nombre;
            cotizacion.textContent = `${data.noches} noche(s) ·${ahorro} Total: S/ ${data.precio_total}. Adelanto para confirmar (50%): S/ ${data.garantia_reserva.monto_requerido}, con ${data.garantia_reserva.plazo_pago_horas} horas para completarlo. Política de salida: ${politica}. ${detalle}`;
            cotizacion.className = 'alert alert-success mb-4';
            guardar.disabled = false;
        } catch (error) {
            cotizacion.textContent = error.message;
            cotizacion.className = 'alert alert-danger mb-4';
        }
    }

    [entrada, salida, adultos, tipo].forEach(control => control.addEventListener('change', () => cargarDisponibilidad(false)));
    habitacionSelect.addEventListener('change', cargarCotizacion);
    promocion.addEventListener('change', () => cargarCotizacion(false));

    document.getElementById('buscar-huesped').addEventListener('click', async () => {
        const tipoDoc = document.getElementById('id_tipo_doc').value;
        const numDoc = document.getElementById('id_num_doc').value.trim();
        const resultado = document.getElementById('resultado-huesped');
        if (!numDoc) return mostrarError(resultado, 'Ingresa el número de documento.');
        try {
            const params = new URLSearchParams({tipo_doc: tipoDoc, num_doc: numDoc});
            const response = await fetch(`/api/huespedes/buscar/?${params}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'No se pudo buscar al huésped.');
            if (!data.encontrado) {
                resultado.textContent = 'Huésped nuevo: completa sus datos.';
                resultado.className = 'form-text text-primary';
                return;
            }
            ['tipo_doc', 'num_doc', 'nombres', 'apellidos', 'email', 'telefono', 'nacionalidad'].forEach(campo => {
                document.getElementById(`id_${campo}`).value = data.huesped[campo] || '';
            });
            resultado.textContent = 'Huésped encontrado; datos cargados.';
            resultado.className = 'form-text text-success';
        } catch (error) {
            mostrarError(resultado, error.message);
        }
    });

    form.addEventListener('submit', event => {
        if (!habitacionInput.value || guardar.disabled) event.preventDefault();
    });

    if (entrada.value && salida.value) cargarDisponibilidad(true);
});
