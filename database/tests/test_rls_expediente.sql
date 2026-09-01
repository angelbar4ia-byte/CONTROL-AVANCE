-- ============================================================
-- ObraCtrl · Aislamiento RLS del expediente y del periodo bloqueado
-- Spec §7.9 (`ExpedienteDoc`) · §11.2 (Expediente) · §11.3 E.5 (bloquear el
-- periodo) · §12.4 (RLS) · D4 del roadmap ("toda tabla nueva entra con
-- política RLS + prueba de aislamiento en el mismo PR").
--
-- Dos tablas de la Fase 5:
--   expediente_doc     entra al loop genérico `por_obra` de la migración 0012.
--   periodo_bloqueado   trae su propia política en la migración 0020.
--
-- Lo que se prueba:
--   1. El alcance por rol del §4 se hereda de la obra en las dos tablas.
--   2. Nadie ve el expediente ni el candado de otra organización.
--   3. La escritura no es más ancha que la lectura: no se puede subir un
--      documento —ni cerrar un periodo— de una obra que no se ve.
--   4. Sin contexto (anónimo) no se ve nada, que es la frontera del §10.7.
--
-- Uso:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/test_rls_expediente.sql
-- ============================================================

\set ON_ERROR_STOP on
\set QUIET on

begin;

-- ------------------------------------------------------------
-- Montaje: dos organizaciones. En Alfa, dos obras en clusters
-- distintos para que el alcance del supervisor se note.
-- ------------------------------------------------------------
insert into organizacion (id, nombre, slug) values
  ('11111111-1111-1111-1111-111111111111', 'Org Alfa', 'exp-alfa'),
  ('22222222-2222-2222-2222-222222222222', 'Org Beta', 'exp-beta');

insert into usuario (id, org_id, nombre, email, rol) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'Res Uno',   'exp-res1@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'Res Dos',   'exp-res2@alfa.mx', 'residente'),
  ('aaaaaaaa-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
   'Sup Uno',   'exp-sup1@alfa.mx', 'supervisor'),
  ('aaaaaaaa-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111',
   'Ctrl Uno',  'exp-ctrl1@alfa.mx', 'control_obra'),
  ('aaaaaaaa-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111',
   'Super Uno', 'exp-si1@alfa.mx',  'super_intendente'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'Res Beta',  'exp-res1@beta.mx', 'residente'),
  ('bbbbbbbb-0000-0000-0000-000000000005', '22222222-2222-2222-2222-222222222222',
   'Super Beta', 'exp-si1@beta.mx', 'super_intendente');

insert into proyecto (id, org_id, clave, nombre) values
  ('a1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'MAGNOLIA', 'Magnolia'),
  ('a1000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'ROBLE', 'Roble'),
  ('b1000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'ENCINO', 'Encino');

insert into cluster (id, org_id, proyecto_id, clave, nombre) values
  ('a2000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a1000000-0000-0000-0000-000000000001', 'FRESNO', 'Fresno'),
  ('a2000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'a1000000-0000-0000-0000-000000000002', 'CEDRO', 'Cedro'),
  ('b2000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'b1000000-0000-0000-0000-000000000001', 'OLMO', 'Olmo');

insert into obra (id, org_id, cluster_id, clave, residente_id, es_urba) values
  ('a3000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000001', 'FRESNO 01',
   'aaaaaaaa-0000-0000-0000-000000000001', true),
  ('a3000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
   'a2000000-0000-0000-0000-000000000002', 'CEDRO 01',
   'aaaaaaaa-0000-0000-0000-000000000002', true),
  ('b3000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'b2000000-0000-0000-0000-000000000001', 'OLMO 01',
   'bbbbbbbb-0000-0000-0000-000000000001', true);

-- Alcance territorial de la 0011, que la 0042 ya no lee.
insert into supervisor_cluster (org_id, supervisor_id, cluster_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000003', 'a2000000-0000-0000-0000-000000000001');

insert into control_proyecto (org_id, usuario_id, proyecto_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000004', 'a1000000-0000-0000-0000-000000000001');

-- Alcance real desde la 0042 (§4). `residente_obra` lo llenó el trigger al
-- insertar las obras. Sup Uno lleva solo a Res Uno —de ahí que siga viendo una
-- obra y no dos—; Super Uno tiene a Sup Uno y, directo, a Res Dos, así que
-- alcanza las dos obras de Alfa.
insert into supervisor_residente (org_id, supervisor_id, residente_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000001');

insert into superintendente_usuario (org_id, superintendente_id, usuario_id) values
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000003'),
  ('11111111-1111-1111-1111-111111111111',
   'aaaaaaaa-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000002'),
  ('22222222-2222-2222-2222-222222222222',
   'bbbbbbbb-0000-0000-0000-000000000005', 'bbbbbbbb-0000-0000-0000-000000000001');

-- Un documento por obra (§7.9). `url` es la CLAVE del objeto en R2, no una
-- URL firmada: la firma caduca, la clave no (§12.2).
insert into expediente_doc (org_id, obra_id, tipo, nombre, url) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   'contrato', 'Contrato FRESNO 01.pdf', 'alfa/fresno-01/contrato.pdf'),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
   'plano', 'Planta CEDRO 01.pdf', 'alfa/cedro-01/planta.pdf'),
  ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001',
   'contrato', 'Contrato OLMO 01.pdf', 'beta/olmo-01/contrato.pdf');

-- Una estimación validada por obra y su candado de periodo (§11.3 E.5).
insert into estimacion (id, org_id, obra_id, folio, semana, anio, modo, estatus,
                        monto_total) values
  ('a4000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'a3000000-0000-0000-0000-000000000001', 'EXP-3326-001', 33, 2026, 'destajo',
   'validada', 1000),
  ('b4000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222',
   'b3000000-0000-0000-0000-000000000001', 'EXP-3326-001', 33, 2026, 'destajo',
   'validada', 1000);

insert into periodo_bloqueado (org_id, obra_id, anio, semana, estimacion_id) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   2026, 33, 'a4000000-0000-0000-0000-000000000001'),
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
   2026, 33, null),
  ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001',
   2026, 33, 'b4000000-0000-0000-0000-000000000001');

-- ------------------------------------------------------------
-- Helpers (mismos que `test_rls.sql`)
-- ------------------------------------------------------------
create or replace function pg_temp.esperar(
  p_caso text, p_obtenido bigint, p_esperado bigint
) returns void language plpgsql as $$
begin
  if p_obtenido is distinct from p_esperado then
    raise exception 'FALLA [%]: se esperaban % filas, se vieron %',
      p_caso, p_esperado, p_obtenido;
  end if;
  raise notice 'OK  [%] -> % filas', p_caso, p_obtenido;
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

set local role obractrl_api;   -- NO es owner: las políticas aplican

-- ------------------------------------------------------------
-- 1 · El expediente hereda el alcance de su obra (§11.2 "todos lectura",
--     acotado por RLS).
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('residente ve el expediente de su obra', count(*), 1)
  from expediente_doc;

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000003', 'supervisor');
select pg_temp.esperar('supervisor ve solo el de su residente', count(*), 1)
  from expediente_doc;
select pg_temp.esperar('supervisor no ve el de un residente ajeno', count(*), 0)
  from expediente_doc where nombre = 'Planta CEDRO 01.pdf';

-- Desde la 0042 Control ve toda la organización: antes esta cuenta era 1.
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
select pg_temp.esperar('control ve el expediente de toda su org', count(*), 2)
  from expediente_doc;

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');
-- Sigue siendo 2, pero por otra razón: ya no es "toda la org" sino la suma de
-- su gente —Sup Uno (que lleva a Res Uno) y Res Dos, directo—.
select pg_temp.esperar('super intendente ve el de su gente', count(*), 2)
  from expediente_doc;
select pg_temp.esperar('super intendente NO cruza de org', count(*), 0)
  from expediente_doc where org_id = '22222222-2222-2222-2222-222222222222';

-- ------------------------------------------------------------
-- 2 · El candado del periodo hereda el mismo alcance que la estimación que
--     lo origina (migración 0020).
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000001', 'residente');
select pg_temp.esperar('residente ve el candado de su obra', count(*), 1)
  from periodo_bloqueado;

select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('super intendente ve los candados de su org', count(*), 2)
  from periodo_bloqueado;

select pg_temp.como('22222222-2222-2222-2222-222222222222',
                    'bbbbbbbb-0000-0000-0000-000000000005', 'super_intendente');
select pg_temp.esperar('Beta no ve los candados de Alfa', count(*), 1)
  from periodo_bloqueado;
select pg_temp.esperar('Beta no ve el expediente de Alfa', count(*), 1)
  from expediente_doc;

-- ------------------------------------------------------------
-- 3 · La escritura no puede ser más ancha que la lectura.
-- ------------------------------------------------------------
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');

-- Permitido en cualquier obra de la organización (§11.2: la subida es de C y
-- SI; el ROL exacto lo aplica el caso de uso, RLS da el aislamiento).
insert into expediente_doc (org_id, obra_id, tipo, nombre, url) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   'acta', 'Acta de entrega.pdf', 'alfa/fresno-01/acta.pdf');
select pg_temp.esperar('control sube a una obra de su org', count(*), 3)
  from expediente_doc;

-- La frontera de escritura ya no se prueba con Control —desde la 0042 no tiene
-- ninguna dentro de su organización— sino con el supervisor, que solo alcanza
-- las obras de sus residentes: CEDRO 01 es de Res Dos, que no es suyo.
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000003', 'supervisor');
do $$
begin
  insert into expediente_doc (org_id, obra_id, tipo, nombre, url) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
     'acta', 'Acta ajena.pdf', 'alfa/cedro-01/acta.pdf');
  raise exception 'FALLA: se subió un documento a una obra fuera del alcance';
exception
  when insufficient_privilege then
    raise notice 'OK  [no se sube al expediente de una obra que no se ve]';
end;
$$;

-- Rechazado: cerrar el periodo de una obra fuera del alcance sería un
-- candado ajeno —y un cobro bloqueado de más (§11.3 E.5).
do $$
begin
  insert into periodo_bloqueado (org_id, obra_id, anio, semana) values
    ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000003',
     2026, 34);
  raise exception 'FALLA: se bloqueó el periodo de una obra fuera del alcance';
