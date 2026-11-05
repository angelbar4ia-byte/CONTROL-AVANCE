alter table vano
  drop constraint if exists ck_vano_bisagra,
  drop constraint if exists ck_vano_lado_hoja,
  drop constraint if exists ck_vano_apertura,
  drop column if exists bisagra,
  drop column if exists lado_hoja,
  drop column if exists apertura_grados;
