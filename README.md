# Taller Mecánico API · Programación III (Capítulos 1 a 6)

API asincrónica construida con **FastAPI**, **SQLModel**, **SQLAlchemy 2.0 (asincrónico)** y **PostgreSQL**, estructurada en capas limpias y testeada exhaustivamente:
`Router` → `Service` → `Unit of Work` → `Repository` → `Model`.

---

## 🚀 Requisitos Previos

- **Python:** 3.12 o superior (probado en Python 3.14).
- **PostgreSQL:** 16 o superior (probado en PostgreSQL 17 con puerto 5432).

---

## 🛠️ Puesta en Marcha desde Cero

### 1. Clonar el repositorio y ubicarse en el directorio
```bash
git clone <url-del-repositorio>
cd Antigravity
```

### 2. Crear y activar el entorno virtual
En Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

En Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar las dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar el archivo `.env`
Copiar la plantilla de ejemplo:
```powershell
copy env.example .env
```

Generar una clave de firma segura para JWT mediante Python:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Completar los valores en `.env` (el archivo `.env` está ignorado en Git):
```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_password_aqui
POSTGRES_DB=taller_mecanico
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
SQL_ECHO=false

JWT_SECRET_KEY=clave_generada_anteriormente
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
COOKIE_SECURE=false

BCRYPT_ROUNDS=12
```

### 5. Crear la Base de Datos y Aplicar Migraciones
En `psql`:
```sql
CREATE DATABASE taller_mecanico;
```

Ejecutar las migraciones asincrónicas con Alembic:
```powershell
alembic upgrade head
```

### 6. Cargar los Datos Iniciales (Seed)
```powershell
python seed.py
```

### 7. Iniciar el Servidor de Desarrollo
```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
La documentación interactiva Swagger UI estará disponible en: `http://localhost:8000/docs`

---

## 🧪 Ejecución de Pruebas Automatizadas

Ejecutar la suite completa de 26 pruebas con `pytest`:
```powershell
pytest -v
```

---

## 📸 Evidencias de Casos de Evaluación

### Evidencia del Caso C-14: Disparador de Sólo Agregado y Clave Foránea
Ejecución en `psql`:
```bash
psql -U postgres -d taller_mecanico -f test/solo_agregado.sql
```

Salida obtenida en consola:
```text
psql:test/solo_agregado.sql:9: ERROR:  Operación rechazada: la tabla historial_estado_orden es de sólo agregado (append-only). Prohibido modificar o borrar filas.
CONTEXTO:  función PL/pgSQL rechazar_modificacion_solo_agregado() en la línea 3 en RAISE
psql:test/solo_agregado.sql:10: ERROR:  Operación rechazada: la tabla historial_estado_orden es de sólo agregado (append-only). Prohibido modificar o borrar filas.
CONTEXTO:  función PL/pgSQL rechazar_modificacion_solo_agregado() en la línea 3 en RAISE
psql:test/solo_agregado.sql:13: ERROR:  Operación rechazada: la tabla movimiento_stock es de sólo agregado (append-only). Prohibido modificar o borrar filas.
CONTEXTO:  función PL/pgSQL rechazar_modificacion_solo_agregado() en la línea 3 en RAISE
psql:test/solo_agregado.sql:14: ERROR:  Operación rechazada: la tabla movimiento_stock es de sólo agregado (append-only). Prohibido modificar o borrar filas.
CONTEXTO:  función PL/pgSQL rechazar_modificacion_solo_agregado() en la línea 3 en RAISE
psql:test/solo_agregado.sql:17: ERROR:  Operación rechazada: la tabla historial_precio_repuesto es de sólo agregado (append-only). Prohibido modificar o borrar filas.
CONTEXTO:  función PL/pgSQL rechazar_modificacion_solo_agregado() en la línea 3 en RAISE
psql:test/solo_agregado.sql:18: ERROR:  Operación rechazada: la tabla historial_precio_repuesto es de sólo agregado (append-only). Prohibido modificar o borrar filas.
CONTEXTO:  función PL/pgSQL rechazar_modificacion_solo_agregado() en la línea 3 en RAISE
psql:test/solo_agregado.sql:22: ERROR:  inserción o actualización en la tabla «orden_trabajo» viola la llave foránea «fk_orden_trabajo_estado»
DETALLE:  La llave (estado)=(ESTADO_INVENTADO) no está presente en la tabla «estado_orden».
```

