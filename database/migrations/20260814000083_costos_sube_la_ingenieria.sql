-- ============================================================
-- ObraCtrl · 0083 · Costos también sube la ingeniería
-- Cerebro WORKFLOWS.md §8.9 (D-575, D-581): la ingeniería la prepara Costos; ahora también la carga.
--
-- Hasta aquí las cargas eran de `es_config()` (Control de obra y Super intendente). Costos puede subir
-- **solo ingeniería del lote**, y lo mínimo que eso toca:
--   · `carga_datos` (el lote), `carga_snapshot` (para revertirlo) y `pendiente` (lo que queda por
--     decidir), siempre que la carga sea de tipo `ingenieria_lote`;
--   · `prototipo` y `prototipo_nodo`, **solo los de un solo uso** (`de_una_obra`): el camino «el más
--     parecido» (diseño nuevo) clona la estructura en un prototipo exclusivo de la obra. Los
--     prototipos compartidos, y cualquier otra carga, siguen siendo de quien configura.
-- Son políticas aditivas: no se toca ninguna de las existentes.
-- ============================================================

create policy carga_datos_costos on carga_datos
  for all
  using      (org_id = app.current_org_id() and app.current_rol() = 'costos' and tipo = 'ingenieria_lote')
  with check (org_id = app.current_org_id() and app.current_rol() = 'costos' and tipo = 'ingenieria_lote');

create policy carga_snapshot_costos on carga_snapshot
  for all
  using (
    org_id = app.current_org_id() and app.current_rol() = 'costos'
    and exists (select 1 from carga_datos c where c.id = carga_id and c.tipo = 'ingenieria_lote')
  )
  with check (
    org_id = app.current_org_id() and app.current_rol() = 'costos'
    and exists (select 1 from carga_datos c where c.id = carga_id and c.tipo = 'ingenieria_lote')
  );

create policy pendiente_costos on pendiente
  for all
  using (
    org_id = app.current_org_id() and app.current_rol() = 'costos'
    and exists (select 1 from carga_datos c where c.id = carga_id and c.tipo = 'ingenieria_lote')
  )
  with check (
    org_id = app.current_org_id() and app.current_rol() = 'costos'
    and exists (select 1 from carga_datos c where c.id = carga_id and c.tipo = 'ingenieria_lote')
  );

create policy prototipo_costos_alta on prototipo
  for insert
  with check (org_id = app.current_org_id() and app.current_rol() = 'costos' and de_una_obra);
create policy prototipo_costos_cambio on prototipo
  for update
  using      (org_id = app.current_org_id() and app.current_rol() = 'costos' and de_una_obra)
  with check (org_id = app.current_org_id() and app.current_rol() = 'costos' and de_una_obra);

create policy prototipo_nodo_costos on prototipo_nodo
  for all
  using (
    org_id = app.current_org_id() and app.current_rol() = 'costos'
    and exists (select 1 from prototipo p where p.id = prototipo_id and p.de_una_obra)
  )
  with check (
    org_id = app.current_org_id() and app.current_rol() = 'costos'
    and exists (select 1 from prototipo p where p.id = prototipo_id and p.de_una_obra)
  );
