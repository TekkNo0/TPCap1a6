from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class RepuestoCreate(BaseModel):
    """Contrato de entrada para dar de alta un repuesto con stock inicial."""

    model_config = ConfigDict(extra="forbid")

    codigo: str = Field(..., min_length=1, max_length=50)
    descripcion: str = Field(..., min_length=1)
    precio: Decimal = Field(..., gt=0)
    stock_inicial: int = Field(default=0, ge=0)


class RepuestoUpdate(BaseModel):
    """Contrato de entrada para actualizar descripción o precio por PATCH.

    extra='forbid' impide que se intente actualizar el stock directamente.
    """

    model_config = ConfigDict(extra="forbid")

    descripcion: Optional[str] = Field(default=None, min_length=1)
    precio: Optional[Decimal] = Field(default=None, gt=0)


class RepuestoReponer(BaseModel):
    """Contrato de entrada para reposición de stock."""

    model_config = ConfigDict(extra="forbid")

    cantidad: int = Field(..., gt=0)
    motivo: str = Field(default="Reposición de stock", min_length=1)


class RepuestoResponse(BaseModel):
    """Contrato de salida para repuestos."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    descripcion: str
    precio: Decimal
    stock: int
    borrado_en: Optional[datetime] = None


class MovimientoStockResponse(BaseModel):
    """Contrato de salida para movimientos de inventario."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    repuesto_id: int
    orden_id: Optional[int]
    usuario_id: int
    cantidad: int
    motivo: str
    cuando: datetime


class HistorialPrecioResponse(BaseModel):
    """Contrato de salida para cambios de precio de un repuesto."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    repuesto_id: int
    usuario_id: int
    precio_anterior: Decimal
    precio_nuevo: Decimal
    cuando: datetime
