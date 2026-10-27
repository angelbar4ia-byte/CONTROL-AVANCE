-- Revierte 0087: quita la pendiente de las líneas, las clases de anotación y la vista del plano.

alter table plano
  drop constraint ck_plano_rotacion,
  drop column volteo_vertical,
  drop column volteo_horizontal,
  drop column rotacion_grados;

alter table nota_plano
  drop constraint ck_nota_plano_destino,
  drop constraint ck_nota_plano_tipo,
  drop column destino,
  drop column tipo;

alter table trazo
  drop constraint ck_trazo_pendiente_en_linea,
  drop constraint ck_trazo_pendiente_positiva,
  drop column pendiente_pct;
