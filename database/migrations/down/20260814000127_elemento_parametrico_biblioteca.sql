drop index if exists ix_elemento_parametrico_categoria;
drop index if exists ux_elemento_parametrico_firma;
drop function if exists app.firma_elemento(text, text, text, jsonb);
alter table elemento_parametrico
  drop constraint if exists ck_elemento_parametrico_subcategoria,
  drop constraint if exists ck_elemento_parametrico_categoria,
  drop column if exists firma,
  drop column if exists subcategoria,
  drop column if exists categoria;
