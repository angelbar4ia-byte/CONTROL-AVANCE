-- ============================================================
-- ObraCtrl · 0029 · Carga masiva de prototipos
-- Spec §8.7 (agregar un invariante = migración) · §10.8 (lote reversible)
--
-- Prototipos hoy solo se da de alta uno a uno (`POST /prototipos`, §7.2).
-- Este valor habilita un cargador de Excel para varios a la vez, con el
-- mismo pipeline de vista previa / aplicar / reversar que ya tienen
-- materiales y almacén — no es un cargador que el §10.6 original ya
-- describiera y le faltara wiring (como sí era el caso de `almacen`,
-- migración 0019): es una extensión nueva del catálogo de cargadores.
-- El espejo en código es `domain/shared/diccionario.py::TipoCarga.PROTOTIPOS`.
-- ============================================================

alter type tipo_carga add value if not exists 'prototipos';
