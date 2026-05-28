# Documentacion tecnica del Sistema Hotelero

## 1. Resumen del sistema

El sistema hotelero es una aplicacion web desarrollada con Django. Permite gestionar la operacion principal de un hotel: usuarios por rol, habitaciones, reservas, check-in, check-out, consumos, caja, comprobantes, limpieza, mantenimiento, calendario de ocupacion y reportes.

El proyecto esta organizado por aplicaciones Django. Cada app agrupa una parte funcional del negocio para mantener el codigo ordenado y facil de sustentar.

## 2. Arquitectura general

La arquitectura sigue el patron MTV de Django:

- **Model**: representa las tablas de la base de datos. Se encuentra en `models.py`.
- **Template**: representa las interfaces HTML. Se encuentra en `templates/`.
- **View**: contiene la logica que procesa solicitudes, consulta modelos y devuelve una respuesta. Se encuentra en `views.py`.

Ademas, Django usa:

- **urls.py**: define las rutas web del sistema.
- **forms.py**: valida formularios antes de guardar datos.
- **admin.py**: registra modelos en el panel administrativo de Django.
- **settings.py**: contiene configuracion general del proyecto.
- **docker-compose.yml**: levanta PostgreSQL, Django y pgAdmin.
- **requirements.txt**: lista las dependencias Python.

## 3. Mapa del proyecto

```text
SistemaHotelero/
├── config/
│   ├── settings.py          Configuracion general de Django
│   ├── urls.py              Rutas principales del proyecto
│   ├── wsgi.py              Entrada WSGI para despliegue
│   └── asgi.py              Entrada ASGI para despliegue asincrono
│
├── usuarios/
│   ├── auth.py              Roles, permisos por grupo y decorador role_required
│   ├── views.py             Dashboards, disponibilidad, nueva reserva y maestros admin
│   ├── urls.py              Login, dashboards y rutas base
│   ├── forms.py             Formulario de busqueda de disponibilidad
│   ├── context_processors.py Variables globales de rol para templates
│   └── management/commands/
│       └── crear_roles_hotel.py Comando para crear grupos y permisos
│
├── hoteles/
│   ├── models.py            Datos fiscales y generales del hotel
│   └── admin.py             Configuracion del hotel en Django admin
│
├── habitaciones/
│   ├── models.py            Tipos, habitaciones y observaciones de mantenimiento
│   ├── views.py             Listado y cambio de estado de habitaciones
│   ├── urls.py              Rutas de habitaciones
│   └── management/commands/
│       └── cargar_datos_hotel.py Comando semilla de tipos, habitaciones y servicios
│
├── reservas/
│   ├── models.py            Huespedes, tarifas, promociones, reservas y acompanantes
│   ├── forms.py             Formularios de reserva, check-in directo y filtros
│   ├── services.py          Calculos de check-in, check-out, noches y tarifas
│   ├── views.py             Reservas, check-in, check-out, clientes, calendario y caja base
│   └── urls.py              Rutas del modulo de reservas
│
├── estancias/
│   ├── models.py            Estancias, cargos, folios, pagos, comprobantes y caja
│   ├── forms.py             Formularios de consumos, pagos y filtros de caja
│   ├── views.py             Consumos, pago de folio, comprobantes y reportes de caja
│   └── urls.py              Rutas de estancias, caja y comprobantes
│
├── reportes/
│   ├── views.py             Dashboard y exportacion PDF de reportes
│   ├── forms.py             Filtros de fechas para reportes
│   ├── pdf.py               Generador PDF interno
│   └── urls.py              Rutas de reportes
│
├── templates/
│   ├── base.html            Plantilla base y navbar por rol
│   ├── registration/        Login
│   ├── usuarios/            Dashboards, reservas, calendario, clientes, caja
│   ├── habitaciones/        Habitaciones y cambio de estado
│   ├── estancias/           Consumos, pagos, historial y reporte de caja
│   └── reportes/            Dashboard de reportes
│
├── docker-compose.yml       Servicios Docker: web, db y pgAdmin
├── Dockerfile               Imagen del servicio Django
├── requirements.txt         Dependencias Python
├── manage.py                Comando principal de Django
└── README.md                Instrucciones rapidas del proyecto
```

