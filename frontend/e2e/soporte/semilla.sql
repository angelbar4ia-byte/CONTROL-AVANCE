-- ============================================================
-- Semilla de los E2E de workflows (§11.3).
--
-- Recrea desde cero la organización `e2e`: borra la que haya (el cascade se
-- lleva todo lo que cuelga de ella) y la arma otra vez. Así cada corrida parte
-- del mismo estado y un E2E que dejó basura no contamina al siguiente.
--
-- Uso (desde la raíz del repo):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f frontend/e2e/soporte/semilla.sql
--
-- Usuarios (la contraseña es E2E_PASSWORD; la auth falsa no distingue):
--   res@e2e.mx residente · sup@e2e.mx supervisor · ctrl@e2e.mx control_obra
--   si@e2e.mx super_intendente
-- ============================================================
\set ON_ERROR_STOP on

delete from organizacion where slug = 'e2e';

insert into organizacion (nombre, slug) values ('Constructora E2E', 'e2e')
returning id as org_id \gset

-- Catálogos canónicos (unidades, frentes, familias...). La semilla espera el
-- valor ya entrecomillado.
\set org_id_q '\'' :org_id '\''
\set org_id :org_id_q
\ir ../../../database/seeds/01_semilla_canonica.sql
\set org_id :org_id_q

begin;

insert into usuario (org_id, nombre, email, rol) values
  (:org_id, 'Rosa Residente',   'res@e2e.mx',  'residente'),
  (:org_id, 'Sara Supervisora', 'sup@e2e.mx',  'supervisor'),
  (:org_id, 'Carlos Control',   'ctrl@e2e.mx', 'control_obra'),
  (:org_id, 'Silvia Superintendente', 'si@e2e.mx', 'super_intendente');

select id as res_id  from usuario where org_id = :org_id and email = 'res@e2e.mx'  \gset
select id as sup_id  from usuario where org_id = :org_id and email = 'sup@e2e.mx'  \gset
select id as ctrl_id from usuario where org_id = :org_id and email = 'ctrl@e2e.mx' \gset
select id as si_id   from usuario where org_id = :org_id and email = 'si@e2e.mx'   \gset

insert into proyecto (org_id, clave, nombre) values (:org_id, 'PROY-E2E', 'Proyecto E2E')
returning id as proyecto_id \gset

insert into cluster (org_id, proyecto_id, clave, nombre)
values (:org_id, :'proyecto_id', 'CLU-E2E', 'Cluster E2E')
returning id as cluster_id \gset

insert into supervisor_cluster (org_id, supervisor_id, cluster_id)
values (:org_id, :'sup_id', :'cluster_id');
insert into control_proyecto (org_id, usuario_id, proyecto_id)
values (:org_id, :'ctrl_id', :'proyecto_id');
-- Cadena de mando (migración 0042): SI -> Supervisor -> Residente -> Obra.
insert into supervisor_residente (org_id, supervisor_id, residente_id)
values (:org_id, :'sup_id', :'res_id');
insert into superintendente_usuario (org_id, superintendente_id, usuario_id)
values (:org_id, :'si_id', :'sup_id');

-- Árbol del prototipo: etapa -> nivel -> 3 conceptos, cada uno con CPU vigente.
insert into prototipo (org_id, proyecto_id, clave, nombre)
values (:org_id, :'proyecto_id', 'CAS-E2E', 'Casa E2E')
returning id as proto_id \gset

insert into etapa_constructiva (org_id, clave, descripcion, orden)
values (:org_id, 'CIM', 'Cimentación', 1) returning id as etapa_id \gset
insert into nivel (org_id, clave, descripcion, orden)
values (:org_id, 'PB', 'Planta baja', 1) returning id as nivel_id \gset

select id as unidad_m2 from unidad where org_id = :org_id and clave = 'm2' \gset
select id as fam_obra from familia where org_id = :org_id and clave = 'FAM-C-OBRA' \gset

