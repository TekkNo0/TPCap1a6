import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
import bcrypt
import jwt

# Semáforo para limitar la concurrencia de llamadas a bcrypt (operación intensiva de CPU)
# evitando saturar el bucle de eventos o los hilos de trabajo (sección 5.6).
_BCRYPT_SEMAPHORE = asyncio.Semaphore(4)


def _hash_sync(password: str, rounds: int) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def _verify_sync(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


async def hash_password(password: str, rounds: int = 12) -> str:
    """Calcula el hash con bcrypt fuera del bucle de eventos y bajo semáforo."""
    async with _BCRYPT_SEMAPHORE:
        return await asyncio.to_thread(_hash_sync, password, rounds)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña con bcrypt fuera del bucle de eventos y bajo semáforo."""
    async with _BCRYPT_SEMAPHORE:
        return await asyncio.to_thread(_verify_sync, plain_password, hashed_password)


async def generate_dummy_hash(rounds: int = 12) -> str:
    """Genera un hash ficticio para mitigar ataques de temporización en login inexistente."""
    return await hash_password("dummy-password-for-timing", rounds=rounds)


def crear_token_jwt(
    usuario_id: int,
    email: str,
    roles: list[str],
    secret_key: str,
    algorithm: str = "HS256",
    expira_minutos: int = 60,
) -> tuple[str, float, int]:
    """Emite un token JWT firmado.

    El iat lleva la hora completa con microsegundos (sin truncar a segundos) para que
    pueda distinguirse con precisión frente a un cambio de contraseña inmediato (RN-07 / 5.10).
    Retorna (token_jwt, iat_flotante, segundos_expiracion).
    """
    ahora = datetime.now(timezone.utc)
    duracion = timedelta(minutes=expira_minutos)
    exp = ahora + duracion

    iat_ts = ahora.timestamp()  # Flotante con microsegundos
    exp_ts = exp.timestamp()
    segundos_exp = int(duracion.total_seconds())

    payload = {
        "sub": str(usuario_id),
        "email": email,
        "roles": roles,
        "iat": iat_ts,
        "exp": exp_ts,
    }

    token = jwt.encode(payload, secret_key, algorithm=algorithm)
    return token, iat_ts, segundos_exp


def decodificar_token_jwt(
    token: str,
    secret_key: str,
    algorithm: str = "HS256",
) -> dict[str, Any]:
    """Decodifica y valida la firma y expiración de un JWT."""
    return jwt.decode(token, secret_key, algorithms=[algorithm])
