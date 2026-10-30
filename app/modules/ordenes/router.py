from typing import Optional
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.dependencies import get_usuario_actual, requiere_rol
from app.core.exceptions import (
    ConflictoError,
    PermisoDenegadoError,
    RecursoNoEncontradoError,
    traducir_error_integridad,
)
from app.core.paginacion import Pagina
from app.modules.ordenes.models import OrdenTrabajo
from app.modules.ordenes.schemas import (
    EstadoOrdenEnum,
    EstadoOrdenResponse,
    HistorialEstadoItem,
    ItemOrdenDetalle,
    OrdenCreate,
    OrdenDetalleResponse,
    OrdenResumenResponse,
)
from app.modules.ordenes.service import OrdenService, simular_notificacion_cliente
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from app.modules.usuarios.models import Usuario

router = APIRouter(tags=["Órdenes de Trabajo"])


def get_orden_service(
    session: AsyncSession = Depends(get_session),
) -> OrdenService:
    """Construye el Unit of Work y el Servicio de Órdenes."""
    uow = OrdenesUnitOfWork(session)
    return OrdenService(uow)


def _mapear_orden_detalle(orden: OrdenTrabajo) -> OrdenDetalleResponse:
    """Mapea una entidad OrdenTrabajo con sus relaciones precargadas a OrdenDetalleResponse."""
    items_dto = [
        ItemOrdenDetalle(
            repuesto_id=item.repuesto_id,
            codigo=item.repuesto.codigo if item.repuesto else "",
            descripcion=item.repuesto.descripcion if item.repuesto else "",
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            subtotal=item.precio_unitario * item.cantidad,
        )
        for item in orden.items
    ]
    hist_dto = [
        HistorialEstadoItem(
            desde_estado=h.desde_estado,
            hasta_estado=h.hasta_estado,
            usuario_id=h.usuario_id,
            cuando=h.cuando,
        )
        for h in orden.historial_estados
    ]
    return OrdenDetalleResponse(
        id=orden.id,  # type: ignore[arg-type]
        estado=orden.estado,
        patente=orden.vehiculo.patente if orden.vehiculo else "",
        total=orden.total,
        creada_en=orden.creada_en,
        mecanico_id=orden.mecanico_id,
        falla=orden.falla,
        cliente=orden.vehiculo.cliente.nombre if (orden.vehiculo and orden.vehiculo.cliente) else "",
        items=items_dto,
        historial=hist_dto,
    )


@router.get("/estados-orden", response_model=list[EstadoOrdenResponse], status_code=status.HTTP_200_OK)
async def listar_estados_catalogo(
    usuario: Usuario = Depends(get_usuario_actual),
    service: OrdenService = Depends(get_orden_service),
) -> list[EstadoOrdenResponse]:
    """Retorna las filas del catálogo estado_orden ordenadas por posición (Autenticado)."""
    estados = await service.listar_catalogo()
    return [EstadoOrdenResponse.model_validate(e) for e in estados]


@router.post(
    "/ordenes",
    response_model=OrdenDetalleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requiere_rol("RECEPCION", "ADMIN"))],
)
async def crear_orden(
    datos: OrdenCreate,
    usuario: Usuario = Depends(get_usuario_actual),
    service: OrdenService = Depends(get_orden_service),
) -> OrdenDetalleResponse:
    """Crea una nueva orden de trabajo en estado PENDIENTE."""
    try:
        orden = await service.crear_orden(datos, usuario_id=usuario.id)  # type: ignore[arg-type]
        return _mapear_orden_detalle(orden)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)
    except IntegrityError as exc:
        raise traducir_error_integridad(exc)


