from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import func, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.paginacion import validar_y_calcular_paginacion
from app.core.repository import BaseRepository
from app.modules.usuarios.models import (
    AsignacionRol,
    EventoSeguridad,
    IntentoAcceso,
    Usuario,
)


class UsuarioRepository(BaseRepository[Usuario]):
    """Repositorio para la entidad Usuario."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Usuario, session)

    async def get_by_email(self, email: str) -> Optional[Usuario]:
        stmt = select(Usuario).where(Usuario.email == email)
        res = await self.session.execute(stmt)
        return res.scalars().first()


class AsignacionRolRepository(BaseRepository[AsignacionRol]):
    """Repositorio para la entidad AsignacionRol."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AsignacionRol, session)

    async def listar_por_usuario(self, usuario_id: int) -> list[AsignacionRol]:
        stmt = (
            select(AsignacionRol)
            .where(AsignacionRol.usuario_id == usuario_id)
            .order_by(AsignacionRol.desde.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_rol_activo(
        self,
        usuario_id: int,
        rol: str,
    ) -> Optional[AsignacionRol]:
        """Busca el rol activo (no revocado) de un usuario."""
        stmt = select(AsignacionRol).where(
            AsignacionRol.usuario_id == usuario_id,
            AsignacionRol.rol == rol,
            AsignacionRol.revocada_en.is_(None),
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def contar_admins_activos(self) -> int:
        """Cuenta administradores con rol vigente (RN-05 autoprotección)."""
        ahora = datetime.now(timezone.utc)
        stmt = (
            select(func.count(func.distinct(AsignacionRol.usuario_id)))
            .where(
                AsignacionRol.rol == "ADMIN",
                AsignacionRol.revocada_en.is_(None),
                or_(AsignacionRol.vence_en.is_(None), AsignacionRol.vence_en > ahora),
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar() or 0


class IntentoAccesoRepository(BaseRepository[IntentoAcceso]):
    """Repositorio para auditoría de límites de tasa en login (RN-08)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(IntentoAcceso, session)

    async def supero_limite_intentos(self, email: str, ip: str) -> bool:
        """Determina si se superaron 5 fallos en 60s desde la misma IP y correo (RN-08).

        Un login exitoso reinicia la cuenta; sólo cuentan los fallos posteriores al último éxito.
        """
        ahora = datetime.now(timezone.utc)
        ventana_60s = ahora - timedelta(seconds=60)

        # 1. Buscar fecha del último éxito para este email e IP
        stmt_exito = (
            select(func.max(IntentoAcceso.cuando))
            .where(
                IntentoAcceso.email == email,
                IntentoAcceso.ip == ip,
                IntentoAcceso.exito.is_(True),
            )
        )
        res_exito = await self.session.execute(stmt_exito)
        ultimo_exito = res_exito.scalar()

        # Determinar punto de corte temporal
        tiempo_corte = ventana_60s
        if ultimo_exito and ultimo_exito > ventana_60s:
            tiempo_corte = ultimo_exito

        # 2. Contar fallos ocurridos desde el punto de corte
        stmt_fallos = (
            select(func.count(IntentoAcceso.id))
            .where(
                IntentoAcceso.email == email,
                IntentoAcceso.ip == ip,
                IntentoAcceso.exito.is_(False),
                IntentoAcceso.cuando >= tiempo_corte,
            )
        )
        res_fallos = await self.session.execute(stmt_fallos)
        cantidad_fallos = res_fallos.scalar() or 0

        return cantidad_fallos >= 5


class EventoSeguridadRepository(BaseRepository[EventoSeguridad]):
    """Repositorio para auditoría de eventos de seguridad."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(EventoSeguridad, session)

    async def listar_paginado(
        self,
        page: int,
        size: int,
    ) -> tuple[list[EventoSeguridad], int, int]:
        count_stmt = select(func.count(EventoSeguridad.id))
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar() or 0

        pages, offset = validar_y_calcular_paginacion(total, page, size)

        stmt = (
            select(EventoSeguridad)
            .order_by(EventoSeguridad.cuando.desc())
            .offset(offset)
            .limit(size)
        )
        res = await self.session.execute(stmt)
        items = list(res.scalars().all())

        return items, total, pages
