from datetime import datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_caso_c02_registro_y_duplicados():
    """Caso C-02: Registro; correo y documento repetidos -> 201; 409 con mensaje propio."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            # 1. Registro exitoso
            body = {
                "email": "nuevo_cliente@test.com",
                "nombre": "Nuevo Cliente",
                "password": "Password123!",
                "documento": "99887766",
                "telefono": "1133221100",
            }
            res = await client.post("/auth/registro", json=body)
            assert res.status_code == 201
            data = res.json()
            assert data["email"] == "nuevo_cliente@test.com"
            assert "password_hash" not in data

            # 2. Correo repetido -> 409
            body_email_dup = {**body, "documento": "11223344"}
            res_dup_email = await client.post("/auth/registro", json=body_email_dup)
            assert res_dup_email.status_code == 409
            assert "correo" in res_dup_email.json()["detail"].lower()

            # 3. Documento repetido -> 409
            body_doc_dup = {**body, "email": "otro_correo@test.com"}
            res_dup_doc = await client.post("/auth/registro", json=body_doc_dup)
            assert res_dup_doc.status_code == 409
            assert "documento" in res_dup_doc.json()["detail"].lower()


@pytest.mark.asyncio
async def test_caso_c03_cookie_login_y_cuerpo_sin_token():
    """Caso C-03: Cookie con HttpOnly, SameSite=Lax, Max-Age; sin token en cuerpo; header Auth da 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            res = await client.post(
                "/auth/login",
                json={"email": "admin@example.com", "password": "Password123!"},
            )
            assert res.status_code == 200
            data = res.json()
            # El cuerpo no trae el token
            assert "token" not in data
            assert "access_token" not in data
            assert data["mensaje"] == "Sesión iniciada"

            # La cookie access_token viaja en encabezados
            assert "access_token" in res.cookies
            set_cookie = res.headers.get("set-cookie", "")
            assert "HttpOnly" in set_cookie
            assert "samesite=lax" in set_cookie.lower()
            assert "Max-Age" in set_cookie

            # Sin cookie o con Authorization: Bearer en ruta protegida da 401
            client_sin_cookie = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
            res_sin_auth = await client_sin_cookie.get("/repuestos")
            assert res_sin_auth.status_code == 401

            res_con_bearer = await client_sin_cookie.get(
                "/repuestos", headers={"Authorization": "Bearer tokeninventado"}
            )
            assert res_con_bearer.status_code == 401


@pytest.mark.asyncio
async def test_caso_c04_login_credenciales_invalidas_tiempo_parecido():
    """Caso C-04: Correo existente con contraseña errónea y correo inexistente -> ambos 401 con mismo cuerpo."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            # 1. Correo existente, contraseña mala
            res_existente_mala = await client.post(
                "/auth/login",
                json={"email": "admin@example.com", "password": "PasswordIncorrecta!"},
            )
            assert res_existente_mala.status_code == 401
            data_1 = res_existente_mala.json()

            # 2. Correo inexistente
            res_inexistente = await client.post(
                "/auth/login",
                json={"email": "no_existe_9999@example.com", "password": "PasswordIncorrecta!"},
            )
            assert res_inexistente.status_code == 401
            data_2 = res_inexistente.json()

            # Mismo cuerpo de error (RN-09)
            assert data_1["detail"] == data_2["detail"] == "Credenciales inválidas."


@pytest.mark.asyncio
async def test_caso_c05_limite_de_intentos_429():
    """Caso C-05: Seis intentos fallidos seguidos -> el sexto responde 429 con Retry-After."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            email_rate = "ataque@example.com"
            # 5 intentos fallidos
            for _ in range(5):
                r = await client.post("/auth/login", json={"email": email_rate, "password": "bad"})
                assert r.status_code == 401

            # El sexto intento debe ser rechazado inmediatamente con 429
            r_sexto = await client.post("/auth/login", json={"email": email_rate, "password": "bad"})
            assert r_sexto.status_code == 429
            assert "Retry-After" in r_sexto.headers
            assert r_sexto.headers["Retry-After"] == "60"


