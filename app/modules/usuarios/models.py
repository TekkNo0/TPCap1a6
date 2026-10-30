from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, DateTime, Index, text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.clientes.models import Cliente


class Usuario(SQLModel, table=True):
    """Modelo de usuario del sistema (personal o cliente)."""

    __tablename__ = "usuario"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(sa_column_kwargs={"unique": True}, index=True)
    nombre: str
    password_hash: str
    activo: bool = Field(default=True)
    debe_cambiar_password: bool = Field(default=False)
    password_cambiada_en: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )

    # Relación 1 a N con roles
    roles: list["AsignacionRol"] = Relationship(
        back_populates="usuario",
        sa_relationship_kwargs={"foreign_keys": "AsignacionRol.usuario_id"},
    )

    # Relación 1 a 1 con Cliente ("Usuario.cliente devuelve un objeto y no una lista")
    cliente: Optional["Cliente"] = Relationship(
        back_populates="usuario",
        sa_relationship_kwargs={"uselist": False},
    )


class AsignacionRol(SQLModel, table=True):
    """Asignación de roles con vigencia e historial de revocación."""

    __tablename__ = "asignacion_rol"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    rol: str = Field(...)
    desde: datetime = Field(sa_type=DateTime(timezone=True))
    vence_en: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    revocada_en: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    otorgada_por: Optional[int] = Field(default=None, foreign_key="usuario.id", index=True)

    usuario: Optional[Usuario] = Relationship(
        back_populates="roles",
        sa_relationship_kwargs={"foreign_keys": "AsignacionRol.usuario_id"},
    )

    __table_args__ = (
        CheckConstraint(
            "rol IN ('ADMIN', 'RECEPCION', 'MECANICO', 'CLIENTE')",
            name="ck_asignacion_rol_tipo",
        ),
        # Índice único parcial: sólo un rol activo/no revocado por usuario
        Index(
            "ix_asignacion_rol_usuario_rol_activa",
            "usuario_id",
            "rol",
            unique=True,
            postgresql_where=text("revocada_en IS NULL"),
        ),
    )


class IntentoAcceso(SQLModel, table=True):
    """Registro de intentos de acceso para límite de tasa y seguridad (RN-08)."""

    __tablename__ = "intento_acceso"

    id: Optional[int] = Field(default=None, primary_key=True)
    cuando: datetime = Field(sa_type=DateTime(timezone=True))
    email: str
    ip: str
    exito: bool

    __table_args__ = (
        Index("ix_intento_acceso_email_ip_cuando", "email", "ip", "cuando"),
    )


class EventoSeguridad(SQLModel, table=True):
    """Registro de auditoría de eventos de seguridad relevantes."""

    __tablename__ = "evento_seguridad"

    id: Optional[int] = Field(default=None, primary_key=True)
    cuando: datetime = Field(sa_type=DateTime(timezone=True))
    actor: str  # texto del actor responsable
    accion: str
