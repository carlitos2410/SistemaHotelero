# Auditoría técnica del Sistema Hotelero

Fecha: 15 de julio de 2026
Alcance: backend Django, API REST, base de datos, reglas hoteleras, roles, frontend web, contenedores y mantenibilidad.

## Seguimiento de mejoras

### 16 de julio de 2026 — Configuración segura por entorno

- Desarrollo dejó de aceptar `ALLOWED_HOSTS = ['*']`.
- Producción exige `SECRET_KEY` y `ALLOWED_HOSTS`; si faltan, el sistema no arranca.
- HTTPS, cookies seguras y HSTS se activan automáticamente en modo producción.
- Se añadieron encabezados, políticas de cookies y protección de contenido explícitas.
- Docker Compose obtiene credenciales y configuración desde variables de entorno.
- Se añadió `.env.example` sin secretos reales y pruebas automatizadas de configuración.
- `HSTS preload` se mantiene como decisión manual para evitar bloquear dominios o subdominios sin preparación HTTPS.

Pendiente de esta línea: sustituir `runserver` por un servidor WSGI de producción cuando se defina el despliegue real.

### 16 de julio de 2026 — Integridad e inmutabilidad financiera

- Reservas con historial, estancias, folios, pagos, comprobantes, cargos, prórrogas y movimientos de caja quedaron protegidos contra borrados en cascada.
- Hotel y huésped no pueden eliminarse mientras conserven reservas relacionadas.
- El administrador Django muestra los registros operativos y financieros en modo de consulta, sin creación, edición ni eliminación manual.
- PostgreSQL valida que el total del folio coincida con subtotal más IGV.
- PostgreSQL exige correlativos de comprobante y movimientos de caja con importes positivos.
- Se conserva el vínculo doble de un adelanto con reserva y folio después del check-in, necesario para trazabilidad sin duplicar el pago.
- La migración se aplicó correctamente y la suite aumentó a 100 pruebas aprobadas.

### 16 de julio de 2026 — Políticas de cobro centralizadas

- Administración puede configurar garantía de reserva, plazo de pago, IGV incluido y porcentajes de early check-in y late checkout desde la política de cobro.
- Se conservaron como valores iniciales las reglas existentes: 50 %, 24 horas, IGV 18 %, early check-in 5 % y late checkout 50 %.
- Cada reserva copia un snapshot de IGV y recargos; los cambios globales solo afectan reservas nuevas.
- Cada folio copia el IGV de su reserva y calcula subtotal e impuesto con ese porcentaje histórico.
- La cotización API y el esquema OpenAPI exponen las mismas reglas que utiliza el frontend.
- Los conceptos de cargos early/late muestran el porcentaje realmente aplicado.
- Los comprobantes PDF muestran y calculan el IGV histórico, sin constantes duplicadas.
- Las migraciones se aplicaron correctamente y la suite aumentó a 102 pruebas aprobadas.

### 16 de julio de 2026 — Rendimiento y crecimiento de datos

- Reservas, clientes, historial de pagos y reporte de caja se paginan en bloques de 25 registros.
- El paginador conserva búsqueda, estado, fechas y demás filtros al cambiar de página.
- Los totales de pagos, ingresos y egresos se calculan sobre todo el conjunto filtrado antes de paginar.
- Los filtros de fecha usan rangos de fecha y hora que permiten aprovechar índices PostgreSQL.
- Housekeeping obtiene únicamente el último checkout por habitación mediante subconsulta, sin precargar todo el historial.
- Se añadieron índices para estados y fechas de reservas, checkouts por habitación, salidas programadas, pagos y movimientos de caja.
- Las migraciones se aplicaron correctamente y la suite aumentó a 105 pruebas aprobadas.

## 1. Resumen ejecutivo

El sistema presenta un nivel funcional sólido para demostración académica: tiene reservas con restricción de solapamiento, tarifas por temporada, promociones, garantía de reserva, check-in y check-out, folio, caja, housekeeping, historial de estados, reportes, API REST y control de acceso por roles.

La suite completa contiene 93 pruebas y finalizó correctamente. Django no detecta migraciones pendientes, el contrato OpenAPI valida y las dependencias instaladas son consistentes.

No se detectaron archivos temporales, plantillas huérfanas, vistas sin ruta, imports muertos ni módulos completos que puedan eliminarse con seguridad. Se retiró solamente un método redundante de `HuespedForm` que devolvía el documento sin validarlo ni transformarlo.

El sistema está preparado para continuar su evolución local. Antes de exponerlo en Internet o usarlo como sistema productivo, deben atenderse los hallazgos de prioridad alta.