---

### Evidencia del Caso C-15: Lecturas sin N+1 (Consultas fijas)
Se verifica que la consulta del detalle completo de una orden con 2 ítems y de otra con 4 ítems ejecuta **exactamente la misma cantidad fija de 6 consultas SQL** mediante precarga (`selectinload`), sin escalar según el número de ítems:

```text
Orden con 2 ítems: 6 consultas ejecutadas
  [1] SELECT orden_trabajo... FROM orden_trabajo WHERE orden_trabajo.id = 1
  [2] SELECT historial_estado_orden... FROM historial_estado_orden WHERE historial_estado_orden.orden_id IN (1)
  [3] SELECT item_orden... FROM item_orden WHERE item_orden.orden_id IN (1)
  [4] SELECT vehiculo... FROM vehiculo WHERE vehiculo.id IN (1)
  [5] SELECT repuesto... FROM repuesto WHERE repuesto.id IN (1, 2)
  [6] SELECT cliente... FROM cliente WHERE cliente.id IN (1)

Orden con 4 ítems: 6 consultas ejecutadas
  [1] SELECT orden_trabajo... FROM orden_trabajo WHERE orden_trabajo.id = 2
  [2] SELECT historial_estado_orden... FROM historial_estado_orden WHERE historial_estado_orden.orden_id IN (2)
  [3] SELECT item_orden... FROM item_orden WHERE item_orden.orden_id IN (2)
  [4] SELECT vehiculo... FROM vehiculo WHERE vehiculo.id IN (2)
  [5] SELECT repuesto... FROM repuesto WHERE repuesto.id IN (1, 2, 3, 4)
  [6] SELECT cliente... FROM cliente WHERE cliente.id IN (2)
```

---

## 📁 Archivos de Prueba Interactiva (REST Client)

En la carpeta [`test/`](file:///c:/Users/maxim/Desktop/Antigravity/test) se encuentran los casos interactivos para ejecutar directamente desde el editor:
- [`test/health.http`](file:///c:/Users/maxim/Desktop/Antigravity/test/health.http): Verificación de estado `/health/live` y `/health/ready`.
- [`test/auth.http`](file:///c:/Users/maxim/Desktop/Antigravity/test/auth.http): Registro, login con cookies HttpOnly, errores de temporización y cambio obligatorio de contraseña.
- [`test/usuarios.http`](file:///c:/Users/maxim/Desktop/Antigravity/test/usuarios.http): Gestión de roles, revocación en vivo multi-sesión (`# @no-cookie-jar`), autoprotección y eventos de auditoría.
- [`test/repuestos.http`](file:///c:/Users/maxim/Desktop/Antigravity/test/repuestos.http): CRUD con búsqueda parametrizada, reposición y protección de stock en PATCH.
- [`test/clientes.http`](file:///c:/Users/maxim/Desktop/Antigravity/test/clientes.http): Gestión de clientes, vehículos y borrado con validación de órdenes abiertas.
- [`test/ordenes.http`](file:///c:/Users/maxim/Desktop/Antigravity/test/ordenes.http): Creación de órdenes con copia de precio, transiciones de estado, rechazo por falta de stock y cancelación por dueño o personal.
- [`test/solo_agregado.sql`](file:///c:/Users/maxim/Desktop/Antigravity/test/solo_agregado.sql): Demostración en SQL de la inmutabilidad de tablas y claves foráneas.