@router.get(
    "/ordenes",
    response_model=Pagina[OrdenResumenResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO"))],
)
async def listar_ordenes(
    estado: Optional[EstadoOrdenEnum] = Query(default=None, description="Filtro opcional por estado"),
    page: int = Query(default=1, description="Número de página"),
    size: int = Query(default=20, description="Cantidad por página (1 a 100)"),
    service: OrdenService = Depends(get_orden_service),
) -> Pagina[OrdenResumenResponse]:
    """Lista órdenes de trabajo con paginación estándar y filtro por estado."""
    estado_str = estado.value if estado else None
    items, total, pages = await service.listar(estado=estado_str, page=page, size=size)
    dtos = [
        OrdenResumenResponse(
            id=o.id,  # type: ignore[arg-type]
            estado=o.estado,
            patente=o.vehiculo.patente if o.vehiculo else "",
            total=o.total,
            creada_en=o.creada_en,
            mecanico_id=o.mecanico_id,
            falla=o.falla,
        )
        for o in items
    ]
    return Pagina(items=dtos, total=total, page=page, size=size, pages=pages)


@router.get("/ordenes/{id}", response_model=OrdenDetalleResponse, status_code=status.HTTP_200_OK)
async def obtener_detalle_orden(
    id: int,
    usuario: Usuario = Depends(get_usuario_actual),
    service: OrdenService = Depends(get_orden_service),
) -> OrdenDetalleResponse:
    """Obtiene el detalle completo de una orden sin N+1 (Personal o dueño del vehículo)."""
    try:
        orden = await service.obtener_por_id(id, usuario_actual=usuario)
        return _mapear_orden_detalle(orden)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)
    except PermisoDenegadoError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.mensaje)


@router.post(
    "/ordenes/{id}/iniciar",
    response_model=OrdenDetalleResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requiere_rol("MECANICO"))],
)
async def iniciar_orden(
    id: int,
    mecanico: Usuario = Depends(get_usuario_actual),
    service: OrdenService = Depends(get_orden_service),
) -> OrdenDetalleResponse:
    """Inicia una orden PENDIENTE pasando a EN_REPARACION y asignando al mecánico."""
    try:
        orden = await service.iniciar(id, mecanico_id=mecanico.id)  # type: ignore[arg-type]
        return _mapear_orden_detalle(orden)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)


@router.post(
    "/ordenes/{id}/terminar",
    response_model=OrdenDetalleResponse,
    status_code=status.HTTP_200_OK,
)
async def terminar_orden(
    id: int,
    background_tasks: BackgroundTasks,
    usuario: Usuario = Depends(get_usuario_actual),
    service: OrdenService = Depends(get_orden_service),
) -> OrdenDetalleResponse:
    """Finaliza una orden con descuento atómico de stock. Agenda notificación en segundo plano."""
    try:
        orden, cliente_email = await service.terminar(id, usuario_actual=usuario)
        background_tasks.add_task(simular_notificacion_cliente, orden.id, cliente_email)
        return _mapear_orden_detalle(orden)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)
    except PermisoDenegadoError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.mensaje)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)


@router.post(
    "/ordenes/{id}/cancelar",
    response_model=OrdenDetalleResponse,
    status_code=status.HTTP_200_OK,
)
async def cancelar_orden(
    id: int,
    usuario: Usuario = Depends(get_usuario_actual),
    service: OrdenService = Depends(get_orden_service),
) -> OrdenDetalleResponse:
    """Cancela una orden PENDIENTE (RECEPCION, ADMIN o el dueño del vehículo)."""
    try:
        orden = await service.cancelar(id, usuario_actual=usuario)
        return _mapear_orden_detalle(orden)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.mensaje)
    except PermisoDenegadoError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.mensaje)
    except ConflictoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)


@router.get("/mis-ordenes", response_model=Pagina[OrdenResumenResponse], status_code=status.HTTP_200_OK)
async def obtener_mis_ordenes(
    page: int = Query(default=1, description="Número de página"),
    size: int = Query(default=20, description="Cantidad por página (1 a 100)"),
    usuario: Usuario = Depends(get_usuario_actual),
    service: OrdenService = Depends(get_orden_service),
) -> Pagina[OrdenResumenResponse]:
    """Retorna las órdenes asociadas a los vehículos del cliente autenticado (RN-17)."""
    items, total, pages = await service.listar_mis_ordenes(
        usuario_id=usuario.id,  # type: ignore[arg-type]
        page=page,
        size=size,
    )
    dtos = [
        OrdenResumenResponse(
            id=o.id,  # type: ignore[arg-type]
            estado=o.estado,
            patente=o.vehiculo.patente if o.vehiculo else "",
            total=o.total,
            creada_en=o.creada_en,
            mecanico_id=o.mecanico_id,
            falla=o.falla,
        )
        for o in items
    ]
    return Pagina(items=dtos, total=total, page=page, size=size, pages=pages)