exception
  when insufficient_privilege then
    raise notice 'OK  [no se cierra el periodo de una obra que no se ve]';
end;
$$;

-- Cruzar de organización tampoco: el `org_id` del token manda sobre el que
-- venga en la fila (§12.4).
select pg_temp.como('11111111-1111-1111-1111-111111111111',
                    'aaaaaaaa-0000-0000-0000-000000000004', 'control_obra');
do $$
begin
  insert into expediente_doc (org_id, obra_id, tipo, nombre, url) values
    ('22222222-2222-2222-2222-222222222222', 'b3000000-0000-0000-0000-000000000001',
     'acta', 'Acta de Beta.pdf', 'beta/olmo-01/acta.pdf');
  raise exception 'FALLA: se escribió en el expediente de otra organización';
exception
  when insufficient_privilege then
    raise notice 'OK  [no se escribe en el expediente de otra org]';
end;
$$;

-- ------------------------------------------------------------
-- 4 · Un periodo se bloquea una sola vez: dos modos de pago (§6) validados
--     en la misma semana comparten candado (`uq_periodo_bloqueado`).
-- ------------------------------------------------------------
insert into periodo_bloqueado (org_id, obra_id, anio, semana) values
  ('11111111-1111-1111-1111-111111111111', 'a3000000-0000-0000-0000-000000000001',
   2026, 33)
on conflict on constraint uq_periodo_bloqueado do nothing;
select pg_temp.esperar('el segundo modo no duplica el candado', count(*), 1)
  from periodo_bloqueado
 where obra_id = 'a3000000-0000-0000-0000-000000000001' and anio = 2026 and semana = 33;

-- ------------------------------------------------------------
-- 5 · Sin contexto -> nada (§10.7).
-- ------------------------------------------------------------
select set_config('app.org_id', '', true);
select set_config('app.usuario_id', '', true);
select set_config('app.rol', '', true);
select pg_temp.esperar('sin contexto no ve el expediente', count(*), 0)
  from expediente_doc;
select pg_temp.esperar('sin contexto no ve los candados', count(*), 0)
  from periodo_bloqueado;

reset role;
rollback;

\echo '== RLS expediente y periodo: todas las aserciones pasaron =='
