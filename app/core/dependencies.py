from datetime import datetime, timezone
from typing import Callable, Sequence
from fastapi import Depends, HTTPException, Request, status
import jwt
from sqlalchemy import or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import decodificar_token_jwt
from app.modules.usuarios.models import AsignacionRol, Usuario


async def obtener_roles_vigentes_usuario(
    usuario_id: int,
    session: AsyncSession,
) -> list[str]:
    """Consulta en la base de datos los roles vigentes del usuario en cada petición (RN-04).

    Un rol está vigente si:
    - revocada_en IS NULL
    - vence_en IS NULL o vence_en > ahora
    """
    ahora = datetime.now(timezone.utc)
    stmt = (
        select(AsignacionRol.rol)
        .where(
            AsignacionRol.usuario_id == usuario_id,
            AsignacionRol.revocada_en.is_(None),
            or_(AsignacionRol.vence_en.is_(None), AsignacionRol.vence_en > ahora),
        )
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_usuario_actual(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Usuario:
    """Extrae y valida el token JWT exclusivamente desde la cookie access_token.

    Responde HTTP 401 si:
    - No existe la cookie
    - El token está vencido o la firma es inválida
    - El usuario no existe o está inactivo
    - El token fue emitido antes del último cambio de contraseña (RN-07).
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado: falta la cookie de sesión access_token.",
        )

    settings = get_settings()
    try:
        payload = decodificar_token_jwt(
            token,
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión ha expirado. Por favor ingrese nuevamente.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación inválido.",
        )

    usuario_id = int(payload.get("sub", 0))
    usuario = await session.get(Usuario, usuario_id)
    if not usuario or not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inexistente o inactivo.",
        )

    # RN-07 / 5.10: El token anterior al último cambio de contraseña no es válido
    if usuario.password_cambiada_en is not None:
        token_iat = float(payload.get("iat", 0.0))
        cambio_ts = usuario.password_cambiada_en.timestamp()
        if token_iat < cambio_ts:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sesión invalidada por cambio de contraseña posterior.",
            )

    # Almacenar payload para uso en /auth/yo
    request.state.token_payload = payload
    return usuario


async def verificar_cambio_password_no_pendiente(
    usuario: Usuario = Depends(get_usuario_actual),
) -> Usuario:
    """Bloquea cualquier ruta del grupo protegido si el usuario debe cambiar su contraseña (RN-06)."""
    if usuario.debe_cambiar_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debe cambiar su contraseña obligatoriamente antes de continuar.",
        )
    return usuario


def requiere_rol(*roles_permitidos: str) -> Callable:
    """Genera una dependencia que autoriza sólo si el usuario posee al menos uno de los roles vigentes en la BD."""

    async def dependencia_rol(
        usuario: Usuario = Depends(get_usuario_actual),
        session: AsyncSession = Depends(get_session),
    ) -> Usuario:
        roles_vigentes = await obtener_roles_vigentes_usuario(
            usuario.id,  # type: ignore[arg-type]
            session,
        )
        if not any(r in roles_vigentes for r in roles_permitidos):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado: se requiere uno de los siguientes roles: {', '.join(roles_permitidos)}",
            )
        return usuario

    return dependencia_rol