insert into concepto (org_id, tipo, clave, descripcion, unidad_id, familia_id) values
  (:org_id, 'concepto', 'E2E-EXC', 'Excavación de cepas',   :'unidad_m2', :'fam_obra'),
  (:org_id, 'concepto', 'E2E-PLA', 'Plantilla de concreto', :'unidad_m2', :'fam_obra'),
  (:org_id, 'concepto', 'E2E-CIM', 'Cimiento de mampostería', :'unidad_m2', :'fam_obra');

insert into cpu (org_id, concepto_id, version, precio_unitario, precio_destajo, vigente)
select :org_id, c.id, 1,
       case c.clave when 'E2E-EXC' then 120 when 'E2E-PLA' then 200 else 450 end,
       case c.clave when 'E2E-EXC' then 90  when 'E2E-PLA' then 150 else 340 end,
       true
from concepto c where c.org_id = :org_id and c.clave like 'E2E-%';

insert into prototipo_nodo (org_id, prototipo_id, tipo, nombre, clave, etapa_id, orden)
values (:org_id, :'proto_id', 'etapa', 'Cimentación', 'N-ETA', :'etapa_id', 1)
returning id as n_etapa \gset
insert into prototipo_nodo (org_id, prototipo_id, parent_id, tipo, nombre, clave, nivel_id, orden)
values (:org_id, :'proto_id', :'n_etapa', 'nivel', 'Planta baja', 'N-NIV', :'nivel_id', 1)
returning id as n_nivel \gset
insert into prototipo_nodo (org_id, prototipo_id, parent_id, tipo, nombre, clave, concepto_id, cantidad, orden)
select :org_id, :'proto_id', :'n_nivel', 'concepto', c.descripcion, 'N-' || c.clave, c.id,
       case c.clave when 'E2E-EXC' then 100 when 'E2E-PLA' then 80 else 60 end,
       row_number() over (order by c.clave)
from concepto c where c.org_id = :org_id and c.clave like 'E2E-%';

-- Calendario del año en curso y ancla de semana (§3.1). Sin el ancla el sistema
-- no sabe qué semana es y se niega a numerarlas: la estimación (§11.3 E) lo
-- dice con «Nadie ha fijado el ancla de semana». Se ancla a la semana que
-- contiene HOY, no a una fija, para que la semilla sirva en cualquier fecha.
select app.generar_calendario(:org_id::uuid, 'obra'::tipo_semana,
                              extract(year from current_date)::smallint);
select app.generar_calendario(:org_id::uuid, 'ordinaria'::tipo_semana,
                              extract(year from current_date)::smallint);

insert into ancla_semana (org_id, tipo, anio, semana, fijada_por)
select :org_id, c.tipo, c.anio, c.semana, :'ctrl_id'
from calendario c
where c.org_id = :org_id
  and c.anio = extract(year from current_date)::smallint
  and current_date between c.fecha_inicio and c.fecha_fin;

-- Obras ya existentes, una por workflow, para que cada E2E sea independiente.
-- La del workflow A NO se siembra: se da de alta por la UI.
insert into obra (org_id, cluster_id, prototipo_id, clave, residente_id)
select :org_id, :'cluster_id', :'proto_id', clave, :'res_id'
from (values ('OBRA-C'), ('OBRA-D'), ('OBRA-E'), ('OBRA-F'), ('OBRA-G')) v(clave);

-- Dos actividades por obra, con cantidad programada (sin ejecución: el avance
-- lo capturan las pruebas, que es lo que se está probando).
insert into actividad
  (org_id, obra_id, concepto_id, descripcion, cant_base, cant_programada,
   precio_unitario, precio_destajo, modo_pago, duracion_dias, nivel_id, etapa_id)
select :org_id, o.id, c.id, c.descripcion, 10, 10,
       p.precio_unitario, p.precio_destajo, 'destajo', 2, :'nivel_id', :'etapa_id'
from obra o
cross join (select id, descripcion from concepto
            where org_id = :org_id and clave in ('E2E-EXC', 'E2E-PLA')) c
join cpu p on p.concepto_id = c.id and p.vigente
where o.org_id = :org_id;

commit;

select 'semilla e2e lista: ' || count(*) || ' actividades en ' ||
       (select count(*) from obra where org_id = :org_id) || ' obras'
from actividad where org_id = :org_id;
