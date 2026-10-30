from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.dependencies import get_usuario_actual, requiere_rol
from app.core.exceptions import (
    ConflictoError,
    RecursoNoEncontradoError,
    traducir_error_integridad,
)
from app.modules.clientes.schemas import (
    ClienteCreate,
    ClienteDetalleResponse,
    ClienteResponse,
    VehiculoCreate,
    VehiculoResponse,
)
from app.modules.clientes.service import ClienteService
from app.modules.clientes.unit_of_work import ClientesUnitOfWork

router = APIRouter(tags=["Clientes y Vehículos"])


def get_cliente_service(
    session: AsyncSession = Depends(get_session),
) -> ClienteService:
    """Construye el Unit of Work y el Servicio de Clientes."""
    uow = ClientesUnitOfWork(session)
    return ClienteService(uow)


@router.post(
    "/clientes",
    response_model=ClienteResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requiere_rol("RECEPCION", "ADMIN"))],
)
async def crear_cliente(
    datos: ClienteCreate,
    service: ClienteService = Depends(get_cliente_service),
) -> ClienteResponse:
    """Registra un nuevo cliente (RECEPCION o ADMIN)."""
    try:
        cliente = await service.crear_cliente(datos)
        return ClienteResponse.model_validate(cliente)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)
    except IntegrityError as exc:
        raise traducir_error_integridad(exc)


@router.get(
    "/clientes/{id}",
    response_model=ClienteDetalleResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("RECEPCION", "ADMIN"))],
)
async def obtener_cliente_con_vehiculos(
    id: int,
    service: ClienteService = Depends(get_cliente_service),
) -> ClienteDetalleResponse:
    """Obtiene el detalle de un cliente incluyendo sus vehículos activos (sin N+1)."""
    try:
        cliente = await service.obtener_con_vehiculos(id)
        return ClienteDetalleResponse.model_validate(cliente)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)


@router.post(
    "/clientes/{id}/vehiculos",
    response_model=VehiculoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requiere_rol("RECEPCION", "ADMIN"))],
)
async def registrar_vehiculo(
    id: int,
    datos: VehiculoCreate,
    service: ClienteService = Depends(get_cliente_service),
) -> VehiculoResponse:
    """Registra un vehículo asociado al cliente."""
    try:
        vehiculo = await service.agregar_vehiculo(id, datos)
        return VehiculoResponse.model_validate(vehiculo)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)
    except IntegrityError as exc:
        raise traducir_error_integridad(exc)


@router.delete(
    "/vehiculos/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requiere_rol("RECEPCION", "ADMIN"))],
)
async def dar_de_baja_vehiculo(
    id: int,
    service: ClienteService = Depends(get_cliente_service),
) -> None:
    """Aplica borrado lógico sobre el vehículo. Rechaza con 409 si tiene órdenes abiertas."""
    try:
        await service.dar_de_baja_vehiculo(id)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)


@router.get("/mis-vehiculos", response_model=list[VehiculoResponse], status_code=status.HTTP_200_OK)
async def obtener_mis_vehiculos(
    usuario = Depends(get_usuario_actual),
    service: ClienteService = Depends(get_cliente_service),
) -> list[VehiculoResponse]:
    """Retorna los vehículos activos pertenecientes al cliente autenticado (RN-17)."""
    cliente = await service.uow.clientes.get_by_usuario_id(usuario.id)
    if not cliente:
        return []
    vehiculos = await service.uow.vehiculos.listar_activos_por_cliente(cliente.id)
    return [VehiculoResponse.model_validate(v) for v in vehiculos]
