(() => {
    const grid = document.getElementById('room-grid');
    const dataUrl = grid.dataset.source;
    const filters = ['hotel', 'piso', 'tipo', 'estado'].map(name => document.getElementById(`filter-${name}`));
    const statusText = document.getElementById('live-status');
    const refreshButton = document.getElementById('refresh-button');
    const modalElement = document.getElementById('room-detail-modal');
    let roomModal;

    function applyFilters() {
        const [hotel, piso, tipo, estado] = filters.map(field => field.value);
        let visibles = 0;
        grid.querySelectorAll('.room-cell').forEach(card => {
            const visible = (!hotel || card.dataset.hotelId === hotel)
                && (!piso || card.dataset.piso === piso)
                && (!tipo || card.dataset.tipoId === tipo)
                && (!estado || card.dataset.estado === estado);
            card.hidden = !visible;
            if (visible) visibles += 1;
        });
        let empty = document.getElementById('filtered-empty-state');
        if (!visibles) {
            if (!empty) {
                empty = document.createElement('div');
                empty.id = 'filtered-empty-state';
                empty.className = 'empty-state';
                empty.textContent = 'No hay habitaciones que coincidan con los filtros.';
                grid.appendChild(empty);
            }
            empty.hidden = false;
        } else if (empty) {
            empty.hidden = true;
        }
    }

    function createRoomCard(room) {
        const card = document.createElement('button');
        card.type = 'button';
        card.className = `room-cell room-${room.estado.toLowerCase()}`;
        card.setAttribute('aria-label', `Habitación ${room.numero}, ${room.estado.toLowerCase()}`);
        Object.entries({
            roomId: room.id, hotelId: room.hotel_id, hotel: room.hotel,
            tipoId: room.tipo_id, tipo: room.tipo, capacidad: room.capacidad,
            piso: room.piso, numero: room.numero, estado: room.estado,
            reservaId: room.reserva_id || '', huesped: room.huesped || ''
        }).forEach(([key, value]) => { card.dataset[key] = String(value); });
        card.dataset.historial = JSON.stringify(room.historial || []);

        const number = document.createElement('div');
        number.className = 'room-number';
        number.textContent = `Hab. ${room.numero}`;
        const type = document.createElement('div');
        type.className = 'room-type';
        type.textContent = room.tipo;
        const meta = document.createElement('div');
        meta.className = 'room-meta';
        meta.textContent = `Piso ${room.piso} · Cap. ${room.capacidad}`;
        const state = document.createElement('span');
        state.className = 'room-state';
        state.textContent = room.estado;
        card.append(number, type, meta, state);
        return card;
    }

    function updateSummary(summary) {
        ['DISPONIBLE', 'RESERVADA', 'OCUPADA', 'LIMPIEZA', 'MANTENIMIENTO'].forEach(state => {
            document.getElementById(`count-${state.toLowerCase()}`).textContent = summary[state] || 0;
        });
    }

    async function refreshRooms() {
        refreshButton.disabled = true;
        statusText.textContent = 'Actualizando plano...';
        try {
            const response = await fetch(dataUrl, {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                credentials: 'same-origin'
            });
            if (!response.ok) throw new Error('No fue posible actualizar el plano.');
            const data = await response.json();
            grid.replaceChildren(...data.habitaciones.map(createRoomCard));
            updateSummary(data.resumen);
            applyFilters();
            const updated = new Date(data.actualizado_en);
            statusText.textContent = `Actualizado a las ${updated.toLocaleTimeString('es-PE', {hour: '2-digit', minute: '2-digit', second: '2-digit'})}`;
        } catch (error) {
            statusText.textContent = 'No se pudo actualizar. Se conservan los últimos datos.';
        } finally {
            refreshButton.disabled = false;
        }
    }

    grid.addEventListener('click', event => {
        const card = event.target.closest('.room-cell');
        if (!card) return;
        document.getElementById('room-detail-title').textContent = `Habitación ${card.dataset.numero}`;
        document.getElementById('detail-hotel').textContent = card.dataset.hotel;
        document.getElementById('detail-tipo').textContent = card.dataset.tipo;
        document.getElementById('detail-piso').textContent = card.dataset.piso;
        document.getElementById('detail-capacidad').textContent = `${card.dataset.capacidad} persona(s)`;
        const state = document.getElementById('detail-estado');
        state.textContent = card.dataset.estado;
        state.className = `badge room-${card.dataset.estado.toLowerCase()}`;
        const guestLabel = document.getElementById('detail-huesped-label');
        const guest = document.getElementById('detail-huesped');
        const reservationLink = document.getElementById('detail-reserva-link');
        const hasReservation = Boolean(card.dataset.reservaId);
        guestLabel.classList.toggle('d-none', !hasReservation);
        guest.classList.toggle('d-none', !hasReservation);
        guest.textContent = card.dataset.huesped;
        reservationLink.classList.toggle('d-none', !hasReservation);
        reservationLink.href = hasReservation ? `/reservas/?q=${encodeURIComponent(card.dataset.reservaId)}` : '#';
        const historyContainer = document.getElementById('detail-history');
        historyContainer.replaceChildren();
        let history = [];
        try { history = JSON.parse(card.dataset.historial || '[]'); } catch (error) { history = []; }
        if (!history.length) {
            const emptyHistory = document.createElement('p');
            emptyHistory.className = 'text-muted mb-0';
            emptyHistory.textContent = 'Todavía no hay transiciones registradas.';
            historyContainer.appendChild(emptyHistory);
        } else {
            history.forEach(change => {
                const item = document.createElement('div');
                item.className = 'border-start border-3 ps-2 mb-2';
                const date = new Date(change.fecha).toLocaleString('es-PE');
                item.textContent = `${date}: ${change.estado_anterior} → ${change.estado_nuevo} · ${change.usuario}${change.motivo ? ` · ${change.motivo}` : ''}`;
                historyContainer.appendChild(item);
            });
        }
        roomModal = roomModal || new bootstrap.Modal(modalElement);
        roomModal.show();
    });

    filters.forEach(filter => filter.addEventListener('change', applyFilters));
    refreshButton.addEventListener('click', refreshRooms);
    window.setInterval(refreshRooms, 15000);
    refreshRooms();
})();
