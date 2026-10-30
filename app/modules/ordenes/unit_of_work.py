from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import ClienteRepository, VehiculoRepository
from app.modules.ordenes.repository import (
    EstadoOrdenRepository,
    HistorialEstadoOrdenRepository,
    ItemOrdenRepository,
    OrdenTrabajoRepository,
)
from app.modules.repuestos.repository import (
    MovimientoStockRepository,
    RepuestoRepository,
)


class OrdenesUnitOfWork(UnitOfWork):
    """Unit of Work para el módulo de órdenes de trabajo.

    Compone todos los repositorios que intervienen en la creación,
    transición de estados y descuento de inventario con la misma sesión.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.catalogo = EstadoOrdenRepository(session)
        self.ordenes = OrdenTrabajoRepository(session)
        self.items = ItemOrdenRepository(session)
        self.historial = HistorialEstadoOrdenRepository(session)
        self.repuestos = RepuestoRepository(session)
        self.movimientos = MovimientoStockRepository(session)
        self.vehiculos = VehiculoRepository(session)
        self.clientes = ClienteRepository(session)
