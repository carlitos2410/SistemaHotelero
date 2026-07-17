(() => {
    const form = document.getElementById('checkin-confirm-form');
    const selector = document.getElementById('promocion-checkin');
    const estado = document.getElementById('estado-promocion-checkin');
    selector.addEventListener('change', async () => {
        const params = new URLSearchParams({
            habitacion: form.dataset.habitacion,
            fecha_entrada: form.dataset.fechaEntrada,
            fecha_salida: form.dataset.fechaSalida,
            num_personas: form.dataset.numPersonas,
        });
        if (selector.value) params.set('promocion', selector.value);
        estado.textContent = 'Recalculando promoción…';
        estado.className = 'small mt-2 text-muted';
        try {
            const respuesta = await fetch(`/api/reservas/cotizar/?${params}`);
            const data = await respuesta.json();
            if (!respuesta.ok) throw new Error(data.detail || 'No se pudo calcular la promoción.');
            document.getElementById('precio-original-checkin').textContent = `S/ ${data.precio_sin_descuento}`;
            document.getElementById('descuento-checkin').textContent = `- S/ ${data.descuento_total}`;
            document.getElementById('total-checkin').textContent = `S/ ${data.precio_total}`;
            const nombres = data.promociones_aplicadas.map(item => item.nombre).join(', ');
            estado.textContent = nombres ? `Se aplicará: ${nombres}. Ahorro S/ ${data.descuento_total}.` : 'No hay descuento aplicable.';
            estado.className = `small mt-2 ${nombres ? 'text-success' : 'text-muted'}`;
        } catch (error) {
            estado.textContent = error.message;
            estado.className = 'small mt-2 text-danger';
        }
    });
    selector.dispatchEvent(new Event('change'));
})();
