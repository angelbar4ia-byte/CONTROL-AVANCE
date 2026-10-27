-- ============================================================
-- ObraCtrl · 0068 · Las dos bitácoras nuevas solo se agregan
--
-- QUÉ FALTABA
--
-- `comprobacion_excedente` (0066) y `programa_edicion` (0067) son rastro de
-- decisiones: quién autorizó trabajo de más, quién editó el programa. Una
-- bitácora que su propio sujeto puede reescribir no prueba nada.
--
-- Las dos migraciones lo intentaron y no lo lograron, por dos razones que la
-- prueba de aislamiento (`test_rls_programa_y_comprobacion.sql`) sacó a la luz:
--
--   · `comprobacion_excedente` quedó con una política `for all`: quien ve la
--     obra podía actualizar y borrar sus decisiones.
--   · el `grant select, insert` de las dos no recortó nada: la migración 0014
--     deja `alter default privileges` que otorga todo a `authenticated` y
--     `obractrl_api` sobre cualquier tabla nueva. Un grant más estrecho encima
--     de un default ancho no lo estrecha; hay que **revocar**.
--
-- Qué se hace: la política de la comprobación se parte en lectura y alta (como
-- la de `programa_edicion`) y se revoca UPDATE/DELETE/TRUNCATE a los dos roles
-- de la aplicación en las dos tablas. Defensa en dos capas: sin política y sin
-- privilegio.
-- ============================================================

drop policy comprobacion_excedente_scope on comprobacion_excedente;

create policy comprobacion_excedente_lectura on comprobacion_excedente
  for select
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from actividad a
       where a.id = actividad_id and app.obra_visible(a.obra_id)
    )
  );

create policy comprobacion_excedente_alta on comprobacion_excedente
  for insert
  with check (
    org_id = app.current_org_id()
    and exists (
      select 1 from actividad a
       where a.id = actividad_id and app.obra_visible(a.obra_id)
    )
  );

revoke update, delete, truncate on comprobacion_excedente from authenticated, obractrl_api;
revoke update, delete, truncate on programa_edicion from authenticated, obractrl_api;
