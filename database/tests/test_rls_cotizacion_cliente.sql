-- ============================================================
-- ObraCtrl · Cotización al cliente (migración 0084)
--   1. El alcance por rol se hereda de la obra; otra organización no ve nada.
--   2. No se escribe en obra ajena.
--   3. Lo cotizado no se reescribe: solo se registra la respuesta, una vez.
--   4. No se borra.
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_cotizacion_cliente.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'cc-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'cc-beta');
insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Res Uno', 'cc-res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Res Dos', 'cc-res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'Ctrl', 'cc-ctrl@alfa.mx', 'control_obra'),
  ('bbbbbbbb-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222', 'Ctrl B', 'cc-ctrl@beta.mx', 'control_obra');
insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'MAG', 'Magnolia'),
  ('b1000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'ENC', 'Encino');
insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a1000000-0000-0000-0000-000000000001', 'FRE', 'Fresno'),
  ('b2000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'b1000000-0000-0000-0000-000000000001', 'OLM', 'Olmo');
insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F1', 'aaaaaaaa-0000-0000-0000-000000000001', true),
  ('a3000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a2000000-0000-0000-0000-000000000001', 'F2', 'aaaaaaaa-0000-0000-0000-000000000002', true),
  ('b3000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'b2000000-0000-0000-0000-000000000001', 'O1', null, true);
insert into cotizacion_cliente (id, org_id, obra_id, folio, metodo_precio, factor, costo_entra, costo_sale,
                                precio_por_diferencia, precio, creada_por) values
  ('c0000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001', 'CZ-F1-001', 'por_diferencia', 0.7, 700, 0, 1000, 1000, 'aaaaaaaa-0000-0000-0000-000000000004'),
  ('c0000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 'CZ-F2-001', 'por_diferencia', 0.7, 700, 0, 1000, 1000, 'aaaaaaaa-0000-0000-0000-000000000004'),
  ('c0000000-0000-0000-0000-000000000003', '22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001', 'CZ-O1-001', 'por_diferencia', 0.7, 700, 0, 1000, 1000, 'bbbbbbbb-0000-0000-0000-000000000004');

create or replace function pg_temp.como(p_org uuid, p_usuario uuid, p_rol text)
returns void language plpgsql as $$
begin
  perform set_config('app.org_id', p_org::text, true);
  perform set_config('app.usuario_id', p_usuario::text, true);
  perform set_config('app.rol', p_rol, true);
end;
$$;
create or replace function pg_temp.esperar(p_caso text, p_obtenido bigint, p_esperado bigint)
returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaban % filas, se vieron %', p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%] -> % filas', p_caso, p_obtenido;
end;
$$;

set local role obractrl_api;

select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('residente ve la de su obra', count(*), 1) from cotizacion_cliente;
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('control ve las de su org', count(*), 2) from cotizacion_cliente;
select pg_temp.como('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('Beta solo ve la suya', count(*), 1) from cotizacion_cliente;

-- 2 · No se escribe en obra ajena
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
do $$
begin
  insert into cotizacion_cliente (org_id, obra_id, folio, metodo_precio, factor, costo_entra, costo_sale,
                                  precio_por_diferencia, precio, creada_por)
  values ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003', 'CZ-X', 'por_diferencia',
          0.7, 1, 0, 1, 1, 'aaaaaaaa-0000-0000-0000-000000000001');
  raise exception 'FALLA [cotización en obra ajena]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [cotización en obra ajena] -> rechazada por RLS';
end;
$$;

-- 3 · Lo cotizado no se reescribe; la respuesta se registra una vez
select pg_temp.como('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
do $$
begin
  update cotizacion_cliente set precio = 1 where id = 'c0000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [reescribir precio]: debió rechazarse';
exception when check_violation then
  raise notice 'OK  [reescribir precio] -> rechazado';
end;
$$;
update cotizacion_cliente set estado = 'aceptada', respondida_por = 'aaaaaaaa-0000-0000-0000-000000000004',
       respondida_en = now() where id = 'c0000000-0000-0000-0000-000000000001';
select pg_temp.esperar('la respuesta se registra', count(*), 1) from cotizacion_cliente where estado = 'aceptada';
do $$
begin
  update cotizacion_cliente set estado = 'rechazada', respondida_en = now() where id = 'c0000000-0000-0000-0000-000000000001';
  raise exception 'FALLA [responder dos veces]: debió rechazarse';
exception when check_violation then
  raise notice 'OK  [responder dos veces] -> rechazado';
end;
$$;

-- 4 · No se borra
do $$
begin
  delete from cotizacion_cliente;
  raise exception 'FALLA [borrar]: debió rechazarse';
exception when insufficient_privilege then
  raise notice 'OK  [borrar] -> sin permiso';
end;
$$;

rollback;