## 4. Aplicaciones del sistema

### 4.1 App `usuarios`

Controla autenticacion, roles, dashboards y funcionalidades iniciales.

Responsabilidades:

- Redireccionar al usuario segun su rol.
- Mostrar dashboards para Gerencia, Administrador, Recepcion y Limpieza.
- Gestionar maestros administrativos desde pantallas internas.
- Buscar disponibilidad.
- Crear reservas desde la consulta de disponibilidad.
- Crear grupos y permisos con el comando `crear_roles_hotel`.

Roles principales:

- **Gerencia**: ve informacion general, reservas, calendario, reportes y politicas.
- **Administrador / Administracion**: gestiona maestros del sistema: hotel, habitaciones, tipos, tarifas, productos y promociones.
- **Recepcionista / Recepcion**: gestiona reservas, check-in, check-out, caja, consumos, clientes y calendario.
- **Limpieza / Heuspeekin / Housekeeping**: cambia habitaciones de limpieza a disponible o mantenimiento.
- **Cliente**: grupo reservado sin permisos internos por ahora.

Archivos importantes:

- `usuarios/auth.py`: define roles y valida permisos mediante `role_required`.
- `usuarios/context_processors.py`: permite mostrar opciones del navbar segun rol.
- `usuarios/views.py`: dashboards y pantallas administrativas.
- `usuarios/management/commands/crear_roles_hotel.py`: comando formal para crear grupos.

### 4.2 App `hoteles`

Guarda informacion general del hotel.

Modelo principal:

- `Hotel`: nombre, RUC, direccion, estrellas y telefono.

Esta informacion se usa en comprobantes, reportes y datos institucionales.

### 4.3 App `habitaciones`

Gestiona la infraestructura fisica del hotel.

Modelos:

- `TipoHabitacion`: define nombre, capacidad, precio base y amenidades.
- `Habitacion`: define numero, piso, hotel, tipo y estado.
- `ObservacionMantenimiento`: registra observaciones cuando una habitacion pasa a mantenimiento.

Estados de habitacion:

- `DISPONIBLE`
- `OCUPADA`
- `LIMPIEZA`
- `MANTENIMIENTO`

Comando semilla:

```powershell
docker compose exec web python manage.py cargar_datos_hotel
```

Este comando crea cinco tipos de habitacion, sesenta habitaciones y productos/servicios iniciales. Es idempotente, por lo tanto puede ejecutarse varias veces sin duplicar datos.

### 4.4 App `reservas`

Gestiona el ciclo previo y operativo de una reserva.

Modelos:

- `Huesped`: datos del cliente principal.
- `Tarifa`: precio por tipo de habitacion y rango de fechas.
- `Promocion`: descuento comercial por fechas y tipo de habitacion.
- `Reserva`: fecha de entrada, salida, habitacion, huesped, estado y precio.
- `Acompanante`: personas adicionales registradas durante el check-in.

Estados de reserva:

- `PENDIENTE`
- `CONFIRMADA`
- `CHECKIN`
- `CHECKOUT`
- `CANCELADA`

Funciones importantes:

- `lista_reservas`: lista y filtra reservas.
- `calendario_ocupacion`: muestra ocupacion mensual por habitacion.
- `checkin_directo`: registra clientes walk-in sin reserva previa.
- `realizar_checkin`: convierte una reserva en estancia activa.
- `realizar_checkout`: finaliza la estancia si el folio esta pagado.
- `estado_habitaciones`: vista general para recepcion.

Archivo `reservas/services.py`:

Contiene logica de negocio que no deberia estar mezclada con templates:

- Calculo de noches reservadas.
- Calculo de noches reales.
- Evaluacion de check-in normal o anticipado.
- Evaluacion de check-out normal o tardio.
- Aplicacion de penalidades o cargos por politica de cobro.

### 4.5 App `estancias`

Gestiona la estadia real del huesped, consumos y caja.

Modelos:

- `ProductoServicio`: productos o servicios cargables a la habitacion.
- `ConfiguracionCobro`: politica de cobro para checkout.
- `Estancia`: uso real de una habitacion despues del check-in.
- `CargoEstancia`: consumos o cargos adicionales.
- `Folio`: cuenta total de la estancia.
- `MetodoPago`: catalogo de metodos de pago.
- `Pago`: pago parcial o total asociado a un folio.
- `Comprobante`: boleta o factura generada por un pago.
- `MovimientoCaja`: registro contable de ingreso o egreso en caja.

