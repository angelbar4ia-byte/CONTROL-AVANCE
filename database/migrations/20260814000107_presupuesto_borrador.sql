-- ============================================================
-- ObraCtrl · 0107 · Árbol propio de la obra: el presupuesto puede estar en borrador (D-624)
--
-- Una obra en diseño puede tener un árbol propio (un prototipo de un solo uso, clonado del prototipo base).
-- Al primer cambio de ese árbol nace una versión del presupuesto en **borrador**: va juntando los cambios;
-- Control de obra o Costos la **confirma** (queda fija, ya no se edita) y después la **fija como activa**
-- (`vigente`). Una versión confirmada se conserva y se puede volver a fijar como activa.
-- ============================================================

alter table presupuesto
  add column estado text not null default 'confirmada',
  add column nota text,
  add constraint ck_presupuesto_estado check (estado in ('borrador', 'confirmada'));

-- Un solo borrador por prototipo: los cambios se juntan en él.
create unique index uq_presupuesto_borrador on presupuesto (org_id, prototipo_id) where estado = 'borrador';

comment on column presupuesto.estado is
  'borrador: junta los cambios del árbol propio de una obra y aún se edita; confirmada: fija (0107, D-624).';
comment on column presupuesto.nota is 'Lo que dice quien confirma la versión («se agregó la cocina») (0107).';