@pytest.mark.asyncio
async def test_caso_c07_revocar_rol_sesion_abierta_y_vencimientos():
    """Caso C-07:

    1. Revocar rol a recepcion con sesión abierta -> la misma cookie da 403 en petición siguiente.
    2. Vencimiento en el pasado o sin zona horaria -> responde 422.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as admin_client:
        async with app.router.lifespan_context(app):
            # Login admin
            res_adm = await admin_client.post("/auth/login", json={"email": "admin@example.com", "password": "Password123!"})
            assert res_adm.status_code == 200

            # Vencimiento sin zona horaria -> 422
            res_sin_tz = await admin_client.post(
                "/usuarios/3/roles",
                json={"rol": "MECANICO", "vence_en": "2030-01-01T12:00:00"},
            )
            assert res_sin_tz.status_code == 422

            # Vencimiento en el pasado -> 422
            res_pasado = await admin_client.post(
                "/usuarios/3/roles",
                json={"rol": "MECANICO", "vence_en": "2020-01-01T12:00:00Z"},
            )
            assert res_pasado.status_code == 422

            # Sesión de recepcionista (id=3 en seed.py)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as recep_client:
                login_rec = await recep_client.post("/auth/login", json={"email": "recepcion@example.com", "password": "Password123!"})
                assert login_rec.status_code == 200

                # Antes de revocar: recepcionista accede a /repuestos
                rep_ok = await recep_client.get("/repuestos")
                assert rep_ok.status_code == 200

                # Admin revoca el rol RECEPCION del usuario 3
                rev = await admin_client.delete("/usuarios/3/roles/RECEPCION")
                assert rev.status_code == 200
                assert rev.json()["revocada_en"] is not None

                # Inmediatamente: la misma cookie de recepcionista ahora da 403 (RN-04)
                rep_bloqueado = await recep_client.get("/repuestos")
                assert rep_bloqueado.status_code == 403

                # /auth/yo muestra que en la BD ya no tiene roles vigentes pero en el token aún figura
                yo_res = await recep_client.get("/auth/yo")
                assert yo_res.status_code == 200
                yo_data = yo_res.json()
                assert "RECEPCION" not in yo_data["roles_vigentes_bd"]
                assert "RECEPCION" in yo_data["roles_en_token"]

            # Restaurar rol RECEPCION al usuario 3 para los siguientes tests
            await admin_client.post("/usuarios/3/roles", json={"rol": "RECEPCION"})


@pytest.mark.asyncio
async def test_caso_c08_autoproteccion_admin():
    """Caso C-08: El administrador no se puede revocar su propio rol ADMIN -> 409."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            # Login admin (id=1)
            await client.post("/auth/login", json={"email": "admin@example.com", "password": "Password123!"})

            res = await client.delete("/usuarios/1/roles/ADMIN")
            assert res.status_code == 409
            assert "administrador no puede revocarse a sí mismo" in res.json()["detail"]


@pytest.mark.asyncio
async def test_caso_c09_cambio_obligatorio_password():
    """Caso C-09:

    Usuario con cambio obligatorio queda bloqueado (403) en grupo protegido;
    luego del cambio, la nueva cookie vale y la anterior da 401.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            # nuevo@example.com tiene debe_cambiar_password = True
            login_res = await client.post(
                "/auth/login",
                json={"email": "nuevo@example.com", "password": "Password123!"},
            )
            assert login_res.status_code == 200
            assert login_res.json()["debe_cambiar_password"] is True
            cookie_antigua = client.cookies.get("access_token")

            # Intento de entrar a grupo protegido (/repuestos) -> 403
            res_bloqueado = await client.get("/repuestos")
            assert res_bloqueado.status_code == 403
            assert "cambiar su contraseña obligatoriamente" in res_bloqueado.json()["detail"]

            # Realizar el cambio de contraseña
            res_cambio = await client.post(
                "/auth/cambiar-password",
                json={
                    "password_actual": "Password123!",
                    "password_nueva": "PasswordNueva456!",
                },
            )
            assert res_cambio.status_code == 200

            # Con la nueva cookie, ya no está bloqueado -> puede acceder a /repuestos (tiene rol MECANICO)
            res_acceso_ok = await client.get("/repuestos")
            assert res_acceso_ok.status_code == 200

            # Con la cookie antigua en un cliente separado -> da 401 (RN-07)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client_viejo:
                client_viejo.cookies.set("access_token", cookie_antigua)
                res_invalido = await client_viejo.get("/auth/yo")
                assert res_invalido.status_code == 401
                assert "invalidada por cambio de contraseña" in res_invalido.json()["detail"]
