-- ============================================================
-- ObraCtrl · 0093 · Costos arma el árbol: niveles, etapas y la unidad de un concepto
-- Cerebro WORKFLOWS.md §8.9 (D-597): desde el cuantificador se arma el árbol (nivel → etapa → partida) y
-- se cambia la unidad de un concepto. Es de Control de obra **y de Costos**.
--
-- `es_config()` (Control de obra y Super intendente) gobierna el catálogo y Costos solo lo leía. Costos
-- recibe lo mínimo, con políticas aditivas (no se toca ninguna):
--   · `nivel` y `etapa_constructiva`: alta y cambio (no borra);
--   · `concepto`: cambio (la API solo lo usa para la unidad; una política no distingue columnas, así
--     que el límite vive en el caso de uso y en su prueba).
-- ============================================================

create policy nivel_costos_alta on nivel
  for insert with check (org_id = app.current_org_id() and app.current_rol() = 'costos');
create policy nivel_costos_cambio on nivel
  for update
  using      (org_id = app.current_org_id() and app.current_rol() = 'costos')
  with check (org_id = app.current_org_id() and app.current_rol() = 'costos');

create policy etapa_costos_alta on etapa_constructiva
  for insert with check (org_id = app.current_org_id() and app.current_rol() = 'costos');
create policy etapa_costos_cambio on etapa_constructiva
  for update
  using      (org_id = app.current_org_id() and app.current_rol() = 'costos')
  with check (org_id = app.current_org_id() and app.current_rol() = 'costos');

create policy concepto_costos_cambio on concepto
  for update
  using      (org_id = app.current_org_id() and app.current_rol() = 'costos')
  with check (org_id = app.current_org_id() and app.current_rol() = 'costos');
