import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_listar_repuestos_envoltorio_paginacion():
    """Valida el envoltorio {items, total, page, size, pages} y size por defecto."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with app.router.lifespan_context(app):
            # Iniciar sesión como ADMIN
            await client.post("/auth/login", json={"email": "admin@example.com", "password": "Password123!"})
            response = await client.get("/repuestos")
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert "total" in data
            assert "page" in data
            assert "size" in data
            assert "pages" in data
            assert data["page"] == 1
            assert data["size"] == 20


@pytest.mark.asyncio
async def test_caso_c16_busqueda_paginacion_y_patch():
    """Caso C-16 de la consigna:

    1. Búsqueda con ' OR '1'='1 -> Lista vacía con total 0.
    2. Con q=freno&size=1 -> total 1 y pages 1, y page=2 da 422.
    3. size=500 -> 422 (límite máximo 100).
    4. PATCH parcial sólo cambia lo enviado (exclude_unset).
    5. Intentar editar stock por PATCH -> 422 (extra='forbid').
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with app.router.lifespan_context(app):
            # Iniciar sesión como ADMIN
            await client.post("/auth/login", json={"email": "admin@example.com", "password": "Password123!"})

            # 1. Búsqueda con intento de inyección SQL
            res_injection = await client.get("/repuestos", params={"q": "' OR '1'='1"})
            assert res_injection.status_code == 200
            data_inj = res_injection.json()
            assert data_inj["total"] == 0
            assert len(data_inj["items"]) == 0
            assert data_inj["pages"] == 1

            # 2. Con q=freno&size=1 -> total 1, pages 1, y page=2 da 422
            res_filtro = await client.get("/repuestos", params={"q": "freno", "size": 1, "page": 1})
            assert res_filtro.status_code == 200
            data_filtro = res_filtro.json()
            assert data_filtro["total"] == 1
            assert data_filtro["pages"] == 1

            res_pagina_invalida = await client.get("/repuestos", params={"q": "freno", "size": 1, "page": 2})
            assert res_pagina_invalida.status_code == 422
            assert "La página 2 no existe: hay 1" in res_pagina_invalida.json()["detail"]

            # 3. size=500 -> 422
            res_size_max = await client.get("/repuestos", params={"size": 500})
            assert res_size_max.status_code == 422

            # 4. PATCH parcial: sólo cambia lo enviado (modificamos descripción del repuesto 1)
            res_patch = await client.patch("/repuestos/1", json={"descripcion": "Filtro de aceite alto rendimiento"})
            assert res_patch.status_code == 200
            data_patch = res_patch.json()
            assert data_patch["descripcion"] == "Filtro de aceite alto rendimiento"
            # El precio no debe haberse modificado ni borrado
            assert data_patch["precio"] == "8500.00"

            # 5. Intentar editar stock por PATCH -> 422 debido a extra='forbid'
            res_patch_stock = await client.patch("/repuestos/1", json={"stock": 999})
            assert res_patch_stock.status_code == 422


@pytest.mark.asyncio
async def test_dar_de_baja_vehiculo_con_orden_abierta_rechaza_409():
    """Valida RN-16: Vehículo con órdenes abiertas no se puede dar de baja (409)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with app.router.lifespan_context(app):
            # Iniciar sesión como ADMIN
            await client.post("/auth/login", json={"email": "admin@example.com", "password": "Password123!"})

            # El vehículo 1 (de Laura) tiene la orden 1 en PENDIENTE
            response = await client.delete("/vehiculos/1")
            assert response.status_code == 409
            assert "órdenes de trabajo abiertas" in response.json()["detail"]


@pytest.mark.asyncio
async def test_crear_repuesto_duplicado_rechaza_409():
    """Valida RN-01: Código duplicado rechaza con 409."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with app.router.lifespan_context(app):
            # Iniciar sesión como ADMIN
            await client.post("/auth/login", json={"email": "admin@example.com", "password": "Password123!"})

            # REP-01 ya existe en seed.py
            body = {
                "codigo": "REP-01",
                "descripcion": "Duplicado",
                "precio": "1000.00",
                "stock_inicial": 5,
            }
            response = await client.post("/repuestos", json=body)
            assert response.status_code == 409
