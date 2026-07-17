(() => {
  const grid = document.getElementById('dashboard-room-grid');
  const piso = document.getElementById('dashboard-filter-piso');
  const estado = document.getElementById('dashboard-filter-estado');
  const status = document.getElementById('dashboard-map-status');
  const fullMapUrl = grid.dataset.fullMapUrl;

  function applyDashboardFilters() {
    grid.querySelectorAll('.hab-card').forEach(card => {
      card.hidden = Boolean((piso.value && card.dataset.piso !== piso.value)
        || (estado.value && card.dataset.estado !== estado.value));
    });
  }

  function createCard(room) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = `hab-card ${room.estado.toLowerCase()}`;
    card.dataset.piso = String(room.piso);
    card.dataset.estado = room.estado;
    card.title = `${room.huesped || 'Sin huésped'} · Ver historial`;
    const number = document.createElement('div'); number.className = 'hab-numero'; number.textContent = `Hab. ${room.numero}`;
    const meta = document.createElement('div'); meta.className = 'hab-meta'; meta.textContent = `${room.tipo} · Piso ${room.piso}`;
    const badge = document.createElement('span'); badge.className = 'hab-badge'; badge.textContent = room.estado;
    card.append(number, meta, badge);
    return card;
  }

  async function refreshDashboardMap() {
    try {
      const response = await fetch(grid.dataset.source, {credentials: 'same-origin'});
      if (!response.ok) throw new Error();
      const data = await response.json();
      grid.replaceChildren(...data.habitaciones.map(createCard));
      applyDashboardFilters();
      status.textContent = `Actualizado ${new Date(data.actualizado_en).toLocaleTimeString('es-PE')}`;
    } catch (error) {
      status.textContent = 'No se pudo actualizar; se muestran los últimos datos.';
    }
  }

  piso.addEventListener('change', applyDashboardFilters);
  estado.addEventListener('change', applyDashboardFilters);
  grid.addEventListener('click', event => {
    if (event.target.closest('.hab-card')) window.location.href = fullMapUrl;
  });
  refreshDashboardMap();
  window.setInterval(refreshDashboardMap, 15000);
})();
