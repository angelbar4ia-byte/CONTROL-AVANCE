-- ============================================================
-- ObraCtrl · Lo asignado está congelado
-- Migración 0078 (trigger `trg_actividad_congelar_lo_asignado`) · cerebro D-571
--
-- «Asignar equivale a contratar: de ahí en adelante, cambiar es control de cambio.»
--
-- Lo que se prueba:
--   1. Antes de asignar la cantidad base y el precio se mueven libremente.
--   2. Con la parte asignada, ni la cantidad base ni el precio se tocan directo.
--   3. Lo programado (fechas) y lo ejecutado (avance) no se congelan.
--   4. El control de cambio, que declara su intención, sí puede.
--   5. La congelación es de la parte, no de la obra: otra parte sigue libre.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_congelar_lo_asignado.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'cg-alfa');
insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAGNOLIA', 'Magnolia');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRESNO', 'Fresno');
insert into obra (id, org_id, cluster_id, clave, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'FRESNO 01', true);
insert into nivel (id, org_id, clave, descripcion, orden) values
  ('a6000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'PB', 'PB', 1);
insert into etapa_constructiva (id, org_id, nivel_id, clave, descripcion, orden) values
  ('a7000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a6000000-0000-0000-0000-000000000001', 'ECO-1', 'Etapa 1', 1),
  ('a7000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a6000000-0000-0000-0000-000000000001', 'ECO-2', 'Etapa 2', 2);
insert into actividad (id, org_id, obra_id, etapa_id, cant_base, cant_programada, precio_unitario) values
  ('a8000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'a7000000-0000-0000-0000-000000000001', 100, 100, 10),
  ('a8000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'a7000000-0000-0000-0000-000000000002', 100, 100, 10);

-- 1 · Sin asignar, libre
update actividad set cant_base = 120, precio_unitario = 11
 where id = 'a8000000-0000-0000-0000-000000000001';
do $$ begin
  if (select cant_base from actividad where id = 'a8000000-0000-0000-0000-000000000001') <> 120 then
    raise exception 'FALLA [libre antes de asignar]';
  end if;
  raise notice 'OK  [libre antes de asignar] -> cant_base 120';
end $$;

-- 2 · Asignada: congelada
insert into parte_estado (org_id, obra_id, clave, estado) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   'etapa:a7000000-0000-0000-0000-000000000001', 'asignada');

do $$ begin
  update actividad set cant_base = 150 where id = 'a8000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [cantidad base de lo asignado]: el UPDATE debió rechazarse';
exception when check_violation then
  raise notice 'OK  [cantidad base de lo asignado] -> congelada';
end $$;
do $$ begin
  update actividad set precio_unitario = 99 where id = 'a8000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [precio de lo asignado]: el UPDATE debió rechazarse';
exception when check_violation then
  raise notice 'OK  [precio de lo asignado] -> congelado';
end $$;

-- 3 · Lo programado y lo ejecutado no se congelan
update actividad set fecha_inicio = '2026-03-02', fecha_termino = '2026-03-13',
                     duracion_dias = 9, avance_pct = 10
 where id = 'a8000000-0000-0000-0000-000000000001';
do $$ begin
  raise notice 'OK  [fechas y avance de lo asignado] -> siguen libres';
end $$;

-- 4 · El control de cambio, que declara su intención, sí puede
select set_config('app.cambio_autorizado', 'on', true);
update actividad set cant_base = 150 where id = 'a8000000-0000-0000-0000-000000000001';
select set_config('app.cambio_autorizado', 'off', true);
do $$ begin
  if (select cant_base from actividad where id = 'a8000000-0000-0000-0000-000000000001') <> 150 then
    raise exception 'FALLA [control de cambio]';
  end if;
  raise notice 'OK  [control de cambio] -> cant_base 150';
end $$;

-- 5 · La congelación es de la parte: la otra sigue libre
update actividad set cant_base = 200 where id = 'a8000000-0000-0000-0000-000000000002';
do $$ begin
  raise notice 'OK  [otra parte] -> sigue libre';
end $$;

-- Un concepto independiente se congela por sí solo (su clave es `concepto:<id>`).
update actividad set parte_independiente = true where id = 'a8000000-0000-0000-0000-000000000002';
insert into parte_estado (org_id, obra_id, clave, estado) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   'concepto:a8000000-0000-0000-0000-000000000002', 'asignada');
do $$ begin
  update actividad set cant_base = 250 where id = 'a8000000-0000-0000-0000-000000000002';
  raise exception 'FALLA [concepto independiente asignado]: el UPDATE debió rechazarse';
exception when check_violation then
  raise notice 'OK  [concepto independiente asignado] -> congelado';
end $$;

rollback;
