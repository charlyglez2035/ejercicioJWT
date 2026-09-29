import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from functools import wraps

import jwt
import psycopg
from flask import g, jsonify, request


class InvalidToken(Exception):
    pass


class RevocationStoreUnavailable(Exception):
    pass


class JWTConfigurationError(Exception):
    pass


def jwt_settings():
    secret = os.getenv("JWT_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise JWTConfigurationError(
            "JWT_SECRET debe tener al menos 32 bytes y configurarse por entorno."
        )
    issuer = os.getenv("JWT_ISSUER", "library-login")
    audience = os.getenv("JWT_AUDIENCE", "library-book")
    try:
        expires_in = int(os.getenv("JWT_EXPIRES_IN_SECONDS", "900"))
    except ValueError as error:
        raise JWTConfigurationError("JWT_EXPIRES_IN_SECONDS debe ser un entero positivo.") from error
    if not issuer or not audience or expires_in < 1:
        raise JWTConfigurationError("JWT issuer, audience y duracion deben configurarse.")
    return {
        "secret": secret,
        "issuer": issuer,
        "audience": audience,
        "expires_in": expires_in,
    }


def issue_token(user_id):
    settings = jwt_settings()
    issued_at = int(time.time())
    claims = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + settings["expires_in"],
        "iss": settings["issuer"],
        "aud": settings["audience"],
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, settings["secret"], algorithm="HS256"), claims


def _db_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "library"),
        user=os.getenv("DB_USER", "library_user"),
        password=os.getenv("DB_PASSWORD", ""),
        connect_timeout=5,
    )


def _is_revoked(jti):
    try:
        with _db_connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM jwt_revocation WHERE jti = %s AND expires_at > CURRENT_TIMESTAMP",
                (jti,),
            ).fetchone()
            return row is not None
    except psycopg.Error as error:
        raise RevocationStoreUnavailable() from error


def decode_token(token):
    settings = jwt_settings()
    try:
        claims = jwt.decode(
            token,
            settings["secret"],
            algorithms=["HS256"],
            issuer=settings["issuer"],
            audience=settings["audience"],
            options={"require": ["sub", "iat", "exp", "iss", "aud", "jti"]},
        )
    except (jwt.PyJWTError, TypeError, ValueError) as error:
        raise InvalidToken() from error
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise InvalidToken()
    if not isinstance(claims.get("jti"), str) or not claims["jti"]:
        raise InvalidToken()
    if _is_revoked(claims["jti"]):
        raise InvalidToken()
    return claims


def bearer_claims():
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise InvalidToken()
    return decode_token(token.strip())


def revoke_token(claims):
    expires_at = datetime.fromtimestamp(int(claims["exp"]), timezone.utc)
    try:
        with _db_connection() as connection:
            connection.execute(
                "DELETE FROM jwt_revocation WHERE expires_at <= CURRENT_TIMESTAMP"
            )
            connection.execute(
                """INSERT INTO jwt_revocation (jti, expires_at)
                   VALUES (%s, %s)
                   ON CONFLICT (jti) DO UPDATE SET expires_at = EXCLUDED.expires_at""",
                (claims["jti"], expires_at),
            )
    except psycopg.Error as error:
        raise RevocationStoreUnavailable() from error


_SECRET_KEY_PATTERN = re.compile(
    r"(authorization|cookie|password|token|secret|api[-_]?key|credential)",
    re.IGNORECASE,
)
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def sanitize(value, key=""):
    if _SECRET_KEY_PATTERN.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {name: sanitize(item, name) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return _JWT_PATTERN.sub("[REDACTED]", value)
    return value


def install_request_logging(app):
    @app.before_request
    def start_request_log():
        g.request_id = request.headers.get("X-Request-ID", "").strip() or str(uuid.uuid4())
        g.request_started = time.perf_counter()

    @app.after_request
    def finish_request_log(response):
        response.headers["X-Request-ID"] = g.get("request_id", str(uuid.uuid4()))
        elapsed_ms = round((time.perf_counter() - g.get("request_started", time.perf_counter())) * 1000, 2)
        body = request.get_json(silent=True)
        response_body = response.get_json(silent=True)
        record = {
            "request_id": response.headers["X-Request-ID"],
            "service": app.name,
            "method": request.method,
            "url": request.base_url,
            "headers": sanitize({
                "content-type": request.headers.get("Content-Type"),
                "accept": request.headers.get("Accept"),
                "authorization": request.headers.get("Authorization"),
                "cookie": request.headers.get("Cookie"),
            }),
            "payload": sanitize(body),
            "status": response.status_code,
            "duration_ms": elapsed_ms,
            "response": sanitize(response_body),
        }
        app.logger.info("request %s", json.dumps(record, ensure_ascii=False, default=str))
        return response


def token_error_response():
    return jsonify(error="Bearer token ausente, invalido, expirado o revocado."), 401


def require_bearer(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            g.jwt_claims = bearer_claims()
        except InvalidToken:
            return token_error_response()
        except RevocationStoreUnavailable:
            logging.getLogger(__name__).exception("No se pudo consultar la revocacion JWT")
            return jsonify(error="No se pudo validar la sesion."), 503
        except JWTConfigurationError:
            logging.getLogger(__name__).exception("La configuracion JWT no es valida")
            return jsonify(error="El servicio no tiene JWT configurado correctamente."), 503
        return function(*args, **kwargs)
    return wrapped