## 2. Validaciones realizadas

- `python manage.py test`: 93 pruebas aprobadas.
- `python manage.py makemigrations --check --dry-run`: sin cambios pendientes.
- `python manage.py spectacular --validate`: esquema OpenAPI válido.
- `python -m pip check`: dependencias sin conflictos.
- Análisis de referencias: todas las plantillas están enlazadas.
- Análisis AST: no se encontraron imports de producción sin uso. Las importaciones de `signals` son intencionales.
- Revisión de rutas: las vistas web y API forman parte de URLs activas.
- `python manage.py check --deploy`: seis advertencias de seguridad que deben resolverse para producción.

## 3. Fortalezas comprobadas

### Modelos y base de datos

- Restricción PostgreSQL que evita reservas activas solapadas por habitación.
- Restricción que evita temporadas tarifarias solapadas por tipo de habitación.
- Restricciones para fechas, porcentajes y montos no negativos.
- Historial de estados de habitaciones y reservas.
- Bloqueos `select_for_update` en operaciones sensibles.
- Transacciones atómicas en reserva, check-in, check-out, cargos, pagos, cancelaciones y prórrogas.

### Reglas hoteleras

- La habitación no puede recibir check-in si no está disponible.
- El check-out bloquea la salida cuando existe deuda.
- El check-out cambia la habitación a limpieza.
- Housekeeping respeta transiciones por rol.
- Las tarifas se calculan por noche y temporada.
- Las promociones quedan reflejadas en el precio histórico de la reserva.
- La garantía del 50 % confirma la reserva cuando se completa.
- Cancelaciones y devoluciones generan movimientos de caja auditables.

### API y frontend

- Endpoints mínimos solicitados por la guía implementados.
- JWT y autenticación de sesión disponibles.
- Permisos diferenciados para recepción, gerencia, administración y limpieza.
- Esquema OpenAPI y Swagger funcionales.
- Plano, calendario, bandeja de reservas, check-in, checkout, folio, caja, housekeeping y reportes integrados.
- Modo claro/nocturno y menú adaptado por rol.

## 4. Hallazgos priorizados

### P1 — Bloqueantes para producción

#### 4.1 Configuración de seguridad de desarrollo

Evidencia:

- `DEBUG` queda activo por defecto.
- `ALLOWED_HOSTS` acepta cualquier host.
- Existe una `SECRET_KEY` de desarrollo como valor alternativo.
- No están configuradas cookies seguras, redirección HTTPS ni HSTS.
- Docker Compose contiene credenciales PostgreSQL conocidas.

Riesgo: exposición de información, suplantación de host, robo de sesión y uso inseguro al publicar el sistema.

Mejora propuesta:

- Separar configuración local y producción mediante variables de entorno.
- Exigir `SECRET_KEY`, hosts y credenciales sin valores inseguros de respaldo en producción.
- Activar HTTPS, cookies seguras y HSTS únicamente detrás de un proxy HTTPS correctamente configurado.
- Usar Gunicorn o equivalente; no usar `runserver` en producción.

Criterio de cierre: `manage.py check --deploy` sin advertencias relevantes en el entorno de producción.

#### 4.2 Conservación legal y contable de datos

Evidencia: varias relaciones financieras y operativas usan `on_delete=CASCADE`. Eliminar un hotel, huésped, reserva, estancia o pago puede eliminar en cadena parte de su trazabilidad.

Riesgo: pérdida de comprobantes, pagos, movimientos de caja, folios e historial.

Mejora propuesta:

- Proteger registros con `PROTECT` o `RESTRICT` cuando tengan movimientos financieros.
- Sustituir eliminación física por campos `activo`, `anulado_en`, `anulado_por` y motivo.
- Impedir desde administración la eliminación de registros contables emitidos.
- Incorporar una política formal de retención y respaldo.

Criterio de cierre: no es posible borrar físicamente un registro que tenga efecto contable; toda anulación conserva autor, fecha y motivo.

#### 4.3 Pagos todavía simulados

Evidencia: los pagos se crean con `es_simulado=True` tanto para folios como para adelantos.

Riesgo: el sistema registra cobros operativos, pero no confirma transacciones con una pasarela ni emite comprobantes electrónicos válidos ante SUNAT.

Mejora propuesta: mantener el modo simulado para la presentación académica y diseñar un adaptador de pagos/comprobantes antes de uso comercial real.

#### 4.4 Aislamiento por hotel

Evidencia: existe la entidad `Hotel`, pero los usuarios y roles no están asociados a un hotel. Los querysets consultan datos globales.

