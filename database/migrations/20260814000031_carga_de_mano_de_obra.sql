-- ============================================================
-- ObraCtrl · 0031 · Carga de mano de obra / destajos
-- Spec §10.6 ("Mano de obra (Destajos)": clave, clave_usuario, descripción,
-- unidad, cuadrilla, rendimiento_teórico/real, costo_unitario, familia) ·
-- §8.7 (agregar un invariante = migración) · §10.8 (lote reversible).
--
-- `TipoInsumo.MANO_OBRA` ya existe en el dominio (se usa en
-- `explosion.categoria`) pero nadie da de alta un insumo de mano de obra:
-- hasta hoy solo `CargadorMateriales` escribe el catálogo de insumos, y
-- solo para `tipo=material`. Este valor habilita el cargador de
-- `CABECERAS_MANO_DE_OBRA.xlsx` (hoja `DESTAJOS`).
--
-- Dos columnas nuevas en `insumo` porque el archivo real trae dos datos
-- que hoy no tienen dónde vivir:
--   - `cuadrilla_id`: qué cuadrilla ejecuta este destajo (la fila del
--     archivo asigna una clave de cuadrilla, no texto libre).
--   - `rendimiento_teorico`: el rendimiento esperado de esa asignación.
-- `rendimiento_real` del §10.6 NO se agrega aquí a propósito: sale de
-- cruzar contra la duración real de la obra, un cálculo posterior — no es
-- un dato que este archivo cargue.
-- ============================================================

alter type tipo_carga add value if not exists 'mano_de_obra';

alter table insumo
  add column cuadrilla_id        uuid references cuadrilla(id),
  add column rendimiento_teorico numeric(18,6);

comment on column insumo.cuadrilla_id is
  'Cuadrilla asignada a este destajo (§10.6, mano de obra). Solo aplica a tipo=mano_obra.';
comment on column insumo.rendimiento_teorico is
  'Rendimiento esperado de la cuadrilla asignada, del archivo de carga (§10.6). El "real" se deriva después de la duración de obra, en otro cálculo.';
