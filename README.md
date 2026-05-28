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

## Base de datos

El proyecto esta configurado para PostgreSQL usando Docker Compose. La base local `db.sqlite3` no forma parte de la entrega final.

Los valores de desarrollo para la conexion a PostgreSQL estan definidos como valores por defecto en `config/settings.py` y coinciden con el servicio `db` de `docker-compose.yml`.
