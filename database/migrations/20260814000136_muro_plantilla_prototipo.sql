-- ============================================================
-- ObraCtrl · 0136 · Plantillas de muro por prototipo (plan de elementos de muro, Ola 4, «plantillas por prototipo»; M-4)
--
-- La plantilla de «muro confinado de tabique» se usa cuando NO hay plano estructural: PROPONE (estima) los castillos. Lleva VARIOS
-- castillos y hay una variante por PROTOTIPO (Zafiro, Oro, Diamante…) y por planta (PB o PA), más una plantilla GLOBAL (el promedio de
-- los prototipos más parecidos) separada en 1 planta y 2 plantas.
--
-- · `prototipo`: la clave del prototipo (oro_401, zafiro_1, …) o `global_1` / `global_2`; `null` = una plantilla de muro cualquiera.
--   Las claves válidas viven en el dominio (`prototipos_de_muro`): un prototipo nuevo no pide migración.
-- · `planta`: PB o PA. El número de plantas de cada prototipo se INFIERE del subcapítulo «PLANTA ALTA» del Excel (a confirmar).
-- · `notas`: de dónde salen los datos (fila y celda del Excel del cerebro) y lo que quedó pendiente.
-- · `por_confirmar`: los datos son de ejemplo o sin confirmar por el usuario (no es la validación de Control de obra).
-- · Las reglas de cada castillo (por ml, separación, extremos, total) viven DENTRO de `elementos` (jsonb): no piden columna.
--
-- Solo etiqueta y receta: no cambia ninguna cantidad ya medida. Aditiva: se puede volver a correr.
-- ============================================================

alter table muro_plantilla
  add column if not exists prototipo     text,
  add column if not exists planta        text,
  add column if not exists notas         text,
  add column if not exists por_confirmar boolean not null default false;

alter table muro_plantilla drop constraint if exists ck_muro_plantilla_prototipo;
alter table muro_plantilla
  add constraint ck_muro_plantilla_prototipo check (prototipo is null or length(btrim(prototipo)) between 1 and 40);
alter table muro_plantilla drop constraint if exists ck_muro_plantilla_planta;
alter table muro_plantilla
  add constraint ck_muro_plantilla_planta check (planta is null or planta in ('PB', 'PA'));
-- La planta solo tiene sentido dentro de un prototipo.
alter table muro_plantilla drop constraint if exists ck_muro_plantilla_planta_de_prototipo;
alter table muro_plantilla
  add constraint ck_muro_plantilla_planta_de_prototipo check (planta is null or prototipo is not null);
alter table muro_plantilla drop constraint if exists ck_muro_plantilla_notas;
alter table muro_plantilla
  add constraint ck_muro_plantilla_notas check (notas is null or length(notas) <= 6000);

create index if not exists ix_muro_plantilla_prototipo on muro_plantilla (org_id, prototipo, planta) where vigente and prototipo is not null;

comment on column muro_plantilla.prototipo is
  'Prototipo de la plantilla: oro_401, zafiro_1, rubi, jade, zafiro_plus, diamante_menos, diamante_mas, global_1 o global_2; null = sin prototipo (0136).';
comment on column muro_plantilla.planta is 'Planta del prototipo: PB o PA (0136). El número de plantas de cada prototipo se infiere del subcapítulo PLANTA ALTA.';
comment on column muro_plantilla.notas is 'De dónde salen los datos (fila y celda del Excel) y lo pendiente; texto libre, 6000 caracteres como máximo (0136).';
comment on column muro_plantilla.por_confirmar is
  'Los datos de la plantilla son de ejemplo o aún no los confirma el usuario; es aparte de la validación de Control de obra (0136).';
