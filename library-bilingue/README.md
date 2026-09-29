# Libreria web monolitica

Aplicacion Node.js con renderizado HTML del lado del servidor, arquitectura MVC modular y acceso directo a PostgreSQL mediante `pg`. No expone APIs REST/GraphQL ni usa JSON/XML como formato de intercambio: los cambios se realizan con formularios HTML y redirecciones HTTP.

## Modelo

`db/scheme.sql` normaliza libros, autores, generos, conceptos, imagenes, formatos, categorias y usuarios. Las dependencias multivaluadas se resuelven con `book_author`, `book_genre`, `book_concept` y `book_image`. `book_concept` conserva una definicion distinta por libro y el indice parcial `one_admin_only_idx` limita a un administrador.

## Despliegue en CentOS Stream 10

1. Instala Node.js 22 o superior y las herramientas de compilacion:

```bash
sudo dnf install -y nodejs npm gcc-c++ make
```

2. Copia el proyecto al servidor y prepara PostgreSQL. Asumiendo la base y usuario indicados:

```bash
cd library
psql -h localhost -U library_user -d library_db -f db/scheme.sql
npm install --omit=dev
```

3. Configura variables de entorno. La aplicacion usa estos valores por defecto, pero se recomienda definirlos:

```bash
export PORT=3000
export SESSION_SECRET='library-secret-2026'
export DB_HOST=localhost
export DB_PORT=5433
export DB_NAME=library
export DB_USER=library_user
export DB_PASSWORD=library666
```

4. Inicia el servidor:

```bash
npm start
```

Abre `http://servidor:3000`. Crea una cuenta desde `/register`; para convertirla en administrador, un administrador existente puede cambiar su rol en `/admin/users`. La restriccion de PostgreSQL impide que haya mas de uno.

Para operar como servicio systemd, crea `/etc/systemd/system/library.service` con `User`, `WorkingDirectory`, `EnvironmentFile` y `ExecStart=/usr/bin/node apps/web-monolito/src/server.js`; despues ejecuta `sudo systemctl daemon-reload && sudo systemctl enable --now library`.

## Estructura

- `apps/web-monolito/src/server.js`: composicion del monolito.
- `apps/web-monolito/src/routes`: controladores HTTP MVC.
- `apps/web-monolito/views`: vistas EJS.
- `apps/web-monolito/public`: estilos y cargas de imagenes.
- `db/scheme.sql`: esquema PostgreSQL.
