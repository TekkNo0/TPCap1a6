from typing import Any
from sqlmodel.ext.asyncio.session import AsyncSession


class UnitOfWork:
    """Clase base de Unit of Work.

    Administra la transacción atómica: confirma si el bloque context manager
    concluye sin errores, o revierte (rollback) en caso de excepción.
    Importante: No cierra la sesión (su ciclo de vida pertenece a get_session).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> "UnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()

    async def commit(self) -> None:
        """Confirma la transacción actual en la base de datos."""
        await self.session.commit()

    async def rollback(self) -> None:
        """Revierte los cambios de la transacción actual."""
        await self.session.rollback()
