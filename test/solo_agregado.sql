-- ============================================================================
-- Caso C-14: Verificación del disparador de sólo agregado y clave foránea (RN-15 / RN-19)
-- ============================================================================
-- Se esperan 6 rechazos por el disparador (UPDATE y DELETE en las 3 tablas inmutables)
-- y 1 rechazo por clave foránea al intentar insertar una orden con estado inválido.
-- Ejecutar en psql: \i test/solo_agregado.sql

-- 1. Intentos sobre historial_estado_orden (deben fallar ambos)
UPDATE historial_estado_orden SET hasta_estado = 'TERMINADA' WHERE id = 1;
DELETE FROM historial_estado_orden WHERE id = 1;

-- 2. Intentos sobre movimiento_stock (deben fallar ambos)
UPDATE movimiento_stock SET cantidad = 999 WHERE id = 1;
DELETE FROM movimiento_stock WHERE id = 1;

-- 3. Intentos sobre historial_precio_repuesto (deben fallar ambos)
UPDATE historial_precio_repuesto SET precio_nuevo = 5000 WHERE id = 1;
DELETE FROM historial_precio_repuesto WHERE id = 1;

-- 4. Intento de orden con un estado inexistente en el catálogo (debe fallar por FK)
INSERT INTO orden_trabajo (vehiculo_id, mecanico_id, estado, falla, creada_en, total)
VALUES (1, NULL, 'ESTADO_INVENTADO', 'Prueba de falla por clave foránea', NOW(), 0.00);
