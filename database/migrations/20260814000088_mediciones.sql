-- ============================================================
-- ObraCtrl · 0088 · Cuantificador: mediciones (la capa sombra)
--
-- QUÉ ES Y PARA QUÉ
--
-- Hasta aquí un trazo nacía ligado a un concepto: se dibujaba para un enlace. Una MEDICIÓN es otra
-- cosa: un grupo con nombre —«Losa de cimentación», «Recámara 1», «Muros eje A», «Castillos K1»—
-- de trazos que viven sobre el plano sin depender de ningún concepto. Se dibuja una vez y después
-- se ASIGNA a uno o varios conceptos (la recámara 1 alimenta losa, firme, piso y pintura).
--
-- · `medicion` tiene tipo (área, lineal o conteo) y puede anidar otras del mismo tipo: la losa se
--   mide por espacios y su total es la suma de ellos.
-- · `trazo.medicion_id` dice a qué medición pertenece un trazo (nulo = suelto, como siempre).
-- · `medicion_asignacion` dice a qué concepto alimenta una medición (y con qué medida y factor).
--   Asignar crea los enlaces de sus trazos —y de los de sus submediciones— y un trazo nuevo que
--   entra a la medición hereda los de su medición y los de las que la contienen. El motor de
--   cantidades no cambia: sigue siendo `medida × factor` por enlace vigente.
-- · `enlace_cuantificacion.asignacion_id` recuerda de qué asignación vino un enlace, para quitarlo
--   (queda como evidencia, no vigente) cuando se quita la asignación o el trazo sale de la medición.
-- ============================================================

create table medicion (
  id         uuid primary key default gen_random_uuid(),
  org_id     uuid not null references organizacion(id) on delete cascade,
  plano_id   uuid not null references plano(id) on delete cascade,
  parent_id  uuid references medicion(id),
  nombre     text not null,
  tipo       text not null,
  orden      integer not null default 0,
  autor_id   uuid references usuario(id),
  created_at timestamptz not null default now(),
  constraint ck_medicion_tipo check (tipo in ('area', 'lineal', 'conteo')),
  constraint ck_medicion_nombre check (length(btrim(nombre)) between 1 and 120),
  constraint ck_medicion_no_es_su_padre check (parent_id is null or parent_id <> id)
);
create index ix_medicion_plano on medicion (org_id, plano_id);
create index ix_medicion_parent on medicion (org_id, parent_id) where parent_id is not null;
-- El mismo nombre no se repite entre hermanas (la «Recámara 1» de dos losas distintas sí puede).
create unique index ux_medicion_nombre_hermanas
  on medicion (plano_id, coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(btrim(nombre)));

comment on table medicion is
  'La capa sombra del cuantificador (0088): un grupo con nombre de trazos de un tipo (área, lineal o conteo), independiente de cualquier concepto, que después se asigna a conceptos. Puede anidar otras del mismo tipo (espacios dentro de una losa).';

alter table trazo
  add column medicion_id uuid references medicion(id) on delete set null;
create index ix_trazo_medicion on trazo (org_id, medicion_id) where medicion_id is not null;
comment on column trazo.medicion_id is
  'La medición a la que pertenece el trazo (0088); nulo = suelto. Si la medición se borra, sus trazos quedan sueltos.';

create table medicion_asignacion (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references organizacion(id) on delete cascade,
  medicion_id       uuid not null references medicion(id) on delete cascade,
  actividad_id      uuid not null references actividad(id) on delete cascade,
  matriz_concepto_id uuid references concepto(id),
  medida            medida_cuantificacion not null,
  factor            numeric(18,6) not null check (factor > 0),
  autor_id          uuid references usuario(id),
  created_at        timestamptz not null default now()
);
create unique index ux_medicion_asignacion
  on medicion_asignacion (medicion_id, actividad_id,
                          coalesce(matriz_concepto_id, '00000000-0000-0000-0000-000000000000'::uuid), medida);
create index ix_medicion_asignacion_actividad on medicion_asignacion (org_id, actividad_id);

comment on table medicion_asignacion is
  'A qué concepto de la obra alimenta una medición, con qué medida y factor (0088). Crea un enlace por cada trazo de la medición y de sus submediciones.';

alter table enlace_cuantificacion
  add column asignacion_id uuid references medicion_asignacion(id) on delete set null;
create index ix_enlace_cuantificacion_asignacion on enlace_cuantificacion (org_id, asignacion_id)
  where asignacion_id is not null;
comment on column enlace_cuantificacion.asignacion_id is
  'La asignación de medición de la que vino este enlace (0088); nulo = se enlazó a mano.';

-- --- RLS: se llega a la obra por el plano, igual que trazo ------------------

alter table medicion enable row level security;
create policy medicion_scope on medicion
  for all
  using (
    org_id = app.current_org_id()
    and exists (select 1 from plano p where p.id = plano_id and app.obra_visible(p.obra_id))
  )
  with check (
    org_id = app.current_org_id()
    and exists (select 1 from plano p where p.id = plano_id and app.obra_visible(p.obra_id))
  );

alter table medicion_asignacion enable row level security;
create policy medicion_asignacion_scope on medicion_asignacion
  for all
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from medicion m join plano p on p.id = m.plano_id
       where m.id = medicion_id and app.obra_visible(p.obra_id)
    )
  )
  with check (
    org_id = app.current_org_id()
    and exists (
      select 1 from medicion m join plano p on p.id = m.plano_id
       where m.id = medicion_id and app.obra_visible(p.obra_id)
    )
  );

grant select, insert, update, delete on medicion, medicion_asignacion
  to authenticated, obractrl_api;
