-- ============================================================
-- ObraCtrl · 0047 · La especialidad: el segundo eje del trabajo
-- Spec §8.3 (frentes) · §7.3 (concepto) · §10.6 (cargadores) · §12.4 (RLS)
--
-- POR QUÉ EL CAMBIO
--
-- Los catálogos reales de la constructora traen **dos** clasificaciones del
-- trabajo, y hasta aquí el esquema solo tenía sitio para una:
--
--   * `CATALOGO_DE_ETAPAS_DE_CONSTRUCCION` clasifica cada etapa en OBRA,
--     INSTALACIONES, SUBCONTRATOS o PINTURA. Son cuatro, y coinciden uno a uno
--     con la columna `TIPO` del catálogo de contratistas. **Ése es el frente**:
--     la clase de fuerza de trabajo que se contrata.
--   * `CATALOGO_DE_CONCEPTOS` clasifica cada concepto en quince valores más
--     finos —ESTRUCTURA, ACABADOS, CARPINTERIA, HERRERIA, CANCELERIA,
--     PERGOLAS…— que coinciden con las columnas `ESPECIALIDAD 1..5` del mismo
--     catálogo de contratistas. **Ésa es la especialidad**: el oficio.
--
-- No son el mismo dato a distinta escala ni uno se deriva del otro. Se
-- comprobó cruzándolos sobre los datos reales: una etapa de frente OBRA
-- contiene conceptos de ACABADOS (74), ESTRUCTURA (32), ALBAÑILERIA (20),
-- BARDA PERIMETRAL (5) y MURO DE CONTENCION (1). Anidan, pero un mismo oficio
-- aparece bajo frentes distintos —ACABADOS sale bajo OBRA y bajo
-- SUBCONTRATOS—, así que no hay jerarquía que colgar de `frente`.
--
-- POR QUÉ UNA TABLA Y NO UNA COLUMNA DE TEXTO EN `concepto`
--
-- Porque la especialidad se cruza con la del contratista para contestar "¿quién
-- de mi lista sabe hacer esto?". Con texto libre, "CARPINTERIA" del concepto y
-- "Carpintería" del contratista no se encontrarían, y ese cruce es la razón de
-- capturarla. Misma forma que `frente` + `contratista_frente` (0005), porque es
-- el mismo problema: un catálogo de clasificación y un puente de capacidad.
--
-- POR QUÉ `especialidad_id` ES NULABLE
--
-- El catálogo real trae especialidad para 461 de los 898 conceptos. Los otros
-- son auxiliares y básicos que no se contratan por oficio. Exigirla obligaría a
-- inventar una para cada uno antes de poder guardar el primero.
--
-- LO QUE ESTA MIGRACIÓN NO HACE
--
-- No toca el catálogo de `frente` ni el mapeo de las etapas. Eso son **datos**
-- del cliente y entran por su cargador (§10.6), no por una migración: sembrar
-- aquí un vocabulario ya salió mal una vez —los seis frentes del §8.3 no eran
-- los que esta constructora usa— y repetirlo con otros cuatro sería el mismo
-- error con distinta lista.
-- ============================================================

create table especialidad (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  clave       text not null,
  nombre      text not null,
  orden       smallint not null default 0,
  estatus     estatus_registro not null default 'activo',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint uq_especialidad_clave unique (org_id, clave)
);
select app.attach_touch('especialidad');

comment on table especialidad is
  'El oficio con el que se ejecuta un concepto (§8.3): ESTRUCTURA, ACABADOS, CARPINTERIA, HERRERIA… Es el segundo eje, más fino que `frente`: el frente dice qué clase de contratista se contrata y la especialidad qué sabe hacer. Un mismo oficio aparece bajo frentes distintos, así que no cuelga de `frente`.';

alter table concepto add column especialidad_id uuid references especialidad(id);
create index ix_concepto_especialidad on concepto (org_id, especialidad_id);

comment on column concepto.especialidad_id is
  'Oficio del concepto, del `CATALOGO_DE_CONCEPTOS` (columna FRENTE). Nulable: el catálogo real la trae para 461 de 898 conceptos; el resto son auxiliares y básicos que no se contratan por oficio.';

create table contratista_especialidad (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizacion(id) on delete cascade,
  contratista_id   uuid not null references contratista(id) on delete cascade,
  especialidad_id  uuid not null references especialidad(id) on delete cascade,
  constraint uq_contratista_especialidad unique (contratista_id, especialidad_id)
);

comment on table contratista_especialidad is
  'Qué oficios sabe hacer un contratista, de las columnas ESPECIALIDAD 1..5 de su catálogo (§10.6). Capacidad de catálogo, no asignación a una obra: para eso está `frente_obra` (0046). Espejo de `contratista_frente` (0005) en el otro eje.';

-- RLS de catálogo: mismo predicado que el loop A) de la 0012 —alcance de
-- organización, escritura solo para quien configura—. Se escribe explícito
-- porque aquel loop ya corrió y no alcanza a las tablas que nacen después.
do $$
declare
  t text;
begin
  foreach t in array array['especialidad', 'contratista_especialidad'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format($p$
      create policy %1$s_select on public.%1$I
        for select using (org_id = app.current_org_id())
    $p$, t);
    perform app.crear_policies_escritura(
      t, 'org_id = app.current_org_id() and app.es_config()');
  end loop;
end;
$$;

grant select, insert, update, delete
  on especialidad, contratista_especialidad to authenticated, obractrl_api;
