from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, Column, DateTime, Numeric, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.clientes.models import Vehiculo
    from app.modules.usuarios.models import Usuario
    from app.modules.repuestos.models import Repuesto


class EstadoOrden(SQLModel, table=True):
    """Tabla catálogo de estados de orden de trabajo (RN-19)."""

    __tablename__ = "estado_orden"

    codigo: str = Field(primary_key=True)
    descripcion: str
    posicion: int = Field(sa_column_kwargs={"unique": True}, index=True)
    es_final: bool

    ordenes: list["OrdenTrabajo"] = Relationship(back_populates="estado_catalogo")


class OrdenTrabajo(SQLModel, table=True):
    """Modelo principal de orden de trabajo del taller mecánico."""

    __tablename__ = "orden_trabajo"

    id: Optional[int] = Field(default=None, primary_key=True)
    vehiculo_id: int = Field(foreign_key="vehiculo.id", index=True)
    mecanico_id: Optional[int] = Field(default=None, foreign_key="usuario.id", index=True)
    estado: str = Field(foreign_key="estado_orden.codigo", index=True)
    falla: str
    creada_en: datetime = Field(sa_type=DateTime(timezone=True))
    total: Decimal = Field(
        default=Decimal("0.00"),
        sa_column=Column(Numeric(12, 2), nullable=False),
    )

    vehiculo: Optional["Vehiculo"] = Relationship(back_populates="ordenes")
    mecanico: Optional["Usuario"] = Relationship()
    estado_catalogo: Optional[EstadoOrden] = Relationship(back_populates="ordenes")
    items: list["ItemOrden"] = Relationship(back_populates="orden")
    historial_estados: list["HistorialEstadoOrden"] = Relationship(back_populates="orden")

    __table_args__ = (
        CheckConstraint("total >= 0", name="ck_orden_trabajo_total_no_negativo"),
    )


class ItemOrden(SQLModel, table=True):
    """Repuesto y cantidad asignados a una orden de trabajo."""

    __tablename__ = "item_orden"

    id: Optional[int] = Field(default=None, primary_key=True)
    orden_id: int = Field(foreign_key="orden_trabajo.id", index=True)
    repuesto_id: int = Field(foreign_key="repuesto.id", index=True)
    cantidad: int
    precio_unitario: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))

    orden: Optional[OrdenTrabajo] = Relationship(back_populates="items")
    repuesto: Optional["Repuesto"] = Relationship(back_populates="items_orden")

    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_item_orden_cantidad_positiva"),
        CheckConstraint("precio_unitario > 0", name="ck_item_orden_precio_unitario_positivo"),
        UniqueConstraint("orden_id", "repuesto_id", name="uq_item_orden_orden_repuesto"),
    )


class HistorialEstadoOrden(SQLModel, table=True):
    """Historial inmutable de cambios de estado de las órdenes (append-only)."""

    __tablename__ = "historial_estado_orden"

    id: Optional[int] = Field(default=None, primary_key=True)
    orden_id: int = Field(foreign_key="orden_trabajo.id", index=True)
    desde_estado: Optional[str] = Field(
        default=None,
        foreign_key="estado_orden.codigo",
        index=True,
    )
    hasta_estado: str = Field(foreign_key="estado_orden.codigo", index=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    cuando: datetime = Field(sa_type=DateTime(timezone=True))

    orden: Optional[OrdenTrabajo] = Relationship(back_populates="historial_estados")
