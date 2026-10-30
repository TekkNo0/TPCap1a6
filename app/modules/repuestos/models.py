from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, Column, DateTime, Index, Numeric, text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.ordenes.models import ItemOrden


class Repuesto(SQLModel, table=True):
    """Modelo de repuesto o autoparte con control de stock y borrado lógico."""

    __tablename__ = "repuesto"

    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: str
    descripcion: str
    precio: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    stock: int = Field(default=0)
    borrado_en: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )

    movimientos: list["MovimientoStock"] = Relationship(back_populates="repuesto")
    historial_precios: list["HistorialPrecioRepuesto"] = Relationship(back_populates="repuesto")
    items_orden: list["ItemOrden"] = Relationship(back_populates="repuesto")

    __table_args__ = (
        CheckConstraint("precio > 0", name="ck_repuesto_precio_positivo"),
        CheckConstraint("stock >= 0", name="ck_repuesto_stock_no_negativo"),
        # Índice único parcial: código único sólo entre repuestos no borrados
        Index(
            "ix_repuesto_codigo_activo",
            "codigo",
            unique=True,
            postgresql_where=text("borrado_en IS NULL"),
        ),
    )


class MovimientoStock(SQLModel, table=True):
    """Movimientos de inventario de repuestos (tabla append-only / sólo agregado)."""

    __tablename__ = "movimiento_stock"

    id: Optional[int] = Field(default=None, primary_key=True)
    repuesto_id: int = Field(foreign_key="repuesto.id", index=True)
    orden_id: Optional[int] = Field(default=None, foreign_key="orden_trabajo.id", index=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    cantidad: int
    motivo: str
    cuando: datetime = Field(sa_type=DateTime(timezone=True))

    repuesto: Optional[Repuesto] = Relationship(back_populates="movimientos")

    __table_args__ = (
        CheckConstraint("cantidad <> 0", name="ck_movimiento_stock_cantidad_distinto_cero"),
    )


class HistorialPrecioRepuesto(SQLModel, table=True):
    """Historial inmutable de modificaciones de precios de repuestos (append-only)."""

    __tablename__ = "historial_precio_repuesto"

    id: Optional[int] = Field(default=None, primary_key=True)
    repuesto_id: int = Field(foreign_key="repuesto.id", index=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    precio_anterior: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    precio_nuevo: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    cuando: datetime = Field(sa_type=DateTime(timezone=True))

    repuesto: Optional[Repuesto] = Relationship(back_populates="historial_precios")

    __table_args__ = (
        CheckConstraint("precio_nuevo > 0", name="ck_historial_precio_nuevo_positivo"),
        CheckConstraint(
            "precio_nuevo <> precio_anterior",
            name="ck_historial_precio_diferente",
        ),
    )
