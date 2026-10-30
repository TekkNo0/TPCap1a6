from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.dependencies import get_usuario_actual, requiere_rol
from app.core.exceptions import (
    ConflictoError,
    RecursoNoEncontradoError,
    traducir_error_integridad,
)
from app.core.paginacion import Pagina
from app.modules.repuestos.schemas import (
    HistorialPrecioResponse,
    MovimientoStockResponse,
    RepuestoCreate,
    RepuestoReponer,
    RepuestoResponse,
    RepuestoUpdate,
)
from app.modules.repuestos.service import RepuestoService
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork

router = APIRouter(prefix="/repuestos", tags=["Repuestos"])


def get_repuesto_service(
    session: AsyncSession = Depends(get_session),
) -> RepuestoService:
    """Construye el Unit of Work y el Servicio de Repuestos."""
    uow = RepuestosUnitOfWork(session)
    return RepuestoService(uow)


@router.get(
    "",
    response_model=Pagina[RepuestoResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO"))],
)
async def listar_repuestos(
    q: Optional[str] = Query(default=None, description="Filtro de búsqueda por descripción"),
    page: int = Query(default=1, description="Número de página"),
    size: int = Query(default=20, description="Cantidad por página (1 a 100)"),
    service: RepuestoService = Depends(get_repuesto_service),
) -> Pagina[RepuestoResponse]:
    """Lista repuestos activos con búsqueda y envoltorio de paginación de la sección 2.9."""
    items, total, pages = await service.listar(q=q, page=page, size=size)
    return Pagina(
        items=[RepuestoResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get(
    "/{id}",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO"))],
)
async def obtener_repuesto(
    id: int,
    service: RepuestoService = Depends(get_repuesto_service),
) -> RepuestoResponse:
    """Obtiene el detalle de un repuesto activo."""
    try:
        repuesto = await service.obtener_por_id(id)
        return RepuestoResponse.model_validate(repuesto)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)


@router.post(
    "",
    response_model=RepuestoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requiere_rol("ADMIN"))],
)
async def crear_repuesto(
    datos: RepuestoCreate,
    admin = Depends(get_usuario_actual),
    service: RepuestoService = Depends(get_repuesto_service),
) -> RepuestoResponse:
    """Crea un repuesto con su stock inicial."""
    try:
        repuesto = await service.crear(datos, usuario_id=admin.id)
        return RepuestoResponse.model_validate(repuesto)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)
    except IntegrityError as exc:
        raise traducir_error_integridad(exc)


@router.patch(
    "/{id}",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("ADMIN"))],
)
async def actualizar_repuesto(
    id: int,
    datos: RepuestoUpdate,
    admin = Depends(get_usuario_actual),
    service: RepuestoService = Depends(get_repuesto_service),
) -> RepuestoResponse:
    """Actualiza parcialmente (PATCH) descripción o precio.

    Rechaza campos no declarados (como stock) con 422.
    """
    try:
        repuesto = await service.actualizar_parcial(id, datos, usuario_id=admin.id)
        return RepuestoResponse.model_validate(repuesto)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)
    except IntegrityError as exc:
        raise traducir_error_integridad(exc)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requiere_rol("ADMIN"))],
)
async def dar_de_baja_repuesto(
    id: int,
    service: RepuestoService = Depends(get_repuesto_service),
) -> None:
    """Aplica borrado lógico sobre el repuesto."""
    try:
        await service.dar_de_baja(id)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)


@router.post(
    "/{id}/reponer",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("ADMIN"))],
)
async def reponer_stock(
    id: int,
    datos: RepuestoReponer,
    admin = Depends(get_usuario_actual),
    service: RepuestoService = Depends(get_repuesto_service),
) -> RepuestoResponse:
    """Repone stock de un repuesto generando un movimiento de entrada."""
    try:
        repuesto = await service.reponer(id, datos, usuario_id=admin.id)
        return RepuestoResponse.model_validate(repuesto)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)
    except IntegrityError as exc:
        raise traducir_error_integridad(exc)


@router.get(
    "/{id}/movimientos",
    response_model=list[MovimientoStockResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("ADMIN"))],
)
async def obtener_movimientos_repuesto(
    id: int,
    service: RepuestoService = Depends(get_repuesto_service),
) -> list[MovimientoStockResponse]:
    """Lista todos los movimientos de stock del repuesto."""
    try:
        movs = await service.obtener_movimientos(id)
        return [MovimientoStockResponse.model_validate(m) for m in movs]
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)


@router.get(
    "/{id}/precios",
    response_model=list[HistorialPrecioResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("ADMIN"))],
)
async def obtener_historial_precios(
    id: int,
    service: RepuestoService = Depends(get_repuesto_service),
) -> list[HistorialPrecioResponse]:
    """Lista el historial de cambios de precio del repuesto."""
    try:
        precios = await service.obtener_historial_precios(id)
        return [HistorialPrecioResponse.model_validate(p) for p in precios]
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)
