-- ============================================================
-- ObraCtrl · 0119 · De dónde viene la cantidad medida de una matriz (D-639)
--
-- La cantidad medida de una matriz interna sale de sus trazos (`origen = 'trazos'`) o de lo que un concepto **toma**
-- de un elemento paramétrico colocado en el plano (`origen = 'elemento'`, D-630): la toma escribe la cantidad medida.
-- Lo trazado directo sobre la matriz manda sobre lo tomado (D-584 regla 2): al medirla con trazos pasa a `trazos`.
-- ============================================================

alter table actividad_matriz
  add column origen text not null default 'trazos',
  add constraint ck_actividad_matriz_origen check (origen in ('trazos', 'elemento'));

comment on column actividad_matriz.origen is
  'De dónde viene la cantidad medida: sus trazos, o lo que toma de un elemento paramétrico colocado (0119, D-639).';