Flujo de caja:

1. El huesped tiene una estancia activa.
2. Se generan cargos de habitacion y consumos.
3. El folio calcula subtotal, IGV y total.
4. Recepcion registra uno o varios pagos.
5. Cada pago genera comprobante.
6. Cada pago genera movimiento de caja.
7. El folio pasa a `PAGADO` si el saldo queda en cero.

Ventaja de la normalizacion:

- `Pago` guarda el abono.
- `Comprobante` guarda el documento fiscal.
- `MovimientoCaja` guarda la trazabilidad de caja.

Separar estas tablas evita duplicidad y facilita reportes.

### 4.6 App `reportes`

Centraliza reportes gerenciales y PDF.

Funciones:

- Dashboard de indicadores.
- Exportacion de reporte hotelero en PDF.
- Generador PDF interno para reportes, boletas y facturas.

Archivo clave:

- `reportes/pdf.py`: construye PDFs sin depender de librerias externas pesadas.

## 5. Flujos principales del sistema

### 5.1 Flujo de inicio de sesion

1. El usuario entra por `/login/`.
2. Django autentica usuario y contrasena.
3. La funcion `inicio` revisa el rol principal.
4. El usuario es enviado a su dashboard:
   - Gerencia: `/gerencia/`
   - Administrador: `/administrador/`
   - Recepcion: `/recepcion/`
   - Limpieza: `/limpieza/`

### 5.2 Flujo de nueva reserva

1. Recepcion consulta disponibilidad en `/disponibilidad/`.
2. El sistema valida fechas y cantidad de personas.
3. Se muestran habitaciones disponibles segun capacidad y ocupacion.
4. Recepcion selecciona habitacion.
5. Se registra huesped y datos de reserva.
6. El sistema evita reservas duplicadas en el mismo rango de fechas.
7. La reserva queda pendiente o confirmada.

### 5.3 Flujo de check-in con reserva

1. Recepcion entra a Check-in.
2. El sistema muestra reservas pendientes.
3. Recepcion confirma el ingreso.
4. Se registra fecha y hora real.
5. Se evalua si el check-in es normal o anticipado.
6. Si es anticipado, se aplica cargo del 5%.
7. Se crea una `Estancia`.
8. Se crea un `Folio`.
9. La habitacion pasa a `OCUPADA`.

### 5.4 Flujo de check-in directo

1. Cliente llega sin reserva.
2. Recepcion usa `checkin-directo`.
3. Se registran datos del huesped.
4. Se selecciona habitacion disponible.
5. Se registran acompanantes si corresponde.
6. Se crea reserva, estancia y folio al mismo tiempo.

### 5.5 Flujo de consumos

1. Recepcion selecciona una estancia activa.
2. Agrega producto o servicio.
3. El consumo se guarda como `CargoEstancia`.
4. El folio recalcula subtotal, IGV y total.

### 5.6 Flujo de check-out

1. Recepcion entra a Check-out.
2. El sistema calcula noches reales y cargos.
3. Se valida politica de cobro:
   - Estadia real.
   - Reserva completa.
   - Estadia real mas penalidad.
4. Si hay saldo pendiente, redirige a Caja.
5. Cuando el folio esta pagado, se finaliza la estancia.
6. La habitacion pasa a `LIMPIEZA`.

### 5.7 Flujo de caja

1. Recepcion abre Caja.
2. Selecciona folio pendiente.
3. Registra metodo de pago, monto y tipo de comprobante.
4. El sistema permite pagos parciales o totales.
5. Se crea `Pago`.
6. Se crea `Comprobante`.
7. Se crea `MovimientoCaja`.
8. Se puede exportar PDF.

### 5.8 Flujo de limpieza y mantenimiento

1. Limpieza ve habitaciones pendientes.
2. Puede marcar una habitacion como disponible.
3. Si encuentra un problema, la envia a mantenimiento.
4. Debe registrar observacion.
5. El sistema guarda historial de observaciones.

### 5.9 Calendario de ocupacion

El calendario se encuentra en:

