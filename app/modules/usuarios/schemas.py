from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validar_max_72_bytes(valor: str) -> str:
    """Valida que una contraseña no supere los 72 bytes en UTF-8 (límite de bcrypt)."""
    if len(valor.encode("utf-8")) > 72:
        raise ValueError("La contraseña no puede superar los 72 bytes.")
    if len(valor.strip()) == 0:
        raise ValueError("La contraseña no puede estar vacía.")
    return valor


class RegistroRequest(BaseModel):
    """Contrato de entrada para autorregistro público de clientes (RN-02).

    extra='forbid' impide que nadie se registre enviando roles u otros campos no autorizados.
    """

    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=3)
    nombre: str = Field(..., min_length=1)
    password: str = Field(...)
    documento: str = Field(..., min_length=1)
    telefono: str = Field(..., min_length=1)

    @field_validator("password")
    @classmethod
    def validar_password(cls, v: str) -> str:
        return _validar_max_72_bytes(v)


class LoginRequest(BaseModel):
    """Contrato de entrada para inicio de sesión."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=1)
    password: str = Field(...)

    @field_validator("password")
    @classmethod
    def validar_password(cls, v: str) -> str:
        return _validar_max_72_bytes(v)


class LoginResponse(BaseModel):
    """Contrato de salida para inicio de sesión exitoso.

    El token no se devuelve en el cuerpo: viaja exclusivamente en la cookie Set-Cookie.
    """

    mensaje: str = "Sesión iniciada"
    debe_cambiar_password: bool
    expira_en_segundos: int


class CambiarPasswordRequest(BaseModel):
    """Contrato de entrada para cambio de contraseña."""

    model_config = ConfigDict(extra="forbid")

    password_actual: str = Field(...)
    password_nueva: str = Field(...)

    @field_validator("password_actual", "password_nueva")
    @classmethod
    def validar_passwords(cls, v: str) -> str:
        return _validar_max_72_bytes(v)


class UsuarioResponse(BaseModel):
    """Contrato de salida para datos de usuario (sin password_hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nombre: str
    activo: bool
    debe_cambiar_password: bool
    password_cambiada_en: Optional[datetime] = None


class UsuarioYoResponse(BaseModel):
    """Contrato de salida para GET /auth/yo."""

    usuario: UsuarioResponse
    roles_vigentes_bd: list[str]
    roles_en_token: list[str]


class UsuarioPersonalCreate(BaseModel):
    """Contrato de entrada para alta de personal por un administrador."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=3)
    nombre: str = Field(..., min_length=1)
    password_provisoria: str = Field(...)
    rol: str = Field(...)

    @field_validator("password_provisoria")
    @classmethod
    def validar_password(cls, v: str) -> str:
        return _validar_max_72_bytes(v)

    @field_validator("rol")
    @classmethod
    def validar_rol(cls, v: str) -> str:
        permitidos = {"ADMIN", "RECEPCION", "MECANICO"}
        if v not in permitidos:
            raise ValueError(f"El rol de personal debe ser uno de: {', '.join(permitidos)}")
        return v


class AsignarRolRequest(BaseModel):
    """Contrato de entrada para asignación de un rol por un administrador."""

    model_config = ConfigDict(extra="forbid")

    rol: str = Field(...)
    vence_en: Optional[datetime] = None

    @field_validator("rol")
    @classmethod
    def validar_rol(cls, v: str) -> str:
        permitidos = {"ADMIN", "RECEPCION", "MECANICO", "CLIENTE"}
        if v not in permitidos:
            raise ValueError(f"Rol inválido. Debe ser uno de: {', '.join(permitidos)}")
        return v

    @field_validator("vence_en")
    @classmethod
    def validar_vencimiento(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None:
            # Debe tener zona horaria explícita
            if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
                raise ValueError("La fecha de vencimiento debe incluir zona horaria.")
            # Debe ser en el futuro
            if v <= datetime.now(timezone.utc):
                raise ValueError("La fecha de vencimiento debe ser futura.")
        return v


class AsignacionRolResponse(BaseModel):
    """Contrato de salida para asignación de rol."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    rol: str
    desde: datetime
    vence_en: Optional[datetime] = None
    revocada_en: Optional[datetime] = None
    otorgada_por: Optional[int] = None


class EventoSeguridadResponse(BaseModel):
    """Contrato de salida para auditoría de eventos de seguridad."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cuando: datetime
    actor: str
    accion: str