Riesgo: si se registra un segundo hotel, un usuario podría consultar u operar información de ambos establecimientos.

Mejora propuesta: decidir explícitamente entre sistema de un solo hotel o multi-hotel. Para multi-hotel, crear membresía Usuario–Hotel–Rol y filtrar todas las vistas, API y reportes por el hotel activo.

### P2 — Importantes para escalabilidad y mantenibilidad

#### 4.5 Listados sin paginación

La bandeja de reservas, clientes, pagos y algunos catálogos pueden cargar todos los registros. Funcionan con la base actual, pero crecerán en memoria y tiempo de respuesta.

Mejora propuesta: paginación del lado del servidor, preservando filtros, con límites de 25 o 50 registros.

#### 4.6 Consulta histórica de housekeeping

El dashboard precarga todos los checkouts históricos de las habitaciones en limpieza para usar únicamente el último.

Mejora propuesta: obtener solo la fecha o estancia del último checkout mediante subconsulta o anotación.

#### 4.7 Índices orientados a consultas reales

Las búsquedas frecuentes filtran reservas por estado y fechas, estancias por checkout y movimientos por fecha. Las claves foráneas tienen índice, pero faltan índices compuestos para estos patrones.

Mejora propuesta: medir con `EXPLAIN ANALYZE` y agregar índices únicamente donde exista ganancia comprobada.

#### 4.8 Políticas codificadas directamente

La garantía del 50 %, su plazo de 24 horas y el IGV del 18 % aparecen como constantes directas en servicios, API, modelos y PDF.

Riesgo: cambiar una política exige editar varios archivos y puede producir inconsistencias.

Mejora propuesta: centralizar garantía, plazo, IGV y recargos horarios en una configuración versionada; copiar un snapshot de la política a cada reserva o estancia.

#### 4.9 Ejecución de vencimientos por interacción

Las reservas sin garantía vencida se liberan cuando se consulta disponibilidad o se abren determinadas pantallas. El comportamiento protege la operación, pero el estado puede quedar desactualizado mientras nadie usa el sistema.

Mejora propuesta: comando idempotente programado cada pocos minutos, conservando la validación defensiva existente en los flujos web.

#### 4.10 Frontend monolítico y dependiente de CDN

`base.html` y varias plantillas contienen grandes bloques de CSS y JavaScript. Bootstrap y fuentes se descargan desde CDN.

Riesgo: mantenimiento difícil, repetición de estilos y degradación visual si el hotel pierde conexión a Internet.

Mejora propuesta: mover estilos y scripts por módulo a archivos estáticos locales y mantener un sistema único de variables de diseño.

### P3 — Evolución recomendada

- Añadir protección contra intentos repetidos en login y obtención de JWT.
- Añadir límites de frecuencia a endpoints de búsqueda y cotización.
- Incorporar logs estructurados, identificador por solicitud y registro de errores.
- Automatizar respaldos PostgreSQL y probar periódicamente la restauración.
- Agregar pruebas end-to-end de los cinco criterios de aceptación de la guía.
- Medir cobertura de pruebas y consultas por pantalla.
- Añadir validación formal de DNI, CE, pasaporte, RUC y teléfono según el tipo de documento.
- Añadir accesibilidad consistente en formularios, tablas y diálogos.

## 5. Evaluación global

| Área | Estado | Observación |
|---|---|---|
| Cumplimiento de guía académica | Alto | Los flujos principales y endpoints requeridos están implementados. |
| Integridad de reservas | Alto | Exclusion constraints, validaciones y transacciones. |
| Tarifas, promociones y folio | Alto | Flujo integrado y probado. |
| Roles operativos | Alto para un hotel | Requiere aislamiento adicional si será multi-hotel. |
| Seguridad local | Adecuada | Autenticación, CSRF y permisos presentes. |
| Seguridad de producción | Pendiente | Seis advertencias de despliegue. |
| Escalabilidad | Media | Falta paginación, optimización e índices medidos. |
| Mantenibilidad frontend | Media | CSS/JS concentrado en plantillas grandes. |
| Observabilidad y respaldo | Baja | No hay estrategia visible de logs, monitoreo y restauración. |

## 6. Orden recomendado de ejecución

1. Configuración y seguridad de producción.
2. Integridad e inmutabilidad financiera.
3. Centralización de políticas de cobro e impuestos.
4. Paginación e índices de reservas, clientes y caja.
5. Optimización de housekeeping y reportes.
6. Separación de CSS/JavaScript en archivos estáticos.
7. Automatización de vencimientos, respaldos y observabilidad.
8. Multi-hotel, solamente si forma parte del alcance real.

