import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_caso_c10_alta_orden_y_repuesto_inexistente():
    """Caso C-10: Alta de orden con 2 ítems -> 201 con precios, total e historial.

    Con repuesto inexistente -> 409 y nada queda guardado.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            # Login como RECEPCION
            await client.post("/auth/login", json={"email": "recepcion@example.com", "password": "Password123!"})

            # 1. Repuesto inexistente (id=9999) -> 409
            body_fail = {
                "vehiculo_id": 1,
                "falla": "Falla prueba inexistente",
                "items": [{"repuesto_id": 9999, "cantidad": 1}],
            }
            res_fail = await client.post("/ordenes", json=body_fail)
            assert res_fail.status_code == 409
            assert "no disponible o inexistente" in res_fail.json()["detail"]

            # 2. Alta con 2 ítems válidos (REP-01 precio 8500 x 1, REP-02 precio 22000 x 2 = 52500)
            body_ok = {
                "vehiculo_id": 1,
                "falla": "Cambio de aceite y frenos delanteros",
                "items": [
                    {"repuesto_id": 1, "cantidad": 1},
                    {"repuesto_id": 2, "cantidad": 2},
                ],
            }
            res_ok = await client.post("/ordenes", json=body_ok)
            assert res_ok.status_code == 201
            data = res_ok.json()
            assert data["estado"] == "PENDIENTE"
            assert data["total"] == "52500.00"
            assert len(data["items"]) == 2
            assert data["items"][0]["precio_unitario"] == "8500.00"
            assert data["items"][0]["subtotal"] == "8500.00"
            assert data["items"][1]["precio_unitario"] == "22000.00"
            assert data["items"][1]["subtotal"] == "44000.00"
            # Primera línea de historial
            assert len(data["historial"]) == 1
            assert data["historial"][0]["hasta_estado"] == "PENDIENTE"


@pytest.mark.asyncio
async def test_caso_c11_terminar_orden_stock_insuficiente_rollback():
    """Caso C-11: Terminar la orden 2 (pide 4 bujías, hay 2 en stock) -> 409.

    El estado, el stock, los movimientos y el historial quedan exactamente como estaban.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            # Login como el mecánico asignado a la orden 2 (mecanico@example.com)
            await client.post("/auth/login", json={"email": "mecanico@example.com", "password": "Password123!"})

            # La orden 2 ya está en EN_REPARACION por seed.py y pide 4 bujías (stock actual es 2)
            res_terminar = await client.post("/ordenes/2/terminar")
            assert res_terminar.status_code == 409
            assert "Stock insuficiente" in res_terminar.json()["detail"]

            # Verificar que la orden sigue EN_REPARACION
            res_detalle = await client.get("/ordenes/2")
            assert res_detalle.status_code == 200
            assert res_detalle.json()["estado"] == "EN_REPARACION"

            # Verificar que el stock de la bujía (id=3) no cambió (sigue en 2)
            res_rep = await client.get("/repuestos/3")
            assert res_rep.status_code == 200
            assert res_rep.json()["stock"] == 2


@pytest.mark.asyncio
async def test_caso_c12_reponer_y_terminar_orden():
    """Caso C-12: Reponer repuesto y terminar orden 2 -> 200 OK y descuento atómico de stock."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            # 1. Login como ADMIN para reponer stock
            await client.post("/auth/login", json={"email": "admin@example.com", "password": "Password123!"})

            # Reponer 10 bujías (id=3)
            res_reponer = await client.post("/repuestos/3/reponer", json={"cantidad": 10, "motivo": "Reposición de bujías"})
            assert res_reponer.status_code == 200
            assert res_reponer.json()["stock"] == 12  # 2 + 10 = 12

            # 2. Login como el mecánico asignado para terminar la orden 2
            await client.post("/auth/login", json={"email": "mecanico@example.com", "password": "Password123!"})
            res_terminar = await client.post("/ordenes/2/terminar")
            assert res_terminar.status_code == 200
            data_term = res_terminar.json()
            assert data_term["estado"] == "TERMINADA"

            # 3. Validar que el stock bajó en 4 unidades (12 - 4 = 8)
            res_rep_post = await client.get("/repuestos/3")
            assert res_rep_post.json()["stock"] == 8

            # 4. Validar que la línea de historial TERMINADA existe
            assert any(h["hasta_estado"] == "TERMINADA" for h in data_term["historial"])


@pytest.mark.asyncio
async def test_caso_c13_cancelar_permisos_y_estados():
    """Caso C-13:

    1. El dueño cancela su orden pendiente -> 200 OK.
    2. Intentar cancelar orden ajena -> 403 Forbidden.
    3. Intentar cancelar orden ya terminada -> 409 Conflict.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            # Laura es la dueña del vehículo 1 (orden 1 en PENDIENTE)
            await client.post("/auth/login", json={"email": "cliente@example.com", "password": "Password123!"})

            # 1. Laura cancela su propia orden 1 -> 200 OK
            res_canc = await client.post("/ordenes/1/cancelar")
            assert res_canc.status_code == 200
            assert res_canc.json()["estado"] == "CANCELADA"

            # 2. Laura intenta cancelar la orden 2 (es del vehículo de Jorge) -> 403 (RN-12)
            res_ajena = await client.post("/ordenes/2/cancelar")
            assert res_ajena.status_code == 403

            # 3. Intentar cancelar una orden terminada con ADMIN -> 409
            await client.post("/auth/login", json={"email": "admin@example.com", "password": "Password123!"})
            res_terminada = await client.post("/ordenes/2/cancelar")
            assert res_terminada.status_code == 409


@pytest.mark.asyncio
async def test_caso_c17_catalogo_estados_y_filtro_invalido():
    """Caso C-17: Catálogo por posición, TERMINADA y CANCELADA finales; filtro inválido responde 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            await client.post("/auth/login", json={"email": "recepcion@example.com", "password": "Password123!"})

            # 1. Catálogo de estados
            res_cat = await client.get("/estados-orden")
            assert res_cat.status_code == 200
            estados = res_cat.json()
            assert len(estados) == 4
            codigos = [e["codigo"] for e in estados]
            assert codigos == ["PENDIENTE", "EN_REPARACION", "TERMINADA", "CANCELADA"]
            assert estados[2]["es_final"] is True
            assert estados[3]["es_final"] is True

            # 2. Filtrar órdenes por un estado no contemplado en el enum/contrato -> 422
            res_invalido = await client.get("/ordenes", params={"estado": "ESTADO_INEXISTENTE"})
            assert res_invalido.status_code == 422