```text
/reservas/calendario/
```

Muestra habitaciones por filas y dias del mes por columnas.

Permite filtrar por:

- Mes
- Ano
- Tipo de habitacion
- Piso

Estados visuales:

- Disponible
- Reservada
- Ocupada
- Limpieza
- Mantenimiento

## 6. Modelos principales de base de datos

### Hotel

Representa la entidad fiscal y comercial del hotel.

Campos principales:

- `nombre`
- `ruc`
- `direccion`
- `estrellas`
- `telefono`

### TipoHabitacion

Representa una categoria de habitacion.

Campos:

- `nombre`
- `capacidad`
- `precio_base`
- `amenidades`

### Habitacion

Representa una habitacion fisica.

Campos:

- `hotel`
- `tipo`
- `numero`
- `piso`
- `estado`

### Huesped

Representa al cliente principal.

Campos:

- `tipo_doc`
- `num_doc`
- `nombres`
- `apellidos`
- `email`
- `telefono`
- `nacionalidad`

### Reserva

Representa una reserva hecha antes o durante la llegada del cliente.

Campos:

- `hotel`
- `huesped`
- `habitacion`
- `fecha_entrada`
- `fecha_salida`
- `num_adultos`
- `estado`
- `precio_total`
- `origen`

### Acompanante

Representa personas adicionales asociadas a la reserva.

### Estancia

Representa el uso real de la habitacion desde check-in hasta check-out.

Guarda:

- Fecha real de check-in.
- Fecha real de check-out.
- Cargos por early check-in.
- Cargos por late check-out.
- Noches reales.
- Politica aplicada.

### CargoEstancia

Representa consumos o cargos adicionales.

Ejemplos:

- Restaurante.
- Lavanderia.
- Minibar.
- Penalidad.
- Early check-in.
- Late check-out.

### Folio

Representa la cuenta de la estancia.

Calcula:

- Subtotal.
- IGV.
- Total.
- Total pagado.
- Saldo pendiente.

### Pago

Representa un pago parcial o total.

Campos:

- `folio`
- `metodo_pago`
- `monto`
- `numero_operacion`
- `estado`
- `usuario_responsable`

### Comprobante

Representa boleta o factura emitida.

Campos:

- `pago`
- `tipo`
- `serie`
- `numero`
- `cliente_documento`
- `cliente_nombre`
- `estado`
- `fecha_emision`

### MovimientoCaja

Representa un movimiento financiero.

Campos:

- `pago`
- `tipo`
- `concepto`
- `monto`
- `metodo_pago`
- `usuario_responsable`
- `fecha`

## 7. Rutas principales

### Usuarios

```text
/login/
/logout/
/
/gerencia/
/administrador/
/recepcion/
/limpieza/
/disponibilidad/
/reservas/nueva/
```

### Reservas

```text
/reservas/
/reservas/calendario/
/reservas/clientes/
/reservas/checkin-directo/
/reservas/checkin-pendientes/
/reservas/checkout-pendientes/
/reservas/caja/
/reservas/estado-habitaciones/
/reservas/checkin/<id>/
/reservas/checkout/<id>/
```

### Estancias y caja

```text
/estancias/
/estancias/configuracion-cobro/
/estancias/caja/historial-pagos/
/estancias/caja/reporte-diario/
/estancias/folios/<id>/pagar/
/estancias/comprobantes/<id>/pdf/
/estancias/<id>/consumos/
```

### Habitaciones

```text
/habitaciones/
/habitaciones/cambiar-estado/<id>/
```

### Reportes

```text
/reportes/
/reportes/pdf/
```

## 8. Docker y base de datos

El proyecto usa Docker Compose para levantar tres servicios:

- `web`: aplicacion Django.
- `db`: PostgreSQL 16.
- `pgadmin`: interfaz grafica para administrar PostgreSQL.

Archivo:

```text
docker-compose.yml
```

Credenciales de PostgreSQL en desarrollo:

```text
Base de datos: sistema_hotelero_db
Usuario: postgres
Password: postgres
Host interno Docker: db
Puerto: 5432
```

Credenciales de pgAdmin:

```text
URL: http://localhost:5050
Email: admin@admin.com
Password: admin
```

## 9. Comandos importantes

