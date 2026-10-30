from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from app.core.exceptions import ConflictoError, RecursoNoEncontradoError
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)
from app.modules.repuestos.schemas import (
    RepuestoCreate,
    RepuestoReponer,
    RepuestoUpdate,
)
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork


class RepuestoService:
    """Reglas de negocio para la administración de repuestos e inventario."""

    def __init__(self, uow: RepuestosUnitOfWork) -> None:
        self.uow = uow

    async def listar(
        self,
        q: Optional[str],
        page: int,
        size: int,
    ) -> tuple[list[Repuesto], int, int]:
        """Lista repuestos activos con búsqueda parametrizada y paginación."""
        return await self.uow.repuestos.listar_y_buscar(q, page, size)

    async def obtener_por_id(self, id_val: int) -> Repuesto:
        """Obtiene un repuesto activo o lanza 404."""
        repuesto = await self.uow.repuestos.get_active_by_id(id_val)
        if not repuesto:
            raise RecursoNoEncontradoError(f"Repuesto con id {id_val} no encontrado.")
        return repuesto

    async def crear(self, datos: RepuestoCreate, usuario_id: int) -> Repuesto:
        """Da de alta un repuesto con su movimiento de stock inicial (RN-14)."""
        async with self.uow:
            existente = await self.uow.repuestos.get_by_codigo_activo(datos.codigo)
            if existente:
                raise ConflictoError(
                    f"Ya existe un repuesto activo con el código '{datos.codigo}'."
                )

            repuesto = Repuesto(
                codigo=datos.codigo,
                descripcion=datos.descripcion,
                precio=datos.precio,
                stock=datos.stock_inicial,
            )
            await self.uow.repuestos.add(repuesto)

            if datos.stock_inicial > 0:
                movimiento = MovimientoStock(
                    repuesto_id=repuesto.id,  # type: ignore[arg-type]
                    orden_id=None,
                    usuario_id=usuario_id,
                    cantidad=datos.stock_inicial,
                    motivo="Stock inicial",
                    cuando=datetime.now(timezone.utc),
                )
                await self.uow.movimientos.add(movimiento)

            return repuesto

    async def actualizar_parcial(
        self,
        id_val: int,
        datos: RepuestoUpdate,
        usuario_id: int,
    ) -> Repuesto:
        """Aplica PATCH usando sólo los campos enviados (exclude_unset).

        Si cambia el precio, anota la línea en historial_precio_repuesto dentro de la
        misma transacción del Unit of Work (RN-20).
        """
        async with self.uow:
            repuesto = await self.obtener_por_id(id_val)
            cambios = datos.model_dump(exclude_unset=True)

            if "precio" in cambios and cambios["precio"] is not None:
                nuevo_precio = Decimal(str(cambios["precio"]))
                if nuevo_precio != repuesto.precio:
                    historial = HistorialPrecioRepuesto(
                        repuesto_id=repuesto.id,  # type: ignore[arg-type]
                        usuario_id=usuario_id,
                        precio_anterior=repuesto.precio,
                        precio_nuevo=nuevo_precio,
                        cuando=datetime.now(timezone.utc),
                    )
                    await self.uow.precios.add(historial)
                    repuesto.precio = nuevo_precio

            if "descripcion" in cambios and cambios["descripcion"] is not None:
                repuesto.descripcion = cambios["descripcion"]

            await self.uow.repuestos.update(repuesto)
            return repuesto

    async def dar_de_baja(self, id_val: int) -> None:
        """Aplica borrado lógico sobre el repuesto (RN-16)."""
        async with self.uow:
            repuesto = await self.obtener_por_id(id_val)
            await self.uow.repuestos.soft_delete(repuesto)

    async def reponer(
        self,
        id_val: int,
        datos: RepuestoReponer,
        usuario_id: int,
    ) -> Repuesto:
        """Incrementa stock mediante un movimiento de reposición (RN-14)."""
        async with self.uow:
            repuesto = await self.obtener_por_id(id_val)
            repuesto.stock += datos.cantidad

            movimiento = MovimientoStock(
                repuesto_id=repuesto.id,  # type: ignore[arg-type]
                orden_id=None,
                usuario_id=usuario_id,
                cantidad=datos.cantidad,
                motivo=datos.motivo,
                cuando=datetime.now(timezone.utc),
            )
            await self.uow.movimientos.add(movimiento)
            await self.uow.repuestos.update(repuesto)
            return repuesto

    async def obtener_movimientos(self, id_val: int) -> list[MovimientoStock]:
        """Retorna el historial de movimientos de inventario de un repuesto."""
        await self.obtener_por_id(id_val)
        return await self.uow.movimientos.get_by_repuesto_id(id_val)

    async def obtener_historial_precios(
        self, id_val: int
    ) -> list[HistorialPrecioRepuesto]:
        """Retorna el historial de cambios de precio de un repuesto."""
        await self.obtener_por_id(id_val)
        return await self.uow.precios.get_by_repuesto_id(id_val)