Cada etapa debe cerrarse con migraciones revisadas, pruebas unitarias, pruebas por rol y verificación visual en modo claro y nocturno.

## 7. Avance del 16/07/2026 — mantenibilidad frontend

- Se configuró `STATICFILES_DIRS` y `STATIC_ROOT` para centralizar los recursos locales.
- El CSS global se trasladó a `static/css/base.css` y la lógica global a `static/js/base.js`.
- Se extrajeron los estilos de 12 vistas a `static/css/pages/` y la navegación modular a `static/css/components/module-nav.css`.
- Se extrajeron los scripts de login, reserva, check-in, plano y dashboard a `static/js/pages/`.
- Los valores generados por Django se entregan al JavaScript mediante atributos `data-*`, evitando mezclar plantillas con lógica de cliente.
- Solo permanece un script mínimo en el `<head>` para aplicar el tema guardado antes del renderizado y evitar el parpadeo claro/oscuro.
- Se actualizaron las pruebas para verificar tanto los enlaces estáticos como el contenido funcional de los recursos.

Validación: `manage.py check` sin observaciones, 105 pruebas aprobadas y comprobación visual del login, modo claro/nocturno y control de contraseña sin errores de consola.

La mantenibilidad frontend pasa de **Media** a **Alta para el alcance actual**. Sigue pendiente decidir si Bootstrap y las fuentes se alojarán localmente para operar sin conexión a Internet.

## 8. Avance del 16/07/2026 — housekeeping y reportes

- Housekeeping valida el filtro de piso y descarta valores inexistentes sin provocar errores del servidor.
- El dashboard obtiene la última observación de mantenimiento mediante subconsultas, sin precargar todo el historial de cada habitación.
- Los listados de limpieza y mantenimiento se evalúan una sola vez antes de clasificarse y renderizarse.
- Revenue facturado, ingresos, devoluciones y pagos históricos se agrupan en PostgreSQL por tipo de habitación, evitando cargar y recorrer cada registro financiero en Python.
- La ocupación de los últimos siete días se calcula sin consultar folios, pagos ni movimientos de caja, porque esa tarjeta solo requiere información operativa.
- Se agregaron pruebas para filtros inválidos, selección de la última observación y ausencia de consultas financieras en el cálculo exclusivamente operativo.

Validación: `manage.py check` sin observaciones y **107 pruebas aprobadas**.

## 9. Avance del 16/07/2026 — automatización, auditoría y flujo integral

- Se creó el comando idempotente `procesar_reservas_operativas` para cancelar garantías vencidas y marcar no-show sin depender de abrir el dashboard.
- El comando admite simulación (`--dry-run`), ejecución inmediata y modo continuo con intervalo configurable.
- El marcado manual y automático de no-show comparte una única regla transaccional y registra el adelanto retenido.
- Se añadió un canal central `hotel.operaciones` para cambios de reserva, estados de habitación, adelantos, cargos y pagos.
- Los eventos solo aceptan identificadores internos, estados, cantidades y montos; contraseñas, documentos y datos personales se descartan.
- Los errores HTTP no controlados se registran mediante `django.request` con el mismo formato de consola.
- Se corrigió la API para no guardar `fecha_checkout` mientras exista deuda pendiente.
- Se agregó una prueba end-to-end que cubre tarifa y promoción, garantía del 50%, check-in, consumo, folio, bloqueo por deuda, pago, checkout, housekeeping y reporte de revenue.
- Los respaldos se excluyen deliberadamente por tratarse de una entrega académica y no formar parte de la rúbrica funcional.

Validación: simulación operativa sin cambios, `manage.py check` sin observaciones y **110 pruebas aprobadas**.

## 10. Avance del 16/07/2026 — contraste nocturno de tablas

- Se normalizaron las variables Bootstrap de fondo, texto, bordes, filas alternas y hover para todas las tablas estándar.
- Se cubrieron explícitamente las tablas personalizadas de dashboard, reservas e inventario de habitaciones.
- Los encabezados nocturnos usan fondo verde oscuro y texto dorado con contraste alto.
- El hover conserva fondo oscuro y texto claro, incluyendo enlaces dentro de la fila.
- Las filas de advertencia, peligro, éxito y estado activo mantienen colores diferenciados sin volver a fondos blancos.

Validación visual en Habitaciones, Reservas y Reportes, sin errores de consola. `manage.py check` sin observaciones y **110 pruebas aprobadas**.
