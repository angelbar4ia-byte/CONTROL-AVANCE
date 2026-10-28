-- ============================================================
-- ObraCtrl · 0090 · Costos da de alta conceptos y matrices, y publica el CPU
-- Cerebro WORKFLOWS.md §8.9 (D-589, D-590): crear conceptos y poner matrices desde el cuantificador
-- es de Control de obra **y de Costos**.
--
-- Hasta aquí el catálogo era de `es_config()` (Control de obra y Super intendente) y Costos solo lo
-- leía. Costos recibe lo mínimo de esa escritura, con políticas aditivas (no se toca ninguna):
--   · `concepto`: **alta** (no cambia ni borra los que ya hay);
--   · `explosion`: solo la composición **viva** (sin versión de CPU) cuyo hijo es un concepto, o sea
--     las matrices que se agregan y se quitan; nunca los insumos ni las filas de una versión;
--   · `cpu`: publicar una versión nueva y retirar la vigente (alta y cambio de la marca `vigente`);
--     no borra versiones.
-- Unidades, familias, insumos y el resto del catálogo siguen siendo de quien configura.
-- ============================================================

create policy concepto_costos_alta on concepto
  for insert
  with check (org_id = app.current_org_id() and app.current_rol() = 'costos');

create policy explosion_costos_matrices on explosion
  for all
  using (
    org_id = app.current_org_id() and app.current_rol() = 'costos'
    and cpu_id is null and tipo_hijo = 'concepto'
  )
  with check (
    org_id = app.current_org_id() and app.current_rol() = 'costos'
    and cpu_id is null and tipo_hijo = 'concepto'
  );

create policy cpu_costos_alta on cpu
  for insert
  with check (org_id = app.current_org_id() and app.current_rol() = 'costos');
create policy cpu_costos_vigencia on cpu
  for update
  using      (org_id = app.current_org_id() and app.current_rol() = 'costos')
  with check (org_id = app.current_org_id() and app.current_rol() = 'costos');
