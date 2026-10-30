from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def health_live() -> dict[str, str | bool]:
    """Indica si el servidor de aplicaciones está vivo y atendiendo peticiones.

    No consulta la base de datos para no saturarla ni fallar si la base está temporalmente caída.
    """
    return {"status": "ok", "live": True}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def health_ready(session: AsyncSession = Depends(get_session)) -> dict[str, str | bool]:
    """Indica si la aplicación está lista para procesar trabajo real.

    Ejecuta 'SELECT 1' en la base de datos. Si la conexión falla, responde HTTP 503.
    """
    try:
        result = await session.execute(text("SELECT 1"))
        _ = result.scalar()
        return {"status": "ok", "ready": True, "database": "connected"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La base de datos no se encuentra disponible.",
        ) from exc
