# Sistema Hotelero

Proyecto Django para gestion hotelera con roles, reservas, check-in/check-out, caja, comprobantes, limpieza, mantenimiento y reportes.

## Ejecucion con Docker

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

## Comandos de inicializacion

Estos comandos forman parte de la arquitectura del proyecto y viven dentro de `management/commands`.

Crear grupos y permisos operativos:

```powershell
docker compose exec web python manage.py crear_roles_hotel
```

Cargar datos semilla del hotel:

```powershell
docker compose exec web python manage.py cargar_datos_hotel
```

El comando de datos semilla requiere que exista al menos un hotel registrado. Crea tipos de habitacion, 60 habitaciones distribuidas en 6 pisos y productos/servicios frecuentes. Es idempotente: puede ejecutarse mas de una vez sin duplicar informacion.

## Automatizacion operativa de reservas

Simular garantias vencidas y no-show sin modificar datos:

```powershell
docker compose exec web python manage.py procesar_reservas_operativas --dry-run
```

Ejecutar una revision inmediata:

```powershell
docker compose exec web python manage.py procesar_reservas_operativas
```

Mantener la automatizacion activa en otra terminal, revisando cada cinco minutos:

```powershell
docker compose exec web python manage.py procesar_reservas_operativas --continuo --intervalo 300
```

El comando es idempotente: una reserva ya cancelada o marcada como no-show no vuelve a procesarse. Los eventos de reservas, habitaciones, adelantos, cargos y pagos se escriben en la salida de Docker sin incluir contrasenas, documentos ni datos personales. Pueden consultarse con:

```powershell
docker compose logs -f web
```

## Base de datos

El proyecto esta configurado para PostgreSQL usando Docker Compose. La base local `db.sqlite3` no forma parte de la entrega final.

Los valores de desarrollo para la conexion a PostgreSQL estan definidos como valores por defecto en `config/settings.py` y coinciden con el servicio `db` de `docker-compose.yml`.
