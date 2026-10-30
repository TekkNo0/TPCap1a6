"""Configuración general de pruebas y fixtures compartidos."""

import asyncio
import pytest
from seed import seed


@pytest.fixture(scope="session", autouse=True)
def reset_database_session():
    """Reinicia la base de datos con los datos del seed antes de ejecutar la suite de pruebas."""
    asyncio.run(seed())
