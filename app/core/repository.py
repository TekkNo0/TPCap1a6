from datetime import datetime, timezone
from typing import Any, Generic, Optional, Type, TypeVar
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Repositorio base genérico para operaciones CRUD de persistencia.

    Recibe en su constructor la sesión y la clase del modelo (sección 6.4.3).
    add() y update() ejecutan flush(), NUNCA commit() (sección 6.4.4).
    """

    def __init__(self, model_class: Type[T], session: AsyncSession) -> None:
        self.model_class = model_class
        self.session = session

    async def get_by_id(self, id_val: Any) -> Optional[T]:
        """Obtiene una entidad por su clave primaria."""
        return await self.session.get(self.model_class, id_val)

    async def get_all(self) -> list[T]:
        """Obtiene todas las entidades registradas."""
        stmt = select(self.model_class)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def count(self) -> int:
        """Retorna la cantidad total de entidades en la tabla."""
        stmt = select(func.count()).select_from(self.model_class)
        res = await self.session.execute(stmt)
        return res.scalar() or 0

    async def add(self, entity: T) -> T:
        """Agrega una entidad y ejecuta flush() (sección 6.4.4)."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: T) -> T:
        """Sincroniza cambios de una entidad mediante flush() (sección 6.4.4)."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: T) -> None:
        """Elimina físicamente una entidad de la sesión y ejecuta flush()."""
        await self.session.delete(entity)
        await self.session.flush()


class SoftDeleteRepository(BaseRepository[T]):
    """Repositorio especializado para entidades con borrado lógico (columna borrado_en).

    Filtra por defecto los dados de baja (sección 6.4.2).
    """

    async def get_by_id(self, id_val: Any) -> Optional[T]:
        """Obtiene una entidad activa (borrado_en IS NULL)."""
        stmt = select(self.model_class).where(
            self.model_class.id == id_val,  # type: ignore[attr-defined]
            self.model_class.borrado_en.is_(None),  # type: ignore[attr-defined]
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_active_by_id(self, id_val: Any) -> Optional[T]:
        """Alias compatible para obtener entidad activa."""
        return await self.get_by_id(id_val)

    async def get_by_id_including_deleted(self, id_val: Any) -> Optional[T]:
        """Obtiene la entidad por clave primaria sin filtrar dados de baja (sección 6.4.2)."""
        return await super().get_by_id(id_val)

    async def get_all(self) -> list[T]:
        """Obtiene todas las entidades activas."""
        stmt = select(self.model_class).where(
            self.model_class.borrado_en.is_(None)  # type: ignore[attr-defined]
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def count(self) -> int:
        """Retorna la cantidad de entidades activas."""
        stmt = (
            select(func.count())
            .select_from(self.model_class)
            .where(self.model_class.borrado_en.is_(None))  # type: ignore[attr-defined]
        )
        res = await self.session.execute(stmt)
        return res.scalar() or 0

    async def soft_delete(self, entity: T, cuando: Optional[datetime] = None) -> None:
        """Marca la entidad como borrada lógicamente estableciendo borrado_en (sección 6.4.2)."""
        if cuando is None:
            cuando = datetime.now(timezone.utc)
        setattr(entity, "borrado_en", cuando)
        await self.session.flush()
