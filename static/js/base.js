        (() => {
            const boton = document.getElementById('theme-toggle');
            const icono = document.getElementById('theme-icon');
            const etiqueta = document.getElementById('theme-label');
            if (!boton) return;

            const actualizarControl = () => {
                const oscuro = document.documentElement.dataset.theme === 'dark';
                boton.setAttribute('aria-pressed', String(oscuro));
                icono.textContent = oscuro ? '☀' : '☾';
                etiqueta.textContent = oscuro ? 'Modo claro' : 'Modo nocturno';
            };

            boton.addEventListener('click', () => {
                const nuevoTema = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
                document.documentElement.dataset.theme = nuevoTema;
                document.documentElement.setAttribute('data-bs-theme', nuevoTema);
                localStorage.setItem('hotel-theme', nuevoTema);
                actualizarControl();
            });

            actualizarControl();
        })();

        (() => {
            const body = document.body;
            const toggle = document.getElementById('sidebar-toggle');
            const mobileToggle = document.getElementById('mobile-menu-toggle');
            const backdrop = document.getElementById('sidebar-backdrop');
            const desktop = () => window.matchMedia('(min-width: 992px)').matches;
            const iconos = {
                'Dashboard': 'D', 'Reservas': 'R', 'Check-in': 'IN', 'Check-out': 'OUT',
                'Caja': '$', 'Plano': 'P', 'Habitaciones': 'H', 'Tipos': 'T',
                'Tarifas': 'TA', 'Productos': 'PR', 'Promociones': '%', 'Reportes': 'RP',
                'Politica': 'PC', 'Usuarios': 'U', 'Administrar usuarios': 'U',
                'Clientes': 'CL', 'Consumos': 'CO', 'Nueva reserva': '+',
            };

            const enlaces = [...document.querySelectorAll('.sidebar-nav .hotel-nav-link')];
            let activo = null;
            let longitudActiva = -1;
            const actual = window.location.pathname;
            const moduloActual = document.querySelector('[data-sidebar-module]')?.dataset.sidebarModule || '';

            enlaces.forEach(enlace => {
                const texto = enlace.textContent.trim();
                enlace.title = texto;
                enlace.textContent = '';
                const icono = document.createElement('span');
                icono.className = 'nav-icon';
                icono.setAttribute('aria-hidden', 'true');
                icono.textContent = iconos[texto] || texto.slice(0, 2).toUpperCase();
                const etiqueta = document.createElement('span');
                etiqueta.className = 'nav-label';
                etiqueta.textContent = texto;
                enlace.append(icono, etiqueta);

                const ruta = new URL(enlace.href, window.location.origin).pathname;
                const coincide = moduloActual
                    ? texto === moduloActual
                    : actual === ruta || (ruta !== '/' && actual.startsWith(ruta));
                if (coincide && ruta.length > longitudActiva) {
                    activo = enlace;
                    longitudActiva = ruta.length;
                }
                enlace.addEventListener('click', () => body.classList.remove('sidebar-mobile-open'));
            });
            if (activo) activo.classList.add('is-active');

            const actualizarAria = () => {
                const colapsado = body.classList.contains('sidebar-collapsed');
                const abiertoMovil = body.classList.contains('sidebar-mobile-open');
                if (toggle) {
                    toggle.setAttribute('aria-expanded', String(desktop() ? !colapsado : abiertoMovil));
                    toggle.setAttribute('aria-label', desktop() ? (colapsado ? 'Expandir menu' : 'Contraer menu') : 'Cerrar menu');
                }
                if (mobileToggle) mobileToggle.setAttribute('aria-expanded', String(abiertoMovil));
            };

            if (localStorage.getItem('hotel-sidebar-collapsed') === 'true' && desktop()) {
                body.classList.add('sidebar-collapsed');
            }
            toggle?.addEventListener('click', () => {
                if (desktop()) {
                    body.classList.toggle('sidebar-collapsed');
                    localStorage.setItem('hotel-sidebar-collapsed', String(body.classList.contains('sidebar-collapsed')));
                } else {
                    body.classList.remove('sidebar-mobile-open');
                }
                actualizarAria();
            });
            mobileToggle?.addEventListener('click', () => {
                body.classList.toggle('sidebar-mobile-open');
                actualizarAria();
            });
            backdrop?.addEventListener('click', () => {
                body.classList.remove('sidebar-mobile-open');
                actualizarAria();
            });
            document.addEventListener('keydown', event => {
                if (event.key === 'Escape') {
                    body.classList.remove('sidebar-mobile-open');
                    actualizarAria();
                }
            });
            window.addEventListener('resize', () => {
                if (desktop()) body.classList.remove('sidebar-mobile-open');
                actualizarAria();
            });
            actualizarAria();
        })();
