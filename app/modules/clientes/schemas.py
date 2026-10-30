from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class VehiculoCreate(BaseModel):
    """Contrato de entrada para registrar un vehículo."""

    model_config = ConfigDict(extra="forbid")

    patente: str = Field(..., min_length=1, max_length=10)
    marca: str = Field(..., min_length=1)
    modelo: str = Field(..., min_length=1)
    anio: int = Field(..., ge=1950, le=2100)


class VehiculoResponse(BaseModel):
    """Contrato de salida para vehículo."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente_id: int
    patente: str
    marca: str
    modelo: str
    anio: int
    borrado_en: Optional[datetime] = None


class ClienteCreate(BaseModel):
    """Contrato de entrada para registrar un cliente."""

    model_config = ConfigDict(extra="forbid")

    usuario_id: Optional[int] = None
    nombre: str = Field(..., min_length=1)
    documento: str = Field(..., min_length=1)
    telefono: str = Field(..., min_length=1)


class ClienteResponse(BaseModel):
    """Contrato de salida para cliente simple."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: Optional[int]
    nombre: str
    documento: str
    telefono: str


class ClienteDetalleResponse(ClienteResponse):
    """Contrato de salida para cliente con sus vehículos asociados."""

    vehiculos: list[VehiculoResponse] = []
