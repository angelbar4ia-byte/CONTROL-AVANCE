-- ============================================================
-- ObraCtrl · Prueba · el avance de la obra se deriva de sus actividades
-- Spec §6 · §8.2 · MODELO.md §3b del cerebro (D-514) · decisión D5
--
-- Cubre la migración 0064. Antes de ella `obra.avance_pct` quedaba en 0 para
-- siempre y el estatus de la obra nunca salía de `pendiente`, aunque todas sus
-- actividades estuvieran concluidas (frenaba el cierre de obra).
--
--   1. La ruta directa (PowerSync) mueve el avance de la OBRA, no solo el de la
--      actividad, y lo pondera por importe (cant_base × precio_unitario).
--   2. El estatus se deriva: >0 en_proceso · >=90 por_entregar, y vuelve si el
--      avance baja (un delta borrado).
--   3. `iniciada` se conserva con avance 0; sin ella, vuelve a `pendiente`.
--   4. `entregada` congela: ni el avance ni el estatus se mueven.
--   5. Sin importes cae al promedio simple.
--   6. Agregar o quitar una actividad recalcula (una nueva diluye).
--   7. No toca las obras de otra organización.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_avance_de_obra.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('a1111111-1111-1111-1111-111111111111', 'Org Alfa', 'test-avance-alfa'),
  ('a2222222-2222-2222-2222-222222222222', 'Org Beta', 'test-avance-beta');

insert into usuario (id, org_id, auth_user_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'a1111111-1111-1111-1111-111111111111',
   'aaaaaaaa-1000-0000-0000-000000000001', 'Res A', 'res@alfa.mx', 'residente');

insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', 'a1111111-1111-1111-1111-111111111111', 'ALFA', 'Alfa'),
  ('b1000000-0000-0000-0000-000000000001', 'a2222222-2222-2222-2222-222222222222', 'BETA', 'Beta');

insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', 'a1111111-1111-1111-1111-111111111111',
   'a1000000-0000-0000-0000-000000000001', 'ALFA-A', 'Alfa A'),
  ('b2000000-0000-0000-0000-000000000001', 'a2222222-2222-2222-2222-222222222222',
   'b1000000-0000-0000-0000-000000000001', 'BETA-A', 'Beta A');

insert into prototipo (id, org_id, proyecto_id, clave, nombre) values
  ('a6000000-0000-0000-0000-000000000001', 'a1111111-1111-1111-1111-111111111111',
   'a1000000-0000-0000-0000-000000000001', 'CAS-A', 'Alfa'),
  ('b6000000-0000-0000-0000-000000000001', 'a2222222-2222-2222-2222-222222222222',
   'b1000000-0000-0000-0000-000000000001', 'CAS-B', 'Beta');

-- Org Alfa: la obra con precios (1), una sin precios (2) y una que se entrega (3).
-- Org Beta: una obra con una actividad que debe quedar intacta.
insert into obra (id, org_id, cluster_id, prototipo_id, clave, residente_id) values
  ('a3000000-0000-0000-0000-000000000001', 'a1111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'a6000000-0000-0000-0000-000000000001',
   'ALFA 01', 'aaaaaaaa-0000-0000-0000-000000000001'),
  ('a3000000-0000-0000-0000-000000000002', 'a1111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'a6000000-0000-0000-0000-000000000001',
   'ALFA 02', 'aaaaaaaa-0000-0000-0000-000000000001'),
  ('a3000000-0000-0000-0000-000000000003', 'a1111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'a6000000-0000-0000-0000-000000000001',
   'ALFA 03', 'aaaaaaaa-0000-0000-0000-000000000001'),
  ('b3000000-0000-0000-0000-000000000001', 'a2222222-2222-2222-2222-222222222222',
   'b2000000-0000-0000-0000-000000000001', 'b6000000-0000-0000-0000-000000000001',
   'BETA 01', null);

-- ALFA 01: A pesa 100 000 (100 × 1000) y B pesa 10 000 (10 × 1000).
insert into actividad (id, org_id, obra_id, descripcion, cant_base, cant_programada, precio_unitario) values
  ('a4000000-0000-0000-0000-00000000000a', 'a1111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000001', 'Muro', 100, 100, 1000),
  ('a4000000-0000-0000-0000-00000000000b', 'a1111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000001', 'Castillo', 10, 10, 1000),
-- ALFA 02: sin precios -> promedio simple.
  ('a4000000-0000-0000-0000-000000000021', 'a1111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000002', 'Sin precio 1', 10, 10, 0),
  ('a4000000-0000-0000-0000-000000000022', 'a1111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000002', 'Sin precio 2', 10, 10, 0),
