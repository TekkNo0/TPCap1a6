from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, DateTime, Index, text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.usuarios.models import Usuario
    from app.modules.ordenes.models import OrdenTrabajo


class Cliente(SQLModel, table=True):
    """Modelo de cliente del taller mecánico."""

    __tablename__ = "cliente"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: Optional[int] = Field(
        default=None,
        foreign_key="usuario.id",
        sa_column_kwargs={"unique": True},
        index=True,
    )
    nombre: str
    documento: str = Field(sa_column_kwargs={"unique": True}, index=True)
    telefono: str

    # Relación 1 a 1 con Usuario
    usuario: Optional["Usuario"] = Relationship(back_populates="cliente")

    # Relación 1 a N con Vehiculo
    vehiculos: list["Vehiculo"] = Relationship(back_populates="cliente")


class Vehiculo(SQLModel, table=True):
    """Modelo de vehículo registrado por un cliente."""

    __tablename__ = "vehiculo"

    id: Optional[int] = Field(default=None, primary_key=True)
    cliente_id: int = Field(foreign_key="cliente.id", index=True)
    patente: str
    marca: str
    modelo: str
    anio: int
    borrado_en: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )

    cliente: Optional[Cliente] = Relationship(back_populates="vehiculos")
    ordenes: list["OrdenTrabajo"] = Relationship(back_populates="vehiculo")

    __table_args__ = (
        CheckConstraint("anio BETWEEN 1950 AND 2100", name="ck_vehiculo_anio"),
        # Índice único parcial: patente única sólo entre los no dados de baja
        Index(
            "ix_vehiculo_patente_activa",
            "patente",
            unique=True,
            postgresql_where=text("borrado_en IS NULL"),
        ),
    )
