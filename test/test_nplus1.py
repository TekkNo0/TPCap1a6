import asyncio
from sqlalchemy import event
import pytest
from httpx import ASGITransport, AsyncClient

import main
from main import app
from app.core.config import get_settings
from app.core.database import create_db_engine, create_session_factory
from app.modules.ordenes.repository import OrdenTrabajoRepository


@pytest.mark.asyncio
async def test_caso_c15_sin_n_plus_1_consultas_fijas():
    """Caso C-15: Detalle de orden con 2 y con 4 ítems ejecuta la misma cantidad fija de consultas."""
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    queries = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def capturar_query(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    async with session_factory() as session:
        repo = OrdenTrabajoRepository(session)

        # Consulta orden 1
        queries.clear()
        orden1 = await repo.get_detalle_completo(1)
        count_orden1 = len(queries)

        # Consulta orden 2
        queries.clear()
        orden2 = await repo.get_detalle_completo(2)
        count_orden2 = len(queries)

        # Deben ser exactamente la misma cantidad fija de consultas
        assert count_orden1 == count_orden2
        assert count_orden1 == 6

    await engine.dispose()
