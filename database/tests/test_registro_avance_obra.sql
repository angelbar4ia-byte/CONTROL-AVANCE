-- ============================================================
-- ObraCtrl · `registro_avance.obra_id` derivado (migración 0021)
-- Spec §12.5 (sync rules sin subconsulta) · §12.4 (RLS) · D5 del ROADMAP
--
-- La columna existe para que PowerSync pueda acotar la bitácora al bucket de
-- la obra. Todo lo que se prueba aquí sale de que **el escritor de esta tabla
-- es un teléfono que escribe directo a Postgres**:
--
--   1. Se deriva sola: quien inserta no la manda (ni el backend ni la semilla).
--   2. Se **pisa** lo que venga en el insert: un cliente no puede marcar su
--      captura como de otra obra.
--   3. Sigue a la actividad si la fila se mueve de actividad.
--   4. Autorizar sigue siendo cosa de `actividad_id`: la política RLS no
--      cambió, así que una obra ajena no se ve aunque `obra_id` diga otra cosa.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_registro_avance_obra.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'ra-alfa');

insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'Res Uno', 'ra-res1@alfa.mx', 'residente');

insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'MAGNOLIA', 'Magnolia');

insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a1000000-0000-0000-0000-000000000001', 'FRESNO', 'Fresno');

-- Dos obras del mismo residente: la suya de verdad y otra para intentar
-- marcar una captura como ajena.
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'FRESNO 01',
   'aaaaaaaa-0000-0000-0000-000000000001', true),
  ('a3000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'FRESNO 02',
   'aaaaaaaa-0000-0000-0000-000000000001', true);

insert into actividad (id, org_id, obra_id, cant_base, cant_programada) values
  ('a5000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000001', 100, 100),
  ('a5000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000002', 100, 100);

create or replace function pg_temp.esperar(
  p_caso text, p_obtenido text, p_esperado text
) returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaba %, se obtuvo %',
      p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%]', p_caso;
end;
$$;

-- ------------------------------------------------------------
-- 1 · Se deriva sola: el insert no menciona `obra_id`, igual que el repo
--     (`actividades_sql.py`) y la semilla de demo.
-- ------------------------------------------------------------
insert into registro_avance (id, org_id, actividad_id, delta_ejecutado, usuario_id)
values ('a6000000-0000-0000-0000-000000000001',
        '11111111-1111-1111-1111-111111111111',
        'a5000000-0000-0000-0000-000000000001', 10,
        'aaaaaaaa-0000-0000-0000-000000000001');

select pg_temp.esperar(
  'obra_id se deriva de la actividad',
  (select obra_id::text from registro_avance
    where id = 'a6000000-0000-0000-0000-000000000001'),
  'a3000000-0000-0000-0000-000000000001'
);

-- ------------------------------------------------------------
-- 2 · Se pisa lo que venga: el cliente escribe directo (D5), así que decir
--     "esta captura es de la otra obra" no puede funcionar.
-- ------------------------------------------------------------
insert into registro_avance
  (id, org_id, obra_id, actividad_id, delta_ejecutado, usuario_id)
values ('a6000000-0000-0000-0000-000000000002',
        '11111111-1111-1111-1111-111111111111',
        'a3000000-0000-0000-0000-000000000002',   -- <- la obra equivocada
        'a5000000-0000-0000-0000-000000000001', 5,
        'aaaaaaaa-0000-0000-0000-000000000001');

select pg_temp.esperar(
  'un obra_id inventado por el cliente se ignora',
  (select obra_id::text from registro_avance
    where id = 'a6000000-0000-0000-0000-000000000002'),
  'a3000000-0000-0000-0000-000000000001'
);

-- ------------------------------------------------------------
-- 3 · Si la fila se mueve de actividad, `obra_id` la sigue. Sin esto, una
--     corrección dejaría la captura en el bucket de sync equivocado.
-- ------------------------------------------------------------
update registro_avance
   set actividad_id = 'a5000000-0000-0000-0000-000000000002'
 where id = 'a6000000-0000-0000-0000-000000000002';

select pg_temp.esperar(
  'obra_id sigue a la actividad al moverla',
  (select obra_id::text from registro_avance
    where id = 'a6000000-0000-0000-0000-000000000002'),
  'a3000000-0000-0000-0000-000000000002'
);

-- ------------------------------------------------------------
-- 4 · La derivación no amplía el alcance de nadie: la política sigue
--     resolviendo por `actividad_id` (§12.4). El residente ve las dos obras
--     porque las dos son suyas; una org ajena no ve ninguna.
-- ------------------------------------------------------------
set local role obractrl_api;

select set_config('app.org_id', '22222222-2222-2222-2222-222222222222', true);
select set_config('app.usuario_id', 'cccccccc-0000-0000-0000-000000000001', true);
select set_config('app.rol', 'super_intendente', true);

select pg_temp.esperar(
  'una org ajena no ve la bitácora',
  (select count(*)::text from registro_avance),
  '0'
);

select set_config('app.org_id', '11111111-1111-1111-1111-111111111111', true);
select set_config('app.usuario_id', 'aaaaaaaa-0000-0000-0000-000000000001', true);
select set_config('app.rol', 'residente', true);

select pg_temp.esperar(
  'el residente ve la bitácora de sus obras',
  (select count(*)::text from registro_avance),
  '2'
);

reset role;
rollback;

\echo '== registro_avance.obra_id: todas las aserciones pasaron =='
