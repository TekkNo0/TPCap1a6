from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, FastAPI

from app.core.config import get_settings
from app.core.database import create_db_engine, create_session_factory
from app.core.dependencies import verificar_cambio_password_no_pendiente
from app.core.security import generate_dummy_hash

# Importar todos los modelos para inicializar el registro declarativo de SQLAlchemy
import app.modules.usuarios.models  # noqa: F401
import app.modules.clientes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401

from app.modules.health.router import router as health_router
from app.modules.repuestos.router import router as repuestos_router
from app.modules.clientes.router import router as clientes_router
from app.modules.usuarios.router import auth_router, usuarios_router
from app.modules.ordenes.router import router as ordenes_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Ciclo de vida de la aplicación FastAPI.

    Crea el motor asincrónico y la fábrica de sesiones dentro del bucle de eventos
    y los almacena en app.state para evitar errores de inicialización temprana (EA-08).
    Calcula además el hash ficticio para mitigar ataques de temporización en login.
    Al apagarse, libera ordenadamente los recursos del motor con dispose().
    """
    settings = get_settings()

    # 1. Crear motor y fábrica de sesiones asincrónicas
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory

    # 2. Calcular una única vez el hash ficticio para comparaciones constantes de login (RN-09)
    app.state.dummy_hash = await generate_dummy_hash(settings.BCRYPT_ROUNDS)

    yield

    # 3. Cierre ordenado de conexiones al apagar
    await engine.dispose()


app = FastAPI(
    title="Taller Mecánico API",
    version="1.0.0",
    description="Sistema de gestión de órdenes de trabajo, repuestos y usuarios",
    lifespan=lifespan,
)

# Dos grupos de rutas obligatorios
api_abierta = APIRouter()
api_protegida = APIRouter(dependencies=[Depends(verificar_cambio_password_no_pendiente)])

# Inclusión de routers en el grupo abierto
api_abierta.include_router(health_router)
api_abierta.include_router(auth_router)

# Inclusión de routers en el grupo protegido (control de cambio obligatorio montado una sola vez)
api_protegida.include_router(usuarios_router)
api_protegida.include_router(clientes_router)
api_protegida.include_router(repuestos_router)
api_protegida.include_router(ordenes_router)

# Registro de grupos en la aplicación principal
app.include_router(api_abierta)
app.include_router(api_protegida)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
