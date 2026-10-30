from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.paginacion import validar_y_calcular_paginacion
from app.core.repository import BaseRepository
from app.modules.clientes.models import Vehiculo
from app.modules.ordenes.models import (
    EstadoOrden,
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)


class EstadoOrdenRepository:
    """Repositorio de sólo lectura para el catálogo de estados de orden (RN-19 / sección 6.4.3).

    No hereda de BaseRepository para no exponer add, update ni delete innecesarios.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_codigo(self, codigo: str) -> Optional[EstadoOrden]:
        """Obtiene un estado por su clave primaria (código)."""
        return await self.session.get(EstadoOrden, codigo)

    async def listar_por_posicion(self) -> list[EstadoOrden]:
        """Retorna todos los estados ordenados por su posición en el flujo."""
        stmt = select(EstadoOrden).order_by(EstadoOrden.posicion)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def count(self) -> int:
        """Cuenta la cantidad de estados en el catálogo."""
        stmt = select(func.count()).select_from(EstadoOrden)
        res = await self.session.execute(stmt)
        return res.scalar() or 0


class OrdenTrabajoRepository(BaseRepository[OrdenTrabajo]):
    """Repositorio para la entidad OrdenTrabajo con precarga sin N+1."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(OrdenTrabajo, session)

    async def get_detalle_completo(self, orden_id: int) -> Optional[OrdenTrabajo]:
        """Carga anticipada de toda la composición: vehículo, cliente, ítems, repuestos e historial.

        Garantiza un número fijo de consultas que no escala con los ítems (sección 4.6).
        """
        stmt = (
            select(OrdenTrabajo)
            .options(
                selectinload(OrdenTrabajo.vehiculo).selectinload(Vehiculo.cliente),
                selectinload(OrdenTrabajo.items).selectinload(ItemOrden.repuesto),
                selectinload(OrdenTrabajo.historial_estados),
            )
            .where(OrdenTrabajo.id == orden_id)
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def listar_paginado(
        self,
        estado: Optional[str],
        page: int,
        size: int,
    ) -> tuple[list[OrdenTrabajo], int, int]:
        """Lista órdenes filtradas opcionalmente por estado con paginación."""
        base_where = []
        if estado:
            base_where.append(OrdenTrabajo.estado == estado)

        count_stmt = select(func.count(OrdenTrabajo.id)).where(*base_where)
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar() or 0

        pages, offset = validar_y_calcular_paginacion(total, page, size)

        stmt = (
            select(OrdenTrabajo)
            .options(selectinload(OrdenTrabajo.vehiculo))
            .where(*base_where)
            .order_by(OrdenTrabajo.creada_en.desc())
            .offset(offset)
            .limit(size)
        )
        res = await self.session.execute(stmt)
        items = list(res.scalars().all())

        return items, total, pages

    async def listar_por_cliente_paginado(
        self,
        cliente_id: int,
        page: int,
        size: int,
    ) -> tuple[list[OrdenTrabajo], int, int]:
        """Lista órdenes de los vehículos pertenecientes a un cliente (RN-17)."""
        join_clause = OrdenTrabajo.vehiculo_id == Vehiculo.id
        base_where = [Vehiculo.cliente_id == cliente_id]

        count_stmt = (
            select(func.count(OrdenTrabajo.id))
            .join(Vehiculo, join_clause)
            .where(*base_where)
        )
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar() or 0

        pages, offset = validar_y_calcular_paginacion(total, page, size)

        stmt = (
            select(OrdenTrabajo)
            .join(Vehiculo, join_clause)
            .options(selectinload(OrdenTrabajo.vehiculo))
            .where(*base_where)
            .order_by(OrdenTrabajo.creada_en.desc())
            .offset(offset)
            .limit(size)
        )
        res = await self.session.execute(stmt)
        items = list(res.scalars().all())

        return items, total, pages


class ItemOrdenRepository(BaseRepository[ItemOrden]):
    """Repositorio para los ítems de repuesto de una orden."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ItemOrden, session)


class HistorialEstadoOrdenRepository(BaseRepository[HistorialEstadoOrden]):
    """Repositorio para la tabla append-only historial_estado_orden."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(HistorialEstadoOrden, session)