Ejecutar proyecto:

```powershell
docker compose up --build
```

Aplicar migraciones:

```powershell
docker compose exec web python manage.py migrate
```

Crear superusuario:

```powershell
docker compose exec web python manage.py createsuperuser
```

Crear grupos y permisos:

```powershell
docker compose exec web python manage.py crear_roles_hotel
```

Cargar datos semilla:

```powershell
docker compose exec web python manage.py cargar_datos_hotel
```

Validar proyecto:

```powershell
docker compose exec web python manage.py check
```

## 10. Diccionario tecnico para sustentacion

### App

Modulo independiente dentro de Django. Cada app agrupa una funcionalidad, por ejemplo reservas, habitaciones o caja.

### Modelo

Clase de Python que representa una tabla en la base de datos.

### Campo

Atributo de un modelo. Representa una columna de la tabla.

### ForeignKey

Relacion de muchos a uno. Ejemplo: muchas habitaciones pertenecen a un hotel.

### OneToOneField

Relacion de uno a uno. Ejemplo: una estancia tiene un folio.

### QuerySet

Conjunto de registros consultados desde la base de datos usando el ORM de Django.

### ORM

Herramienta de Django que permite consultar la base de datos usando Python en lugar de SQL directo.

### Vista

Funcion que recibe una solicitud web, procesa datos y devuelve una respuesta HTML o PDF.

### Template

Archivo HTML que se renderiza con datos enviados desde una vista.

### URL

Ruta que conecta una direccion web con una vista.

### Form

Clase que valida datos enviados por el usuario antes de procesarlos.

### ModelForm

Formulario basado directamente en un modelo. Facilita crear o editar registros.

### Decorador

Funcion que envuelve otra funcion para agregar comportamiento. En el proyecto se usa `role_required` para validar permisos.

### role_required

Decorador propio del sistema. Permite que solo ciertos roles entren a una vista.

### Context processor

Funcion que agrega variables globales a los templates. Se usa para saber si el usuario es gerente, administrador, recepcionista o limpieza.

### Migracion

Archivo que describe cambios en la base de datos. Django lo usa para crear o modificar tablas.

### Docker

Herramienta para ejecutar el sistema en contenedores, evitando problemas de configuracion local.

### Docker Compose

Archivo y comando para levantar varios servicios juntos: Django, PostgreSQL y pgAdmin.

### PostgreSQL

Sistema gestor de base de datos usado por el proyecto.

### pgAdmin

Interfaz grafica para revisar la base de datos PostgreSQL.

### Folio

Cuenta de la estancia. Agrupa habitacion, consumos, impuestos, pagos y saldo.

### Estancia

Uso real de una habitacion por parte del huesped. Empieza en check-in y termina en check-out.

### Check-in

Ingreso del huesped. En el sistema crea una estancia, cambia habitacion a ocupada y crea folio.

### Check-out

Salida del huesped. En el sistema calcula cargos, valida pago y envia habitacion a limpieza.

### Early check-in

Ingreso antes de la hora oficial. El sistema aplica cargo del 5%.

### Late check-out

Salida despues de la hora oficial. El sistema aplica cargo del 50%.

### CargoEstancia

Consumo o cargo adicional agregado a la estancia.

### Pago

Abono parcial o total que se registra sobre un folio.

### Comprobante

Documento emitido por un pago. Puede ser boleta o factura.

### MovimientoCaja

Registro financiero que permite construir reportes de caja.

### Idempotente

Un proceso que puede ejecutarse varias veces sin duplicar informacion. El comando `cargar_datos_hotel` es idempotente.

### Datos semilla

Datos iniciales para empezar a usar el sistema, como tipos de habitacion, habitaciones y productos.

### Template base

Plantilla principal `base.html`. Define estructura comun, navbar y estilos compartidos.

### Navbar por rol

Menu que cambia segun el grupo del usuario autenticado.

### PDF

Archivo exportable usado para reportes, boletas y facturas.

## 11. Argumentos para sustentar decisiones tecnicas

### Por que se separo Reserva de Estancia

Porque una reserva representa una intencion o plan, mientras que una estancia representa el uso real de la habitacion. Esto permite calcular el monto final segun fechas y horas reales.

