from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo


class ClienteRepository(BaseRepository[Cliente]):
    """Repositorio para la entidad Cliente."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Cliente, session)

    async def get_by_documento(self, documento: str) -> Optional[Cliente]:
        stmt = select(Cliente).where(Cliente.documento == documento)
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def get_by_usuario_id(self, usuario_id: int) -> Optional[Cliente]:
        stmt = select(Cliente).where(Cliente.usuario_id == usuario_id)
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def get_con_vehiculos_activos(self, cliente_id: int) -> Optional[Cliente]:
        """Carga anticipada (selectinload) de vehículos activos para evitar N+1."""
        stmt = (
            select(Cliente)
            .options(selectinload(Cliente.vehiculos))
            .where(Cliente.id == cliente_id)
        )
        res = await self.session.execute(stmt)
        cliente = res.scalars().first()
        if cliente:
            # Filtrar sólo vehículos que no tengan borrado lógico
            cliente.vehiculos = [v for v in cliente.vehiculos if v.borrado_en is None]
        return cliente


class VehiculoRepository(SoftDeleteRepository[Vehiculo]):
    """Repositorio para la entidad Vehiculo."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Vehiculo, session)

    async def get_by_patente_activa(self, patente: str) -> Optional[Vehiculo]:
        stmt = select(Vehiculo).where(
            Vehiculo.patente == patente,
            Vehiculo.borrado_en.is_(None),
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def listar_activos_por_cliente(self, cliente_id: int) -> list[Vehiculo]:
        stmt = (
            select(Vehiculo)
            .where(
                Vehiculo.cliente_id == cliente_id,
                Vehiculo.borrado_en.is_(None),
            )
            .order_by(Vehiculo.id)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def tiene_ordenes_abiertas(self, vehiculo_id: int) -> bool:
        """Verifica si el vehículo tiene órdenes en estados no finales (RN-16)."""
        stmt = (
            select(func.count(OrdenTrabajo.id))
            .join(EstadoOrden, OrdenTrabajo.estado == EstadoOrden.codigo)
            .where(
                OrdenTrabajo.vehiculo_id == vehiculo_id,
                EstadoOrden.es_final.is_(False),
            )
        )
        res = await self.session.execute(stmt)
        count = res.scalar() or 0
        return count > 0
