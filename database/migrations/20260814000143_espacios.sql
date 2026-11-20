-- ============================================================
-- ObraCtrl · 0143 · Capa «ESPACIO»: el cuarto o área como unidad donde se asignan zonas de losa, muros y elementos (D-565, D-566, D-640)
--
-- Un ESPACIO (recámara 1, baño, cocina, cochera…) es el nivel de agrupación entre el nivel/etapa y la partida del árbol del presupuesto. Sirve
-- para que cada zona de losa, cada muro y cada elemento sepa EN QUÉ PARTIDA se mide, sin contar nada dos veces:
--
--   · `espacio`        : el espacio de UNA obra (nombre, tipo, nivel opcional, m² opcionales). Es lo único «capturado»; no es una zona de losa
--                        (una zona puede cubrir varios cuartos) ni una medición (la capa sombra de 0088 no depende del árbol).
--   · `espacio_nodo`   : la rama del árbol del presupuesto (un `prototipo_nodo`) que pertenece a un espacio. Las partidas debajo de esa rama
--                        heredan el espacio, igual que heredan el nivel y la etapa. Es una tabla de la OBRA (no del prototipo): el árbol del
--                        prototipo base es compartido y no se toca. Un nodo sin espacio (ni él ni un ancestro) es una partida «general».
--   · `trazo.espacio_id`          : el espacio donde cae un muro, un polígono de losa o un elemento colocado.
--   · `trazo.espacio_comparte_id` + `trazo.espacio_reparto_pct`: MURO COMPARTIDO entre dos espacios. El muro se traza UNA vez y su cantidad
--                        se reparte (por omisión mitad y mitad): el reparto SIEMPRE suma 100 %, así que nunca cuenta dos veces.
--   · `losa_elemento.espacio_id`  : el espacio de una trabe, contratrabe o nervadura de la zona (lo que anunciaba la nota de `matriz_de_losa`).
--   · `enlace_ranura.espacio_id`  : la capa «espacio» de los enlaces de ranura (pedido del 2026-11-16): el mismo muro se enlaza a conceptos
--                        distintos según el cuarto. Pesa entre la ubicación y la etapa.
--
-- Solo Control de obra edita la estructura de los espacios (igual que las zonas de losa); los demás roles que ven la obra leen. Aditiva y
-- reversible: nada de lo ya guardado cambia; un muro, una zona o un elemento SIN espacio se comportan exactamente como hasta hoy.
-- ============================================================

