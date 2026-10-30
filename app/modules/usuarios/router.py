from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.dependencies import (
    get_usuario_actual,
    obtener_roles_vigentes_usuario,
    requiere_rol,
)
from app.core.exceptions import (
    ConflictoError,
    RecursoNoEncontradoError,
    traducir_error_integridad,
)
from app.core.paginacion import Pagina
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.schemas import (
    AsignacionRolResponse,
    AsignarRolRequest,
    CambiarPasswordRequest,
    EventoSeguridadResponse,
    LoginRequest,
    LoginResponse,
    RegistroRequest,
    UsuarioPersonalCreate,
    UsuarioResponse,
    UsuarioYoResponse,
)
from app.modules.usuarios.service import UsuarioService
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork

auth_router = APIRouter(prefix="/auth", tags=["Autenticación"])
usuarios_router = APIRouter(tags=["Usuarios y Seguridad"])


def get_usuario_service(
    session: AsyncSession = Depends(get_session),
) -> UsuarioService:
    """Construye el Unit of Work y el Servicio de Usuarios."""
    uow = UsuariosUnitOfWork(session)
    return UsuarioService(uow)


def _set_auth_cookie(response: Response, token: str, max_age: int) -> None:
    """Configura la cookie access_token con HttpOnly y SameSite=Lax (sección 5.3)."""
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )


# -----------------------------------------------------------------------------
# RUTAS ABIERTAS (AUTH)
# -----------------------------------------------------------------------------

@auth_router.post("/registro", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def registro_cliente(
    datos: RegistroRequest,
    service: UsuarioService = Depends(get_usuario_service),
) -> UsuarioResponse:
    """Autorregistro público para nuevos clientes (RN-02)."""
    try:
        usuario = await service.registrar_cliente(datos)
        return UsuarioResponse.model_validate(usuario)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)
    except IntegrityError as exc:
        raise traducir_error_integridad(exc)


@auth_router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    datos: LoginRequest,
    request: Request,
    response: Response,
    service: UsuarioService = Depends(get_usuario_service),
) -> LoginResponse:
    """Inicio de sesión. El token viaja exclusivamente en Set-Cookie (HttpOnly)."""
    ip = request.client.host if request.client else "127.0.0.1"
    dummy_hash = getattr(request.app.state, "dummy_hash", "$2b$12$dummyhashforauthentication")
    session_factory = request.app.state.session_factory

    usuario, token, exp_seg = await service.login(
        datos=datos,
        ip=ip,
        dummy_hash=dummy_hash,
        session_factory=session_factory,
    )

    _set_auth_cookie(response, token, exp_seg)
    return LoginResponse(
        mensaje="Sesión iniciada",
        debe_cambiar_password=usuario.debe_cambiar_password,
        expira_en_segundos=exp_seg,
    )


@auth_router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response) -> dict[str, str]:
    """Cierra la sesión borrando la cookie access_token."""
    response.delete_cookie(key="access_token", path="/")
    return {"mensaje": "Sesión cerrada exitosamente"}


@auth_router.get("/yo", response_model=UsuarioYoResponse, status_code=status.HTTP_200_OK)
async def obtener_perfil_yo(
    request: Request,
    usuario: Usuario = Depends(get_usuario_actual),
    session: AsyncSession = Depends(get_session),
) -> UsuarioYoResponse:
    """Retorna los datos del usuario autenticado, roles vigentes en la BD y roles en el token."""
    roles_bd = await obtener_roles_vigentes_usuario(
        usuario.id,  # type: ignore[arg-type]
        session,
    )
    payload = getattr(request.state, "token_payload", {})
    roles_token = payload.get("roles", [])

    return UsuarioYoResponse(
        usuario=UsuarioResponse.model_validate(usuario),
        roles_vigentes_bd=roles_bd,
        roles_en_token=roles_token,
    )


