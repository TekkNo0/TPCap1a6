from typing import Optional
from sqlalchemy import bindparam, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.paginacion import validar_y_calcular_paginacion
from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)


class RepuestoRepository(SoftDeleteRepository[Repuesto]):
    """Repositorio para la entidad Repuesto con soporte de borrado lógico."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Repuesto, session)

    async def get_by_codigo_activo(self, codigo: str) -> Optional[Repuesto]:
        """Busca un repuesto no borrado por su código."""
        stmt = select(Repuesto).where(
            Repuesto.codigo == codigo,
            Repuesto.borrado_en.is_(None),
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def listar_y_buscar(
        self,
        q: Optional[str],
        page: int,
        size: int,
    ) -> tuple[list[Repuesto], int, int]:
        """Lista repuestos activos con filtro opcional por descripción usando parámetros ligados.

        Retorna (items, total, pages).
        """
        # Consulta base filtrando sólo activos
        base_where = [Repuesto.borrado_en.is_(None)]
        if q is not None and q.strip() != "":
            # Parámetro ligado explícito para evitar inyección SQL (RN-18 / C-16)
            filtro = f"%{q.strip()}%"
            base_where.append(
                Repuesto.descripcion.ilike(bindparam("q_param", filtro))
            )

        # 1. Conteo total con exactamente los mismos filtros
        count_stmt = select(func.count(Repuesto.id)).where(*base_where)
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar() or 0

        # 2. Validación de página y cálculo de offset
        pages, offset = validar_y_calcular_paginacion(total, page, size)

        # 3. Consulta de ítems paginados
        items_stmt = (
            select(Repuesto)
            .where(*base_where)
            .order_by(Repuesto.id)
            .offset(offset)
            .limit(size)
        )
        items_res = await self.session.execute(items_stmt)
        items = list(items_res.scalars().all())

        return items, total, pages


class MovimientoStockRepository(BaseRepository[MovimientoStock]):
    """Repositorio para la entidad inmutable MovimientoStock."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(MovimientoStock, session)

    async def get_by_repuesto_id(self, repuesto_id: int) -> list[MovimientoStock]:
        """Obtiene todos los movimientos de un repuesto ordenados por fecha."""
        stmt = (
            select(MovimientoStock)
            .where(MovimientoStock.repuesto_id == repuesto_id)
            .order_by(MovimientoStock.cuando.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())


class HistorialPrecioRepository(BaseRepository[HistorialPrecioRepuesto]):
    """Repositorio para la entidad inmutable HistorialPrecioRepuesto."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(HistorialPrecioRepuesto, session)

    async def get_by_repuesto_id(self, repuesto_id: int) -> list[HistorialPrecioRepuesto]:
        """Obtiene el historial de precios de un repuesto ordenado por fecha."""
        stmt = (
            select(HistorialPrecioRepuesto)
            .where(HistorialPrecioRepuesto.repuesto_id == repuesto_id)
            .order_by(HistorialPrecioRepuesto.cuando.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
