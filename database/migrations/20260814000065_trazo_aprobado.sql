-- ============================================================
-- ObraCtrl · 0065 · Un trazo puede quedar aprobado por Control de obra
--
-- QUÉ SE AGREGA
--
-- `aprobar_trazo` es una función atómica de Control de obra (cerebro MODELO.md
-- §1b, «Quién puede trazar»; WORKFLOWS.md, «Aprobar el trazo») que el modelo
-- declaraba sin darle dónde vivir. Aquí se le da lo mínimo: quién y cuándo.
--
-- LO QUE ESTO NO HACE (decisión explícita, abierta)
--
-- El cerebro no define si un trazo **sin aprobar** cuenta en la cantidad, y
-- dice solo que «si hace falta aprobación, se define por obra» (C-3). Esta
-- migración toma la lectura que no cambia ninguna cifra: **aprobar es una
-- marca de revisión**, no una compuerta. Un trazo cuenta desde que se guarda,
-- aprobado o no, exactamente como hasta hoy.
--
-- Si el negocio decide que un trazo no cuente hasta ser aprobado, el cambio
-- vive en la lectura de la cantidad vigente (`_MEDIDA_VALOR_SQL` y los
-- recálculos de `cuantificar.py`) y, por obra, en una bandera de gobierno —
-- no en estas columnas, que ya dicen lo necesario para cualquiera de las dos
-- lecturas.
--
-- Sin tabla nueva: quién aprueba y cuándo es un hecho del trazo, igual que
-- `autor_id`. Las dos columnas van juntas (check): o hay aprobación completa
-- o no hay ninguna.
-- ============================================================

alter table trazo
  add column aprobado_por uuid references usuario(id),
  add column aprobado_en  timestamptz,
  add constraint ck_trazo_aprobacion
    check ((aprobado_por is null) = (aprobado_en is null));

comment on column trazo.aprobado_por is
  'Control de obra que lo aprobó (`aprobar_trazo`, MODELO.md §1b). Marca de revisión: no es una compuerta, un trazo sin aprobar cuenta igual en la cantidad (ver el encabezado de la migración 0065).';
comment on column trazo.aprobado_en is
  'Cuándo se aprobó. Va junto con `aprobado_por` (ck_trazo_aprobacion).';
