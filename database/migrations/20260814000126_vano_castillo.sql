-- ============================================================
-- ObraCtrl · 0126 · Castillos de un muro con cadena (paramétrico de muro, F-22, tanda 3)
--
-- En un muro «con cadena» los castillos ya se conocen y se colocan; restan de los m² del muro de ladrillo. Un castillo se
-- descuenta igual que una puerta o un paso: su ancho × la altura del muro × las caras que cuenta el muro, y su ancho del largo
-- (parte del piso). Por eso es un tipo más de vano. Solo se coloca sobre un muro con cadena y toma la altura del muro.
-- ============================================================

alter table vano drop constraint if exists ck_vano_tipo;
alter table vano
  add constraint ck_vano_tipo check (tipo in ('puerta', 'ventana', 'cancel', 'arco', 'paso', 'castillo'));

alter table vano_version drop constraint if exists ck_vano_version_tipo;
alter table vano_version
  add constraint ck_vano_version_tipo check (tipo in ('puerta', 'ventana', 'cancel', 'arco', 'paso', 'castillo'));

-- Las organizaciones que ya tienen catálogo de vanos reciben su primera versión de castillo (K-01, 0.15 m de ancho).
insert into vano_version (org_id, tipo, clave, ancho_m, alto_m, antepecho_m)
select distinct org_id, 'castillo', 'K-01', 0.15, 2.6, 0 from vano_version
on conflict do nothing;
