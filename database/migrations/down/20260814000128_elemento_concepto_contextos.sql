-- Lo que no existía antes de la 0128 no cabe en el modelo anterior: los conceptos propuestos (sin concepto del catálogo) y los
-- que se pagan por contexto o escalón se borran; los generales vuelven a ser uno por (elemento, concepto).
delete from elemento_concepto
 where concepto_id is null or nivel_min is not null or nivel_max is not null or ubicacion is not null or alto_hasta_m is not null;
drop index if exists ux_elemento_concepto_propuesto;
drop index if exists ux_elemento_concepto_catalogo;
alter table elemento_concepto
  drop constraint if exists ck_elemento_concepto_propuesto,
  drop constraint if exists ck_elemento_concepto_contexto,
  drop constraint if exists ck_elemento_concepto_estado,
  drop column if exists ranura,
  drop column if exists descripcion,
  drop column if exists clave_propuesta,
  drop column if exists estado,
  drop column if exists alto_hasta_m,
  drop column if exists ubicacion,
  drop column if exists nivel_max,
  drop column if exists nivel_min;
alter table elemento_concepto alter column concepto_id set not null;
alter table elemento_concepto add constraint uq_elemento_concepto unique (elemento_id, concepto_id);
