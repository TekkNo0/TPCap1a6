from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EstadoOrdenEnum(str, Enum):
    """Vocabulario formal de estados para el contrato de la API y el servicio (sección 4.8)."""

    PENDIENTE = "PENDIENTE"
    EN_REPARACION = "EN_REPARACION"
    TERMINADA = "TERMINADA"
    CANCELADA = "CANCELADA"


class ItemOrdenInput(BaseModel):
    """Contrato de entrada para un ítem de repuesto dentro de una orden."""

    model_config = ConfigDict(extra="forbid")

    repuesto_id: int = Field(..., gt=0)
    cantidad: int = Field(..., gt=0)


class OrdenCreate(BaseModel):
    """Contrato de entrada para crear una orden de trabajo (RN-10).

    El precio y el total nunca viajan en el cuerpo: el precio se copia del repuesto
    y el total lo calcula el servidor.
    """

    model_config = ConfigDict(extra="forbid")

    vehiculo_id: int = Field(..., gt=0)
    falla: str = Field(..., min_length=1)
    items: list[ItemOrdenInput] = Field(..., min_length=1)

    @field_validator("items")
    @classmethod
    def validar_repuestos_unicos(cls, v: list[ItemOrdenInput]) -> list[ItemOrdenInput]:
        ids = [item.repuesto_id for item in v]
        if len(ids) != len(set(ids)):
            raise ValueError("No se permiten repuestos repetidos en una misma orden.")
        return v


class ItemOrdenDetalle(BaseModel):
    """Detalle de un repuesto dentro de una orden con su subtotal."""

    model_config = ConfigDict(from_attributes=True)

    repuesto_id: int
    codigo: str
    descripcion: str
    cantidad: int
    precio_unitario: Decimal
    subtotal: Decimal


class HistorialEstadoItem(BaseModel):
    """Línea del historial inmutable de estados de una orden."""

    model_config = ConfigDict(from_attributes=True)

    desde_estado: Optional[str] = None
    hasta_estado: str
    usuario_id: int
    cuando: datetime


class OrdenDetalleResponse(BaseModel):
    """Respuesta completa del detalle de una orden (sección 2.8 y 4.6)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    estado: str
    patente: str
    total: Decimal
    creada_en: datetime
    mecanico_id: Optional[int] = None
    falla: str
    cliente: str
    items: list[ItemOrdenDetalle] = []
    historial: list[HistorialEstadoItem] = []


class OrdenResumenResponse(BaseModel):
    """Respuesta para listados de órdenes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    estado: str
    patente: str
    total: Decimal
    creada_en: datetime
    mecanico_id: Optional[int] = None
    falla: str


class EstadoOrdenResponse(BaseModel):
    """Contrato de salida para las filas del catálogo estado_orden."""

    model_config = ConfigDict(from_attributes=True)

    codigo: str
    descripcion: str
    posicion: int
    es_final: bool
