-- ============================================================
-- ObraCtrl · 0045 · El frente agrupa etapas constructivas
-- Spec §8.3 (frentes) · §10.1 (etapas) · §7.6 (Actividad) · §11.3
--
-- POR QUÉ EL CAMBIO
--
-- El jefe de obra lo describe así: *"nuestro frente es una mezcla, es por
-- etapa de construcción. En mi nivel CIMENTACIÓN puedo tener 2 frentes,
-- ESTRUCTURA e INSTALACIONES, aunque INSTALACIONES tiene varias etapas de
-- construcción"*.
--
-- Y el catálogo real lo confirma. Las 52 etapas se llaman así:
--
--   ECO-00001  ESTRUCTURA CIM
--   ECO-00002  INSTALACIONES SANITARIAS CIM
--   ECO-00003  INSTALACIONES HIDRAULICAS CIM
--   ECO-00004  INSTALACIONES ELECTRICAS CIM
--   ECO-00005  INSTALACIONES GAS CIM
--
-- Cuatro etapas que son UN frente. La relación es de muchos a uno —una etapa
-- pertenece a un frente, un frente agrupa varias— y no existía en ningún
-- lado: `actividad.frente_id` estaba ahí desde la 0007 pero nadie sabía de
-- dónde sacarlo, así que ninguna actividad generada tenía frente.
--
-- POR QUÉ UNA COLUMNA Y NO UNA TABLA PUENTE
--
-- Porque una etapa pertenece a **un** frente y no a varios: si `INSTALACIONES
-- HIDRAULICAS CIM` estuviera en dos, el residente vería su trabajo contado
-- dos veces al planear cuántas cuadrillas necesita, que es justo la cifra que
-- este modelo existe para producir. La unicidad la da la columna sola; una
-- tabla puente tendría que defenderla con un índice y un `check` que dijeran
-- lo mismo.
--
-- Nulable a propósito: una etapa sin frente todavía es el estado normal
-- mientras se captura, y exigirlo obligaría a llenar las 52 antes de poder
-- guardar la primera. Lo que cuelgue de una etapa sin frente sale reportado
-- aparte en la planeación, no se pierde.
--
-- LOS FRENTES YA TIENEN SEMILLA
--
-- `database/seeds/01_semilla_canonica.sql` da los ocho del §8.3 (PRE, CIM,
-- EST, ALB, HID, ELE, ACA, HER). No se repiten aquí: son semilla editable
-- (§8.7) y la pantalla de Frentes deja crear los que cada constructora use de
-- verdad —`INSTALACIONES` agrupando hidráulica, sanitaria, eléctrica y gas es
-- exactamente ese caso—. Una migración que los volviera a insertar tendría
-- dos definiciones de la misma lista.
-- ============================================================

alter table etapa_constructiva
  add column frente_id uuid references frente(id);

create index ix_etapa_frente on etapa_constructiva (org_id, frente_id);

comment on column etapa_constructiva.frente_id is
  'Frente al que pertenece la etapa (§8.3). Un frente agrupa varias etapas —INSTALACIONES cubre hidráulica, sanitaria, eléctrica y gas— y una etapa pertenece a uno solo: contarla dos veces inflaría las cuadrillas que la planeación pide. `null` = sin asignar todavía.';
