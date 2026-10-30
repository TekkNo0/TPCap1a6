import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from main import app


@pytest.mark.asyncio
async def test_health_live_endpoint():
    """Valida que GET /health/live responda 200 sin depender de la base de datos."""
    # Lifespan mockeado para no requerir conexión real a postgres durante el test unitario
    with (
        patch("main.create_db_engine"),
        patch("main.create_session_factory"),
        patch("main.generate_dummy_hash", new_callable=AsyncMock, return_value="$2b$12$dummyhashvalue"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health/live")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["live"] is True


@pytest.mark.asyncio
async def test_health_ready_503_when_database_fails():
    """Valida que GET /health/ready responda 503 si la base de datos no contesta."""
    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("Connection refused")

    async def override_get_session():
        yield mock_session

    from app.core.database import get_session
    app.dependency_overrides[get_session] = override_get_session

    try:
        with (
            patch("main.create_db_engine"),
            patch("main.create_session_factory"),
            patch("main.generate_dummy_hash", new_callable=AsyncMock, return_value="$2b$12$dummyhashvalue"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/health/ready")
                assert response.status_code == 503
                data = response.json()
                assert "La base de datos no se encuentra disponible" in data["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_ready_200_when_database_ok():
    """Valida que GET /health/ready responda 200 cuando SELECT 1 funciona."""
    from unittest.mock import MagicMock
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_session.execute.return_value = mock_result

    async def override_get_session():
        yield mock_session

    from app.core.database import get_session
    app.dependency_overrides[get_session] = override_get_session

    try:
        with (
            patch("main.create_db_engine"),
            patch("main.create_session_factory"),
            patch("main.generate_dummy_hash", new_callable=AsyncMock, return_value="$2b$12$dummyhashvalue"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/health/ready")
                assert response.status_code == 200
                data = response.json()
                assert data["ready"] is True
                assert data["database"] == "connected"
    finally:
        app.dependency_overrides.clear()
