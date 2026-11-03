-- ============================================================
-- ObraCtrl · 0102 · Catálogo de mano de obra (puestos y cuadrillas) y semilla
-- de cuadrillas-rendimiento
-- Decisión del usuario (D-616): las 39 cuadrillas se guardan en la tabla de
-- cuadrillas, y para fletes y cuadrillas no se ignora ninguna columna de
-- sus archivos.
--
-- `CATALOGO_DE_MANO_DE_OBRA` (97 filas, 36 columnas): 58 puestos (insumos de
-- mano de obra, MOCA-xxx) y 39 cuadrillas (C = «+», MOCU-xxx y CUAD-xxx).
-- C, Clave, Descripción, Unidad, Familia, Subfamilia y Tipo viven en el
-- insumo o en la cuadrilla; las 28 columnas del cálculo del salario real
-- (salario tabulado, FSR, cuotas IMSS, INFONAVIT...) viven en
-- `mano_de_obra_opus`, una fila por clave.
--
-- `SEMILLA-cuadrilla-rendimiento` (265 filas): destajo → cuadrilla y
-- rendimiento teórico (`insumo.cuadrilla_id` / `rendimiento_teorico`, 0031),
-- más su Origen y sus tres columnas de referencia.
-- ============================================================

alter type tipo_carga add value if not exists 'catalogo_mano_de_obra';
alter type tipo_carga add value if not exists 'semilla_cuadrilla_rendimiento';

-- La cuadrilla guarda también lo que el archivo trae de ella.
alter table cuadrilla add column familia_id    uuid references familia(id);
alter table cuadrilla add column desglosable   boolean not null default false;
alter table cuadrilla add column fecha_costo   date;
alter table cuadrilla add column tipo_opus     text;
comment on column cuadrilla.desglosable is 'Columna C del catálogo de mano de obra: «+» = cuadrilla (se abre en sus puestos).';

-- Semilla: lo que el archivo trae además de la liga y el rendimiento.
alter table insumo add column origen_rendimiento  text;
alter table insumo add column ref_descripcion     text;
alter table insumo add column ref_unidad          text;
alter table insumo add column ref_costo_unitario  numeric(18,4);
comment on column insumo.origen_rendimiento is 'Columna Origen de la semilla (migrado, completado · factor 1.085...).';

create table mano_de_obra_opus (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  clave         text not null,
  insumo_id     uuid references insumo(id) on delete cascade,
  cuadrilla_id  uuid references cuadrilla(id) on delete cascade,
  utilizar_hoja_fsr boolean not null default false,
  categoria_fsr text,
  fecha         date,
  costo_unitario                 numeric(18,6),
  salario_tabulado               numeric(18,6),
  salario_nominal_mn             numeric(18,6),
  fsr                            numeric(18,6),
  salario_nominal_me             numeric(18,6),
  salario_real                   numeric(18,6),
  factor_salario_base            numeric(18,6),
  sbc                            numeric(18,6),
  excedente_tres_salarios        numeric(18,6),
  aplicacion_imss                numeric(18,6),
  cuota_fija                     numeric(18,6),
  prestaciones_en_especie        numeric(18,6),
  prestaciones_en_dinero         numeric(18,6),
  invalidez_y_vida               numeric(18,6),
  cesantia_en_edad_avanzada      numeric(18,6),
  riesgos_de_trabajo             numeric(18,6),
  guarderias                     numeric(18,6),
  sar                            numeric(18,6),
  suma_prestaciones_imss         numeric(18,6),
  factor_cuota_patronal_imss     numeric(18,6),
  infonavit                      numeric(18,6),
  impuesto_sobre_nomina          numeric(18,6),
  suma_prestaciones              numeric(18,6),
  obligacion_obrero_patronal     numeric(18,6),
  factor_de_salario_gravable     numeric(18,6),
  salario_gravable               numeric(18,6),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint uq_mano_de_obra_opus_clave unique (org_id, clave),
  constraint ck_mano_de_obra_opus_dueno check (num_nonnulls(insumo_id, cuadrilla_id) = 1)
);
select app.attach_touch('mano_de_obra_opus');
create index ix_mano_de_obra_opus_insumo on mano_de_obra_opus (insumo_id);
create index ix_mano_de_obra_opus_cuadrilla on mano_de_obra_opus (cuadrilla_id);

comment on table mano_de_obra_opus is
  'Columnas del cálculo del salario real de CATALOGO_DE_MANO_DE_OBRA, tal cual vienen: una fila por puesto o cuadrilla (D-616).';

alter table mano_de_obra_opus enable row level security;

create policy mano_de_obra_opus_select on mano_de_obra_opus
  for select using (org_id = app.current_org_id());

select app.crear_policies_escritura(
  'mano_de_obra_opus', 'org_id = app.current_org_id() and app.es_config()');