@auth_router.post("/cambiar-password", status_code=status.HTTP_200_OK)
async def cambiar_password(
    datos: CambiarPasswordRequest,
    response: Response,
    usuario: Usuario = Depends(get_usuario_actual),
    service: UsuarioService = Depends(get_usuario_service),
) -> dict[str, str]:
    """Cambia la contraseña del usuario y actualiza la cookie con un token nuevo (RN-07)."""
    _, nuevo_token, exp_seg = await service.cambiar_password(
        usuario_id=usuario.id,  # type: ignore[arg-type]
        datos=datos,
    )
    _set_auth_cookie(response, nuevo_token, exp_seg)
    return {"mensaje": "Contraseña actualizada exitosamente."}


# -----------------------------------------------------------------------------
# RUTAS PROTEGIDAS (ADMIN)
# -----------------------------------------------------------------------------

@usuarios_router.post(
    "/usuarios",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requiere_rol("ADMIN"))],
)
async def crear_personal(
    datos: UsuarioPersonalCreate,
    admin: Usuario = Depends(get_usuario_actual),
    service: UsuarioService = Depends(get_usuario_service),
) -> UsuarioResponse:
    """Alta de personal por un administrador (contraseña provisoria, cambio obligatorio)."""
    try:
        usuario = await service.crear_personal(datos, admin_actor=admin.email)
        return UsuarioResponse.model_validate(usuario)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)
    except IntegrityError as exc:
        raise traducir_error_integridad(exc)


@usuarios_router.get(
    "/usuarios/{id}/roles",
    response_model=list[AsignacionRolResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("ADMIN"))],
)
async def listar_roles_usuario(
    id: int,
    service: UsuarioService = Depends(get_usuario_service),
) -> list[AsignacionRolResponse]:
    """Lista todos los roles (vigentes e históricos) asignados a un usuario."""
    try:
        roles = await service.listar_roles_usuario(id)
        return [AsignacionRolResponse.model_validate(r) for r in roles]
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)


@usuarios_router.post(
    "/usuarios/{id}/roles",
    response_model=AsignacionRolResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requiere_rol("ADMIN"))],
)
async def asignar_rol(
    id: int,
    datos: AsignarRolRequest,
    admin: Usuario = Depends(get_usuario_actual),
    service: UsuarioService = Depends(get_usuario_service),
) -> AsignacionRolResponse:
    """Asigna un rol con vencimiento opcional a un usuario."""
    try:
        rol = await service.asignar_rol(id, datos, admin_usuario=admin)
        return AsignacionRolResponse.model_validate(rol)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)
    except IntegrityError as exc:
        raise traducir_error_integridad(exc)


@usuarios_router.delete(
    "/usuarios/{id}/roles/{rol}",
    response_model=AsignacionRolResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("ADMIN"))],
)
async def revocar_rol(
    id: int,
    rol: str,
    admin: Usuario = Depends(get_usuario_actual),
    service: UsuarioService = Depends(get_usuario_service),
) -> AsignacionRolResponse:
    """Revoca un rol estableciendo revocada_en. Aplica autoprotección (RN-05)."""
    try:
        rol_revocado = await service.revocar_rol(
            usuario_id=id,
            rol=rol,
            admin_usuario=admin,
        )
        return AsignacionRolResponse.model_validate(rol_revocado)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)


@usuarios_router.get(
    "/eventos",
    response_model=Pagina[EventoSeguridadResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("ADMIN"))],
)
async def listar_eventos_seguridad(
    page: int = Query(default=1, description="Número de página"),
    size: int = Query(default=20, description="Cantidad por página (1 a 100)"),
    service: UsuarioService = Depends(get_usuario_service),
) -> Pagina[EventoSeguridadResponse]:
    """Lista los eventos de auditoría de seguridad de forma paginada."""
    items, total, pages = await service.listar_eventos_seguridad(page=page, size=size)
    return Pagina(
        items=[EventoSeguridadResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )
