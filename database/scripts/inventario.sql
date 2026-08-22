-- ============================================================
-- ¿Qué tiene de verdad esta base? (§12.12)
--
-- La bitácora `app.schema_migrations` dice qué **cree** el runner que está
-- aplicado. Esto dice qué **existe**. Normalmente coinciden; cuando no, es
-- porque alguien aplicó SQL a mano en el editor de Supabase o porque se corrió
-- `migrar.sh --sellar` sobre una base que no tenía todo.
--
-- Sellar marca una migración como aplicada **sin correrla**: sirve para una
-- base que ya tiene el esquema y le falta la bitácora, y deja rota —y
-- convencida de estar al día— a una base incompleta. De ahí este inventario.
--
-- CÓMO SE LEE
--
--   aplicada | existe | qué significa
--   ---------+--------+---------------------------------------------------
--   sí       | sí     | correcto, no hay nada que hacer
--   sí       | NO     | **sellada de más**: borra su renglón y vuelve a migrar
--   no       | sí     | aplicada a mano: séllala para que el runner lo sepa
--   no       | NO     | pendiente normal: `./scripts/migrar.sh` la aplica
--
-- Cada renglón mira **un objeto testigo** de su migración: el más específico
-- que crea. No prueba que la migración esté completa —un `alter` a medias no
-- se ve desde aquí— pero sí distingue "corrió" de "no corrió", que es la
-- pregunta que desatasca.
--
-- Uso:
--   psql "$DATABASE_URL" -f scripts/inventario.sql
--   …o pegarlo en el editor SQL de Supabase.
-- ============================================================

with testigos(version, objeto, existe) as (
  values
    ('20260814000001_extensiones_y_esquema',      'app.touch_updated_at()',            to_regprocedure('app.touch_updated_at()') is not null),
    ('20260814000002_enums_canonicos',            'tipo rol_usuario',                  to_regtype('rol_usuario') is not null),
    ('20260814000003_identidad_y_configuracion',  'organizacion',                      to_regclass('public.organizacion') is not null),
    ('20260814000004_proyecto_y_obra',            'proyecto',                          to_regclass('public.proyecto') is not null),
    ('20260814000005_catalogos_y_apu',            'unidad',                            to_regclass('public.unidad') is not null),
    ('20260814000006_presupuesto_y_programacion', 'prototipo_nodo',                    to_regclass('public.prototipo_nodo') is not null),
    ('20260814000007_ejecucion_y_avance',         'actividad',                         to_regclass('public.actividad') is not null),
    ('20260814000008_materiales_y_almacen',       'motivo_almacen',                    to_regclass('public.motivo_almacen') is not null),
    ('20260814000009_control_y_flujos',           'incidencia',                        to_regclass('public.incidencia') is not null),
    ('20260814000010_soporte_y_cargas',           'expediente_doc',                    to_regclass('public.expediente_doc') is not null),
    ('20260814000011_rls_helpers',                'app.obra_visible()',                to_regprocedure('app.obra_visible(uuid)') is not null),
    ('20260814000012_rls_policies',               'política obra_select',              exists (select 1 from pg_policies where tablename = 'obra' and policyname = 'obra_select')),
    ('20260814000013_calendario_generador',       'app.generar_calendario()',          exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'app' and p.proname = 'generar_calendario')),
    ('20260814000014_roles_y_grants',             'rol obractrl_api',                  exists (select 1 from pg_roles where rolname = 'obractrl_api')),
    ('20260814000015_auth_hook',                  'custom_access_token_hook()',        exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public' and p.proname = 'custom_access_token_hook')),
    ('20260814000016_autoasignacion_control',     'app.asignar_proyecto_a_su_creador', exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'app' and p.proname = 'asignar_proyecto_a_su_creador')),
    ('20260814000017_agregacion_registro_avance', 'app.registro_avance_agregar',       exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'app' and p.proname = 'registro_avance_agregar')),
    ('20260814000018_actividad_prototipo_nodo',   'actividad.prototipo_nodo_id',       exists (select 1 from information_schema.columns where table_name = 'actividad' and column_name = 'prototipo_nodo_id')),
    ('20260814000019_carga_de_almacen',           'carga_snapshot.orden',              exists (select 1 from information_schema.columns where table_name = 'carga_snapshot' and column_name = 'orden')),
    ('20260814000020_periodo_bloqueado',          'periodo_bloqueado',                 to_regclass('public.periodo_bloqueado') is not null),
    ('20260814000021_registro_avance_obra',       'registro_avance.obra_id',           exists (select 1 from information_schema.columns where table_name = 'registro_avance' and column_name = 'obra_id')),
    ('20260814000022_idempotencia',               'idempotencia',                      to_regclass('public.idempotencia') is not null),
    ('20260814000023_bitacora_de_negocio',        'app.bitacora_registrar',            exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'app' and p.proname = 'bitacora_registrar')),
    ('20260814000024_registro_de_respaldos',      'app.respaldo',                      to_regclass('app.respaldo') is not null),
    ('20260814000025_guardia_de_privilegios',     'usuario.debe_cambiar_password',     exists (select 1 from information_schema.columns where table_name = 'usuario' and column_name = 'debe_cambiar_password')),
    ('20260814000026_actividad_extra_catalogo',   'actividad.orden_cambio',            exists (select 1 from information_schema.columns where table_name = 'actividad' and column_name = 'orden_cambio')),
    ('20260814000027_orden_de_eventos',           'incidencia_evento.orden',           exists (select 1 from information_schema.columns where table_name = 'incidencia_evento' and column_name = 'orden')),
    ('20260814000028_dispositivo_push',           'dispositivo_push',                  to_regclass('public.dispositivo_push') is not null)
)
select
  t.version,
  t.objeto,
  case when b.version is null then 'no' else (case when b.sellada then 'sí (sellada)' else 'sí' end) end as aplicada,
  case when t.existe then 'sí' else 'NO' end                                                            as existe,
  case
    when b.version is not null and not t.existe then '<<< SELLADA DE MÁS: borra su renglón y vuelve a migrar'
    when b.version is null     and     t.existe then 'aplicada a mano: séllala'
    when b.version is null     and not t.existe then 'pendiente'
    else ''
  end                                                                                                    as accion
from testigos t
left join app.schema_migrations b on b.version = t.version
order by t.version;
