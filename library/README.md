# Libreria web y servicios JWT

Aplicacion Node.js MVC con PostgreSQL y microservicios Flask para login y libros. El catalogo conserva sus formularios; `/jwt-demo` demuestra consultas publicas y escrituras protegidas con JWT en el microservicio book.

## Modelo

`db/scheme.sql` normaliza libros, autores, generos, conceptos, imagenes, formatos, categorias y usuarios. Las dependencias multivaluadas se resuelven con `book_author`, `book_genre`, `book_concept` y `book_image`. `book_concept` conserva una definicion distinta por libro y el indice parcial `one_admin_only_idx` limita a un administrador.

## Ejecucion local en WSL

Instala los paquetes del sistema y PostgreSQL si aun no estan disponibles:

```bash
sudo apt update
sudo apt install -y nodejs npm python3 python3-pip python3-venv python3-tk postgresql postgresql-client
```

PostgreSQL local de WSL usa el puerto `5432`; si no esta iniciado, arranca el servicio con `sudo service postgresql start`.

Desde `library/`, configura las variables locales y una clave JWT aleatoria compartida solo por los dos servicios Flask:

```bash
cp .env.example .env
cp apps/services/login/.env.example apps/services/login/.env
cp apps/services/soap/.env.example apps/services/soap/.env
python3 -c 'import secrets; print("JWT_SECRET=" + secrets.token_urlsafe(48)); print("SESSION_SECRET=" + secrets.token_urlsafe(48))'
# Guarda JWT_SECRET (mismo valor) en los dos .env de servicios y SESSION_SECRET en .env raiz.
```

Aplica el esquema inicial si la base aun no existe y luego la migracion aditiva:

```bash
psql -h localhost -p 5432 -U library_user -d library -f db/scheme.sql
psql -h localhost -p 5432 -U library_user -d library -f db/jwt-revocations.sql
```

Instala dependencias Python y Node:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r apps/services/login/requirements.txt
python3 -m pip install -r apps/services/soap/requirements.txt
npm install
```

Abre tres terminales WSL, todas desde `library/`:

```bash
python3 apps/services/login/app.py
```

```bash
python3 apps/services/soap/app.py
```

```bash
npm start
```

Visita `http://localhost:3000/jwt-demo`. El cliente Tkinter se inicia con `python3 apps/Python_app/tkinter_client.py`; URLs de login y book se pueden cambiar desde la ventana. Tkinter consume HTTP y no se conecta a PostgreSQL.

## Configuracion

`JWT_SECRET` es obligatorio y debe ser una clave aleatoria de al menos 32 bytes, igual en `apps/services/login/.env` y `apps/services/soap/.env`. Copia los `.env.example` de ambos servicios y pega en ellos el mismo valor generado; Express no necesita ni recibe esa clave. No existe secreto de respaldo. `JWT_ISSUER`, `JWT_AUDIENCE` y `JWT_EXPIRES_IN_SECONDS` deben coincidir. Las variables PostgreSQL viven en el `.env` raíz. Ningun `.env` se versiona.

`DB_PASSWORD` en el `.env` raíz no puede quedar vacío: debe coincidir con la contraseña PostgreSQL de `DB_USER` (por defecto `library_user`). El monolito y ambos servicios Flask leen esas variables desde ese archivo.

La tabla `jwt_revocation` debe existir antes de iniciar login y book. Ejecuta `db/jwt-revocations.sql` una sola vez; conserva datos y no requiere modificar libros.

## Endpoints

- Publicos: `POST /register`, `POST /login`, `GET /health`, `GET /api/books`, `GET /api/books/{isbn}` y equivalentes publicos `/books`.
- Requieren `Authorization: Bearer <token>`: `GET /session`, `POST /logout`, `POST /api/books`, `PUT/PATCH/DELETE /api/books/{isbn}` y sus alias `/books`.
- `OPTIONS` queda publico. `session` y `logout` requieren un token valido; logout persiste la revocacion por `jti` hasta su expiracion.
- La web actua como proxy y conserva el JWT en la sesion de Express; nunca lo entrega al navegador. La consola muestra respuestas reales de los microservicios y redacta credenciales.

Registro sigue usando los campos `nombre`, `apellido_paterno`, `apellido_materno`, `email` y `password`; el inicio de sesion usa `identity` y `password`. El registro exige verificacion de correo segun la configuracion SMTP existente.

## Estructura

- `apps/web-monolito/src/server.js`: composicion del monolito y proxy JWT.
- `apps/web-monolito/src/routes`: controladores HTTP MVC.
- `apps/web-monolito/views`: vistas EJS.
- `apps/web-monolito/public`: estilos y cargas de imagenes.
- `apps/services/shared/jwt_security.py`: emision, validacion, revocacion y sanitizacion compartidas.
- `db/scheme.sql`: esquema PostgreSQL inicial.
- `db/jwt-revocations.sql`: migracion aditiva de revocacion.