-- ALFA 03: la que se entrega.
  ('a4000000-0000-0000-0000-000000000031', 'a1111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000003', 'Entregable', 10, 10, 1000),
-- BETA 01
  ('b4000000-0000-0000-0000-000000000001', 'a2222222-2222-2222-2222-222222222222',
   'b3000000-0000-0000-0000-000000000001', 'Ajena', 10, 10, 1000);

create or replace function pg_temp.esperar_num(p_caso text, p_obtenido numeric, p_esperado numeric)
returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaba %, se obtuvo %', p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%] -> %', p_caso, p_obtenido;
end;
$$;

create or replace function pg_temp.esperar_texto(p_caso text, p_obtenido text, p_esperado text)
returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaba "%", se obtuvo "%"', p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%] -> %', p_caso, p_obtenido;
end;
$$;

create or replace function pg_temp.como(p_org uuid, p_usuario uuid, p_rol text)
returns void language plpgsql as $$
begin
  perform set_config('app.org_id',     p_org::text,     true);
  perform set_config('app.usuario_id', p_usuario::text, true);
  perform set_config('app.rol',        p_rol,           true);
end;
$$;

-- La obra arranca sin avance.
select pg_temp.esperar_num('obra nueva: avance 0', avance_pct, 0)
  from obra where id = 'a3000000-0000-0000-0000-000000000001';
select pg_temp.esperar_texto('obra nueva: pendiente', estatus::text, 'pendiente')
  from obra where id = 'a3000000-0000-0000-0000-000000000001';

set local role obractrl_api;   -- NO es owner: las políticas aplican
select pg_temp.como('a1111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');

-- ------------------------------------------------------------
-- 1 · La ruta directa mueve el avance de la obra, ponderado por importe.
--     B (10 000) al 100 %: 10 000 × 100 / 110 000 = 9.09.
-- ------------------------------------------------------------
insert into registro_avance (org_id, actividad_id, delta_ejecutado, usuario_id) values
  ('a1111111-1111-1111-1111-111111111111', 'a4000000-0000-0000-0000-00000000000b',
   10, 'aaaaaaaa-0000-0000-0000-000000000001');

select pg_temp.esperar_num('B al 100 %: la obra va en 9.09 (ponderado, no 50)', avance_pct, 9.09)
  from obra where id = 'a3000000-0000-0000-0000-000000000001';
select pg_temp.esperar_texto('avance > 0 -> en_proceso', estatus::text, 'en_proceso')
  from obra where id = 'a3000000-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- 2 · >= 90 % -> por_entregar. A al 90 %: (90 000 + 10 000) / 110 000 = 90.91.
-- ------------------------------------------------------------
insert into registro_avance (id, org_id, actividad_id, delta_ejecutado, usuario_id) values
  ('a5000000-0000-0000-0000-000000000001', 'a1111111-1111-1111-1111-111111111111',
   'a4000000-0000-0000-0000-00000000000a', 90, 'aaaaaaaa-0000-0000-0000-000000000001');

select pg_temp.esperar_num('A al 90 %: la obra va en 90.91', avance_pct, 90.91)
  from obra where id = 'a3000000-0000-0000-0000-000000000001';
select pg_temp.esperar_texto('>= 90 -> por_entregar', estatus::text, 'por_entregar')
  from obra where id = 'a3000000-0000-0000-0000-000000000001';

insert into registro_avance (org_id, actividad_id, delta_ejecutado, usuario_id) values
  ('a1111111-1111-1111-1111-111111111111', 'a4000000-0000-0000-0000-00000000000a',
   10, 'aaaaaaaa-0000-0000-0000-000000000001');
select pg_temp.esperar_num('todo concluido: 100', avance_pct, 100)
  from obra where id = 'a3000000-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- 3 · El estatus se deriva también hacia abajo: se borra el delta de 90.
--     A queda en 10 %: (10 000 + 10 000) / 110 000 = 18.18 -> en_proceso.
-- ------------------------------------------------------------
delete from registro_avance where id = 'a5000000-0000-0000-0000-000000000001';
select pg_temp.esperar_num('sin el delta de 90: 18.18', avance_pct, 18.18)
  from obra where id = 'a3000000-0000-0000-0000-000000000001';
select pg_temp.esperar_texto('baja de 90 -> en_proceso', estatus::text, 'en_proceso')
  from obra where id = 'a3000000-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- 4 · Sin importes -> promedio simple. Una al 100 % y otra en 0: 50.