create table if not exists espacio (
  id         uuid primary key default gen_random_uuid(),
  org_id     uuid not null references organizacion(id) on delete cascade,
  obra_id    uuid not null references obra(id) on delete cascade,
  nombre     text not null,
  tipo       text not null default 'otro',
  nivel_id   uuid references nivel(id) on delete set null,
  area_m2    numeric(10,2),
  orden      integer not null default 0,
  autor_id   uuid references usuario(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_espacio_nombre check (length(btrim(nombre)) between 1 and 60),
  constraint ck_espacio_tipo check (
    tipo in ('recamara', 'bano', 'cocina', 'sala', 'comedor', 'estancia', 'cochera', 'pasillo', 'escalera', 'patio', 'azotea', 'bodega', 'otro')
  ),
  constraint ck_espacio_area check (area_m2 is null or (area_m2 > 0 and area_m2 <= 100000))
);
create unique index if not exists ux_espacio_nombre on espacio (obra_id, lower(btrim(nombre)));
create index if not exists ix_espacio_obra on espacio (org_id, obra_id, orden);
select app.attach_touch('espacio');

comment on table espacio is
  'Un espacio (recámara, baño, cochera…) de una obra: el nivel de agrupación entre el nivel/etapa y la partida del árbol. Donde se asignan zonas de losa, muros y elementos (0143).';
comment on column espacio.nivel_id is 'El nivel donde está el espacio (informativo; no es una capa de enlace) (0143).';
comment on column espacio.area_m2 is 'm² del espacio, si se conocen: es el único dato que se captura del espacio (0143).';

create table if not exists espacio_nodo (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references organizacion(id) on delete cascade,
  obra_id           uuid not null references obra(id) on delete cascade,
  espacio_id        uuid not null references espacio(id) on delete cascade,
  prototipo_nodo_id uuid not null references prototipo_nodo(id) on delete cascade,
  created_at        timestamptz not null default now()
);
-- Un nodo pertenece a lo más a un espacio por obra.
create unique index if not exists ux_espacio_nodo_nodo on espacio_nodo (obra_id, prototipo_nodo_id);
create index if not exists ix_espacio_nodo_espacio on espacio_nodo (espacio_id);

comment on table espacio_nodo is
  'La rama del árbol del presupuesto (prototipo_nodo) que pertenece a un espacio de la obra: sus partidas heredan el espacio como heredan el nivel y la etapa. De la obra, no del prototipo compartido (0143).';

alter table trazo
  add column if not exists espacio_id           uuid,
  add column if not exists espacio_comparte_id  uuid,
  add column if not exists espacio_reparto_pct  numeric(5,2);

alter table trazo drop constraint if exists trazo_espacio_id_fkey;
alter table trazo drop constraint if exists trazo_espacio_comparte_id_fkey;
alter table trazo
  add constraint trazo_espacio_id_fkey foreign key (espacio_id) references espacio(id) on delete set null,
  add constraint trazo_espacio_comparte_id_fkey foreign key (espacio_comparte_id) references espacio(id) on delete set null;

alter table trazo drop constraint if exists ck_trazo_espacio_reparto;
alter table trazo drop constraint if exists ck_trazo_espacio_distintos;
alter table trazo
  -- El reparto es la parte del espacio principal (1 a 99 %); el resto es del otro. Sin reparto vale mitad y mitad.
  add constraint ck_trazo_espacio_reparto check (espacio_reparto_pct is null or (espacio_reparto_pct > 0 and espacio_reparto_pct < 100)),
  add constraint ck_trazo_espacio_distintos check (espacio_comparte_id is null or espacio_id is null or espacio_comparte_id <> espacio_id);

create index if not exists ix_trazo_espacio on trazo (espacio_id) where espacio_id is not null;
create index if not exists ix_trazo_espacio_comparte on trazo (espacio_comparte_id) where espacio_comparte_id is not null;

comment on column trazo.espacio_id is 'El espacio donde cae el muro, el polígono de losa o el elemento; null = sin espacio, como siempre (0143).';
comment on column trazo.espacio_comparte_id is 'Muro compartido: el otro espacio. El muro se traza una vez y su cantidad se reparte entre los dos sin contarse dos veces (0143).';
comment on column trazo.espacio_reparto_pct is 'Muro compartido: el % que toca al espacio principal (1 a 99); el resto es del otro. null = mitad y mitad (0143).';

alter table losa_elemento add column if not exists espacio_id uuid;
alter table losa_elemento drop constraint if exists losa_elemento_espacio_id_fkey;
alter table losa_elemento
  add constraint losa_elemento_espacio_id_fkey foreign key (espacio_id) references espacio(id) on delete set null;
create index if not exists ix_losa_elemento_espacio on losa_elemento (espacio_id) where espacio_id is not null;
comment on column losa_elemento.espacio_id is 'El espacio donde está la trabe, contratrabe o nervadura de la zona; null = sin espacio (0143).';

alter table enlace_ranura add column if not exists espacio_id uuid;
alter table enlace_ranura drop constraint if exists enlace_ranura_espacio_id_fkey;
alter table enlace_ranura
  add constraint enlace_ranura_espacio_id_fkey foreign key (espacio_id) references espacio(id) on delete cascade;
-- La capa pasa a incluir el espacio (las capas vacías cuentan como una: «cualquiera»).
drop index if exists ux_enlace_ranura_capa;
create unique index if not exists ux_enlace_ranura_capa on enlace_ranura (
  org_id, obra_id, ranura,
  coalesce(nivel_id, '00000000-0000-0000-0000-000000000000'::uuid),
  coalesce(etapa_id, '00000000-0000-0000-0000-000000000000'::uuid),
  coalesce(ubicacion, ''),
  coalesce(espacio_id, '00000000-0000-0000-0000-000000000000'::uuid)
);
comment on column enlace_ranura.espacio_id is 'Capa «espacio» del enlace: solo aplica a lo que se mide en ese espacio; null = cualquiera (0143).';

-- RLS: se lee dentro de la organización y de las obras que el rol ve; solo Control de obra escribe la estructura de los espacios.
alter table espacio enable row level security;
drop policy if exists espacio_lectura on espacio;
create policy espacio_lectura on espacio
  for select using (org_id = app.current_org_id() and app.obra_visible(obra_id));
drop policy if exists espacio_alta on espacio;
create policy espacio_alta on espacio
  for insert with check (org_id = app.current_org_id() and app.current_rol() = 'control_obra' and app.obra_visible(obra_id));
drop policy if exists espacio_cambio on espacio;
create policy espacio_cambio on espacio
  for update
  using (org_id = app.current_org_id() and app.current_rol() = 'control_obra' and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.current_rol() = 'control_obra' and app.obra_visible(obra_id));
drop policy if exists espacio_baja on espacio;
create policy espacio_baja on espacio
  for delete using (org_id = app.current_org_id() and app.current_rol() = 'control_obra' and app.obra_visible(obra_id));
grant select, insert, update, delete on espacio to authenticated, obractrl_api;

alter table espacio_nodo enable row level security;
drop policy if exists espacio_nodo_lectura on espacio_nodo;
create policy espacio_nodo_lectura on espacio_nodo
  for select using (org_id = app.current_org_id() and app.obra_visible(obra_id));
drop policy if exists espacio_nodo_alta on espacio_nodo;
create policy espacio_nodo_alta on espacio_nodo
  for insert
  with check (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra' and app.obra_visible(obra_id)
    -- El espacio y el nodo deben ser de ESTA obra: el nodo, del árbol de su prototipo.
    and exists (select 1 from espacio e where e.id = espacio_nodo.espacio_id and e.obra_id = espacio_nodo.obra_id)
    and exists (
      select 1 from prototipo_nodo n join obra o on o.prototipo_id = n.prototipo_id
       where n.id = espacio_nodo.prototipo_nodo_id and o.id = espacio_nodo.obra_id
    )
  );
drop policy if exists espacio_nodo_baja on espacio_nodo;
create policy espacio_nodo_baja on espacio_nodo
  for delete using (org_id = app.current_org_id() and app.current_rol() = 'control_obra' and app.obra_visible(obra_id));
grant select, insert, delete on espacio_nodo to authenticated, obractrl_api;

-- Al crear el árbol propio de una obra (Control de obra o Costos), sus nodos se copian con otros ids y las ramas asignadas a un espacio deben seguir a
-- su copia. Es un cambio de puntero, no una edición de la estructura de los espacios (que es solo de Control de obra): lo hace esta función, que
-- corre como dueña pero solo toca filas de la organización y de la obra que el rol ve.
create or replace function app.espacio_nodo_seguir_a_la_copia(p_obra uuid, p_viejo uuid, p_nuevo uuid)
returns integer
language sql
security definer
set search_path = public, app, pg_temp
as $$
  with movidas as (
    update espacio_nodo
       set prototipo_nodo_id = p_nuevo
     where obra_id = p_obra and prototipo_nodo_id = p_viejo
       and org_id = app.current_org_id() and app.obra_visible(p_obra)
    returning 1
  )
  select count(*)::int from movidas
$$;
revoke all on function app.espacio_nodo_seguir_a_la_copia(uuid, uuid, uuid) from public;
grant execute on function app.espacio_nodo_seguir_a_la_copia(uuid, uuid, uuid) to authenticated, obractrl_api;
comment on function app.espacio_nodo_seguir_a_la_copia(uuid, uuid, uuid) is
  'La rama de un espacio sigue a su nodo copiado al crear el árbol propio de la obra; solo toca la organización y la obra visibles (0143).';
