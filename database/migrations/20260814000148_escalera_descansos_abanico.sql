-- ============================================================
-- ObraCtrl · 0148 · Escalera: descansos propios y escalones de abanico (Fase 4d)
--
-- La escalera de 0145 (`escalera_zona`) tenía un descanso implícito entre rampas (ancho × `largo_descanso_m`). Esta migración agrega, sin tocarla:
--
--   · `escalera_descanso`: un DESCANSO PROPIO entre la rampa `posicion` y la siguiente (1 = entre la 1.ª y la 2.ª), con sus dimensiones (`largo_m` en el sentido de
--     la marcha × `ancho_m` transversal), su `espesor_m`, el `giro_grados` del recorrido ahí (0, 90 o 180) y, si se quiere, un POLÍGONO del plano (`trazo_id`) cuya
--     área —con la escala, al calcular, sin guardarla— manda sobre largo × ancho. Lo que va nulo toma la omisión de la escalera. Una posición sin fila conserva el
--     descanso implícito de 0145: una escalera sin descansos propios calcula igual que antes. Se paga con el concepto propuesto EJ-820 por m² (suma de las áreas).
--   · `escalera_abanico`: un grupo de ESCALONES DE ABANICO en la `posicion` (0 = antes de la 1.ª rampa, k = tras la rampa k): `escalones`, el fondo del peldaño en
--     el borde interior y en el exterior (`ancho_interior_m`, `ancho_exterior_m`; el largo del peldaño es el ancho de la escalera) y el radio de la línea de huella
--     medido desde el borde interior (`radio_huella_m`, supuesto editable: 0.35 m). Los escalones de abanico forman parte de los peldaños del desnivel (no se suman).
--
-- RLS igual que `escalera_zona`: leen quienes ven la obra del plano; escribe solo Control de obra. Aditiva y reversible: sin filas nuevas todo se comporta como hasta hoy.
-- ============================================================

create table if not exists escalera_descanso (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  escalera_id uuid not null references escalera_zona(id) on delete cascade,
  posicion    smallint not null,
  giro_grados smallint not null default 90,
  largo_m     numeric(5,3),
  ancho_m     numeric(5,3),
  espesor_m   numeric(5,3),
  trazo_id    uuid references trazo(id) on delete set null,
  autor_id    uuid references usuario(id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint ck_escalera_descanso_posicion check (posicion between 1 and 3),
  constraint ck_escalera_descanso_giro check (giro_grados in (0, 90, 180)),
  constraint ck_escalera_descanso_largo check (largo_m is null or largo_m between 0.40 and 6.00),
  constraint ck_escalera_descanso_ancho check (ancho_m is null or ancho_m between 0.40 and 6.00),
  constraint ck_escalera_descanso_espesor check (espesor_m is null or espesor_m between 0.05 and 0.50),
  constraint ux_escalera_descanso_posicion unique (escalera_id, posicion)
);
-- Un polígono del plano da el área de UN descanso: dos descansos sobre el mismo polígono contarían lo mismo dos veces.
create unique index if not exists ux_escalera_descanso_trazo on escalera_descanso (trazo_id) where trazo_id is not null;
create index if not exists ix_escalera_descanso_org on escalera_descanso (org_id, escalera_id);
select app.attach_touch('escalera_descanso');

create table if not exists escalera_abanico (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizacion(id) on delete cascade,
  escalera_id      uuid not null references escalera_zona(id) on delete cascade,
  posicion         smallint not null,
  escalones        smallint not null,
  ancho_interior_m numeric(5,3) not null,
  ancho_exterior_m numeric(5,3) not null,
  radio_huella_m   numeric(5,3) not null default 0.35,
  autor_id         uuid references usuario(id) on delete set null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint ck_escalera_abanico_posicion check (posicion between 0 and 4),
  constraint ck_escalera_abanico_escalones check (escalones between 1 and 12),
  constraint ck_escalera_abanico_interior check (ancho_interior_m between 0.02 and 0.60),
  constraint ck_escalera_abanico_exterior check (ancho_exterior_m between 0.10 and 0.80),
  constraint ck_escalera_abanico_orden check (ancho_exterior_m >= ancho_interior_m),
  constraint ck_escalera_abanico_radio check (radio_huella_m between 0.10 and 5.00),
  constraint ux_escalera_abanico_posicion unique (escalera_id, posicion)
);
create index if not exists ix_escalera_abanico_org on escalera_abanico (org_id, escalera_id);
select app.attach_touch('escalera_abanico');

comment on table escalera_descanso is
  'Un descanso propio de una escalera, entre la rampa `posicion` y la siguiente: largo × ancho, espesor, giro y, si se quiere, el área de un polígono del plano; lo nulo toma la omisión (0148).';
comment on column escalera_descanso.giro_grados is 'El giro del recorrido en el descanso: 0 recto, 90 cambio de dirección o 180 vuelta (0148).';
comment on column escalera_descanso.trazo_id is 'Medición derivada: polígono del plano cuya área (con la escala) manda sobre largo × ancho; se calcula, no se guarda (0148).';
comment on table escalera_abanico is
  'Un grupo de escalones de abanico de una escalera: escalones con el fondo del peldaño en el borde interior y exterior y el radio de la línea de huella; forman parte de los peldaños del desnivel (0148).';
comment on column escalera_abanico.radio_huella_m is 'Distancia del borde interior a la línea de huella; supuesto editable de 0.35 m (0148).';

do $$
declare
  t text;
begin
  foreach t in array array['escalera_descanso', 'escalera_abanico'] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists %I on %I', t || '_lectura', t);
    execute format(
      'create policy %I on %I for select using (
         org_id = app.current_org_id()
         and exists (
           select 1 from escalera_zona e join losa_zona z on z.id = e.zona_id join plano p on p.id = z.plano_id
            where e.id = escalera_id and app.obra_visible(p.obra_id)
         )
       )', t || '_lectura', t);
    execute format('drop policy if exists %I on %I', t || '_alta', t);
    execute format(
      'create policy %I on %I for insert with check (
         org_id = app.current_org_id() and app.current_rol() = ''control_obra''
         and exists (
           select 1 from escalera_zona e join losa_zona z on z.id = e.zona_id join plano p on p.id = z.plano_id
            where e.id = escalera_id and app.obra_visible(p.obra_id)
         )
       )', t || '_alta', t);
    execute format('drop policy if exists %I on %I', t || '_cambio', t);
    execute format(
      'create policy %I on %I for update
         using (
           org_id = app.current_org_id() and app.current_rol() = ''control_obra''
           and exists (
             select 1 from escalera_zona e join losa_zona z on z.id = e.zona_id join plano p on p.id = z.plano_id
              where e.id = escalera_id and app.obra_visible(p.obra_id)
           )
         )
         with check (org_id = app.current_org_id() and app.current_rol() = ''control_obra'')', t || '_cambio', t);
    execute format('drop policy if exists %I on %I', t || '_baja', t);
    execute format(
      'create policy %I on %I for delete using (
         org_id = app.current_org_id() and app.current_rol() = ''control_obra''
         and exists (
           select 1 from escalera_zona e join losa_zona z on z.id = e.zona_id join plano p on p.id = z.plano_id
            where e.id = escalera_id and app.obra_visible(p.obra_id)
         )
       )', t || '_baja', t);
    execute format('grant select, insert, update, delete on %I to authenticated, obractrl_api', t);
  end loop;
end $$;
