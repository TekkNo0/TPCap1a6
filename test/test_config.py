import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_fails_without_password_and_secret(monkeypatch):
    """Verifica que si faltan POSTGRES_PASSWORD o JWT_SECRET_KEY, la app no arranca."""
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    # Forzar carga ignorando archivo .env temporalmente
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    errors = exc_info.value.errors()
    missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
    assert "POSTGRES_PASSWORD" in missing_fields
    assert "JWT_SECRET_KEY" in missing_fields


def test_database_url_computed(monkeypatch):
    """Verifica que @computed_field arme correctamente la URL con asyncpg."""
    settings = Settings(
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_db",
        POSTGRES_HOST="127.0.0.1",
        POSTGRES_PORT=5433,
        JWT_SECRET_KEY="test_secret",
        _env_file=None,
    )
    assert (
        settings.database_url
        == "postgresql+asyncpg://test_user:test_password@127.0.0.1:5433/test_db"
    )
