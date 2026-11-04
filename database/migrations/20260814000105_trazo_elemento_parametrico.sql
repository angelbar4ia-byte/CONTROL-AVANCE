-- ============================================================
-- ObraCtrl · 0105 · Un trazo es un elemento paramétrico (D-602, D-604)
--
-- Un trazo se marca con un elemento paramétrico del catálogo: un Punto es una pieza (castillo, zapata), una Línea
-- son sus metros (trabe, cadena) y un Área son sus m² (losa). El plano suma lo que llevan: la receta de una muestra
-- × lo que aporta cada trazo. `lados_cimbra` fija a mano los lados de cimbra de esa pieza (un castillo aislado lleva
-- 4, junto a un vano 3, en un muro continuo 2); sin fijar se usa el que dice el elemento.
-- ============================================================

alter table trazo
  add column elemento_parametrico_id uuid references elemento_parametrico(id) on delete set null,
  add column lados_cimbra smallint,
  add constraint ck_trazo_lados_cimbra check (lados_cimbra is null or lados_cimbra between 1 and 4);

create index ix_trazo_elemento_parametrico on trazo (org_id, plano_id, elemento_parametrico_id)
  where elemento_parametrico_id is not null;

comment on column trazo.elemento_parametrico_id is 'El elemento paramétrico que es este trazo (pieza, metros o m²); el plano suma su receta (0105).';
comment on column trazo.lados_cimbra is 'Lados de cimbra fijados a mano para esta pieza; null = el que dice el elemento (0105).';