### Por que se separo Pago, Comprobante y MovimientoCaja

Porque cada uno cumple una responsabilidad distinta:

- `Pago`: dinero recibido.
- `Comprobante`: documento emitido.
- `MovimientoCaja`: trazabilidad financiera.

Esto mejora normalizacion, evita duplicidad y facilita reportes.

### Por que se usa Docker

Para que el proyecto funcione igual en cualquier maquina sin depender de configuraciones locales. Docker levanta Django, PostgreSQL y pgAdmin con un solo comando.

### Por que existen comandos de management

Porque crear roles y datos semilla es una tarea formal del sistema. No se dejaron scripts sueltos, sino comandos integrados a Django.

### Por que se usa PostgreSQL

Porque es una base de datos robusta y mas adecuada para un sistema real que SQLite.

### Por que hay roles

Porque un hotel tiene areas con responsabilidades distintas. No todos los usuarios deben acceder a caja, configuracion o limpieza.

## 12. Estado actual del proyecto

El sistema cuenta con:

- Gestion de usuarios por rol.
- Gestion de hotel, habitaciones, tipos, tarifas, productos y promociones.
- Busqueda de disponibilidad.
- Reservas con validacion de capacidad.
- Registro de clientes y acompanantes.
- Check-in normal, anticipado y directo.
- Check-out normal y tardio.
- Calculo por estancia real.
- Politica configurable de cobro.
- Consumos a habitacion.
- Caja con pagos parciales y totales.
- Boleta y factura en PDF.
- Movimiento de caja.
- Reporte diario de caja.
- Reportes gerenciales.
- Calendario de ocupacion.
- Limpieza y mantenimiento con observaciones.
- API REST con autenticacion JWT.
- Documentacion Swagger/OpenAPI.
- Tests de disponibilidad, reservas y check-in/check-out.
- Docker y PostgreSQL.

## 13. API REST, JWT y Swagger

Para cumplir con la capa de integracion solicitada en la rubrica, el sistema incluye una app llamada `api`. Esta app no reemplaza las pantallas web; funciona como una capa adicional para que otros clientes puedan consumir datos del sistema.

### Archivos principales

- `api/serializers.py`: convierte modelos Django a JSON y valida datos recibidos por la API.
- `api/views.py`: contiene los endpoints REST para habitaciones, reservas, estancias, folios, housekeeping y reportes.
- `api/urls.py`: registra las rutas `/api/`.
- `api/tests.py`: contiene pruebas automaticas de reglas criticas.

### Autenticacion JWT

La API usa JSON Web Token. Primero se solicita un token con usuario y contrasena:

```text
POST /api/auth/token/
```

Luego el cliente consume endpoints enviando el token en la cabecera:

```text
Authorization: Bearer <token>
```

### Swagger

La documentacion navegable de la API esta disponible en:

```text
/api/docs/
```

El esquema OpenAPI esta disponible en:

```text
/api/schema/
```

### Endpoints implementados

- `GET /api/habitaciones/disponibles/`: consulta habitaciones disponibles por fechas, tipo y numero de personas.
- `POST /api/reservas/`: crea reservas calculando tarifa vigente.
- `POST /api/reservas/{id}/checkin/`: registra check-in y crea estancia y folio.
- `POST /api/estancias/{id}/checkout/`: valida deuda, finaliza estancia y pasa habitacion a limpieza.
- `POST /api/estancias/{id}/cargos/`: agrega cargos adicionales al folio.
- `GET /api/estancias/{id}/folio/`: consulta folio con cargos y saldo.
- `PATCH /api/habitaciones/{id}/housekeeping/`: actualiza estado de limpieza o mantenimiento.
- `GET /api/reportes/ocupacion/`: devuelve ocupacion y revenue del dia.

## 14. Pruebas automaticas

El proyecto incluye pruebas en `api/tests.py` para validar reglas de negocio importantes:

- Una habitacion con reserva solapada no aparece como disponible.
- La reserva calcula precio usando tarifa vigente.
- El check-in bloquea habitaciones en mantenimiento.
- El check-out no se permite si el folio tiene deuda.
- Al finalizar check-out, la habitacion pasa a limpieza.

Comando para ejecutar las pruebas:

```bash
docker compose exec -T web python manage.py test api
```