-- ------------------------------------------------------------
insert into registro_avance (org_id, actividad_id, delta_ejecutado, usuario_id) values
  ('a1111111-1111-1111-1111-111111111111', 'a4000000-0000-0000-0000-000000000021',
   10, 'aaaaaaaa-0000-0000-0000-000000000001');
select pg_temp.esperar_num('sin precios: promedio simple 50', avance_pct, 50)
  from obra where id = 'a3000000-0000-0000-0000-000000000002';

-- ------------------------------------------------------------
-- 5 · No toca otra organización.
-- ------------------------------------------------------------
reset role;
select pg_temp.esperar_num('Org Beta intacta: avance 0', avance_pct, 0)
  from obra where id = 'b3000000-0000-0000-0000-000000000001';
select pg_temp.esperar_texto('Org Beta intacta: pendiente', estatus::text, 'pendiente')
  from obra where id = 'b3000000-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- 6 · `iniciada` se conserva con avance 0; sin ella, vuelve a pendiente.
--     (Como admin: marcar la obra es del flujo, no de quien captura.)
-- ------------------------------------------------------------
update obra set estatus = 'iniciada' where id = 'a3000000-0000-0000-0000-000000000003';

set local role obractrl_api;
select pg_temp.como('a1111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');

select pg_temp.esperar_texto('iniciada con avance 0 se conserva', estatus::text, 'iniciada')
  from obra where id = 'a3000000-0000-0000-0000-000000000003';

insert into registro_avance (id, org_id, actividad_id, delta_ejecutado, usuario_id) values
  ('a5000000-0000-0000-0000-000000000031', 'a1111111-1111-1111-1111-111111111111',
   'a4000000-0000-0000-0000-000000000031', 5, 'aaaaaaaa-0000-0000-0000-000000000001');
select pg_temp.esperar_texto('iniciada + avance -> en_proceso', estatus::text, 'en_proceso')
  from obra where id = 'a3000000-0000-0000-0000-000000000003';

-- El avance vuelve a 0 (se borra el delta): una obra en_proceso sin avance
-- regresa a pendiente, como Obra.sincronizar_avance.
delete from registro_avance where id = 'a5000000-0000-0000-0000-000000000031';
select pg_temp.esperar_texto('en_proceso sin avance -> pendiente', estatus::text, 'pendiente')
  from obra where id = 'a3000000-0000-0000-0000-000000000003';

-- ------------------------------------------------------------
-- 7 · `entregada` congela: ni avance ni estatus se mueven.
-- ------------------------------------------------------------
reset role;
update obra set estatus = 'entregada', avance_pct = 100
 where id = 'a3000000-0000-0000-0000-000000000003';

set local role obractrl_api;
select pg_temp.como('a1111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
insert into registro_avance (org_id, actividad_id, delta_ejecutado, usuario_id) values
  ('a1111111-1111-1111-1111-111111111111', 'a4000000-0000-0000-0000-000000000031',
   2, 'aaaaaaaa-0000-0000-0000-000000000001');
select pg_temp.esperar_texto('entregada se queda entregada', estatus::text, 'entregada')
  from obra where id = 'a3000000-0000-0000-0000-000000000003';
select pg_temp.esperar_num('entregada conserva su avance', avance_pct, 100)
  from obra where id = 'a3000000-0000-0000-0000-000000000003';

-- ------------------------------------------------------------
-- 8 · Una actividad nueva diluye; quitarla restaura. (Como admin.)
-- ------------------------------------------------------------
reset role;
insert into actividad (id, org_id, obra_id, descripcion, cant_base, cant_programada, precio_unitario)
values ('a4000000-0000-0000-0000-00000000000c', 'a1111111-1111-1111-1111-111111111111',
        'a3000000-0000-0000-0000-000000000001', 'Nueva', 100, 100, 1000);
-- Pesos: A 100 000 (10 %), B 10 000 (100 %), nueva 100 000 (0 %):
-- (10 000 + 10 000 + 0) / 210 000 = 9.52.
select pg_temp.esperar_num('una actividad nueva diluye el avance', avance_pct, 9.52)
  from obra where id = 'a3000000-0000-0000-0000-000000000001';

delete from actividad where id = 'a4000000-0000-0000-0000-00000000000c';
select pg_temp.esperar_num('quitarla restaura el avance', avance_pct, 18.18)
  from obra where id = 'a3000000-0000-0000-0000-000000000001';

rollback;
