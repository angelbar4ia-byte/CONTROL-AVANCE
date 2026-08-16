-- ============================================================
-- ObraCtrl · Semilla de demo — organización + usuario Control
-- Spec §4 (roles) · §12.4 (auth) · §11.3 workflow C
--
-- Crea una organización de prueba, vincula un usuario `control_obra` a una
-- cuenta de Supabase Auth ya existente, y siembra un proyecto con dos obras
-- y unas cuantas actividades/solicitudes de cierre en distintos estatus —
-- lo suficiente para que la bandeja de Cierres (`/cierres`, web) tenga algo
-- real que revisar al entrar como Control.
--
-- Prerrequisito: el usuario de Supabase Auth YA debe existir (Dashboard →
-- Authentication → Users → Add user, o `supabase auth admin create-user`).
-- Este script NO crea la cuenta de Auth —eso vive fuera de Postgres—, solo
-- la vincula a un `usuario` de ObraCtrl vía `auth_user_id`.
--
-- Uso:
--   psql "$DATABASE_URL" \
--     -v auth_user_id="'<uuid del usuario en Supabase Auth>'" \
--     -v control_email="'control.demo@obractrl.mx'" \
--     -f 02_demo_control.sql
--
-- Reejecutable: los catálogos/dimensión usan upsert por clave; las
-- actividades y cierres de ejemplo se omiten si ya existen (ver el \if).
-- ============================================================

\set ON_ERROR_STOP on

-- `auth_user_id` y `control_email` se pasan YA entrecomillados por línea de
-- comandos (ver el bloque "Uso" arriba) — mismo convenio que `org_id` en
-- `01_semilla_canonica.sql`: el valor de la variable psql ya trae las
-- comillas SQL, así que abajo se usan como `:auth_user_id` (sin comillas de
-- psql), nunca como `:'auth_user_id'` (eso las duplicaría).
\if :{?auth_user_id}
\else
  \echo 'Falta -v auth_user_id="''<uuid>''" — crea primero el usuario en Supabase Auth (Dashboard).'
  \quit
\endif

\if :{?control_email}
\else
  \echo 'Falta -v control_email="''control.demo@obractrl.mx''" (usa el mismo correo que diste de alta en Supabase Auth).'
  \quit
\endif

begin;

-- ------------------------------------------------------------
-- Organización + usuarios
-- ------------------------------------------------------------
insert into organizacion (nombre, slug)
values ('ObraCtrl Demo', 'obractrl-demo')
on conflict (slug) do update set nombre = excluded.nombre
returning id as org_id \gset

insert into usuario (org_id, auth_user_id, nombre, email, rol)
values (:'org_id', :auth_user_id, 'Control Demo', :control_email, 'control_obra')
on conflict (org_id, email) do update
  set auth_user_id = excluded.auth_user_id,
      rol           = excluded.rol,
      nombre        = excluded.nombre
returning id as control_id \gset

-- Residente/Supervisor de utilería: no inician sesión (sin auth_user_id),
-- solo dan contexto realista a las obras y solicitudes de ejemplo.
insert into usuario (org_id, nombre, email, rol)
values (:'org_id', 'Residente Demo', 'residente.demo@obractrl.mx', 'residente')
on conflict (org_id, email) do update set nombre = excluded.nombre
returning id as residente_id \gset

insert into usuario (org_id, nombre, email, rol)
values (:'org_id', 'Supervisor Demo', 'supervisor.demo@obractrl.mx', 'supervisor')
on conflict (org_id, email) do update set nombre = excluded.nombre
returning id as supervisor_id \gset

-- ------------------------------------------------------------
-- Proyecto · Cluster · Prototipo · Obras
-- ------------------------------------------------------------
insert into proyecto (org_id, clave, nombre, ubicacion)
values (:'org_id', 'DEMO', 'Fraccionamiento Demo', 'Querétaro, Qro.')
on conflict (org_id, clave) do update set nombre = excluded.nombre
returning id as proyecto_id \gset

insert into cluster (org_id, proyecto_id, clave, nombre)
values (:'org_id', :'proyecto_id', 'FRESNO', 'Cluster Fresno')
on conflict (org_id, proyecto_id, clave) do update set nombre = excluded.nombre
returning id as cluster_id \gset

insert into prototipo (org_id, proyecto_id, clave, nombre, m2, niveles, recamaras)
values (:'org_id', :'proyecto_id', 'CAS-1', 'Prototipo Cedro', 95.5, 2, 3)
on conflict (org_id, clave) do update set nombre = excluded.nombre
returning id as prototipo_id \gset

-- Puentes de alcance (§4): sin esto, RLS no deja ver nada aunque el JWT
-- traiga el rol correcto — `app.obra_visible()` exige la fila (0011).
insert into control_proyecto (org_id, usuario_id, proyecto_id)
values (:'org_id', :'control_id', :'proyecto_id')
on conflict (usuario_id, proyecto_id) do nothing;

insert into supervisor_cluster (org_id, supervisor_id, cluster_id)
values (:'org_id', :'supervisor_id', :'cluster_id')
on conflict (supervisor_id, cluster_id) do nothing;

insert into obra (org_id, cluster_id, prototipo_id, clave, residente_id, estatus, avance_pct)
values (:'org_id', :'cluster_id', :'prototipo_id', 'FRESNO 01', :'residente_id', 'en_proceso', 62.5)
on conflict (org_id, clave) do update set avance_pct = excluded.avance_pct
returning id as obra1_id \gset

insert into obra (org_id, cluster_id, prototipo_id, clave, residente_id, estatus, avance_pct)
values (:'org_id', :'cluster_id', :'prototipo_id', 'FRESNO 02', :'residente_id', 'iniciada', 18.0)
on conflict (org_id, clave) do update set avance_pct = excluded.avance_pct
returning id as obra2_id \gset

-- ------------------------------------------------------------
-- Actividades + solicitudes de cierre de ejemplo (reejecutable: se omite
-- si FRESNO 01 ya tiene actividades cargadas).
-- ------------------------------------------------------------
select exists(select 1 from actividad where obra_id = :'obra1_id') as ya_sembrado \gset

\if :ya_sembrado
\echo 'FRESNO 01 ya tiene actividades — se omite la carga de ejemplo (rerun seguro).'
\else

-- 1) Ya validada: Control ve el flujo completo (solicitada->autorizada->validada).
insert into actividad
    (org_id, obra_id, descripcion, cant_base, cant_programada, cant_ejecutada,
     precio_unitario, precio_destajo, modo_pago, estatus)
values
    (:'org_id', :'obra1_id', 'Cimentación - zapatas', 100, 100, 95,
     500, 150, 'destajo', 'concluida')
returning id as act1_id \gset

insert into solicitud_cierre
    (org_id, actividad_id, solicitada_por, autorizada_por, validada_por,
     cantidad, monto, checklist, adjuntos, estatus, fecha_autoriza, fecha_valida)
values
    (:'org_id', :'act1_id', :'residente_id', :'supervisor_id', :'control_id',
     95, 14250, '[{"item":"Nivelación","ok":true}]'::jsonb,
     '["r2://demo/zapatas-1.jpg"]'::jsonb, 'validada', now(), now());

-- 2) Autorizada, pendiente de que Control la valide — la fila que se
--    espera que el usuario Control accione al entrar a /cierres.
insert into actividad
    (org_id, obra_id, descripcion, cant_base, cant_programada, cant_ejecutada,
     precio_unitario, precio_destajo, modo_pago, estatus)
values
    (:'org_id', :'obra1_id', 'Estructura - castillos y cadenas', 50, 50, 30,
     650, 180, 'destajo', 'pendiente_cierre')
returning id as act2_id \gset

insert into solicitud_cierre
    (org_id, actividad_id, solicitada_por, autorizada_por,
     cantidad, monto, checklist, adjuntos, estatus, fecha_autoriza)
values
    (:'org_id', :'act2_id', :'residente_id', :'supervisor_id',
     30, 5400, '[{"item":"Verticalidad","ok":true}]'::jsonb,
     '["r2://demo/castillos-1.jpg"]'::jsonb, 'autorizada', now());

-- 3) Recién solicitada — todavía le toca al Supervisor, Control solo la ve.
insert into actividad
    (org_id, obra_id, descripcion, cant_base, cant_programada, cant_ejecutada,
     precio_unitario, precio_destajo, modo_pago, estatus)
values
    (:'org_id', :'obra1_id', 'Acabados - aplanado interior', 80, 80, 80,
     420, 130, 'destajo', 'pendiente_cierre')
returning id as act3_id \gset

insert into solicitud_cierre
    (org_id, actividad_id, solicitada_por, cantidad, monto, checklist, adjuntos, estatus)
values
    (:'org_id', :'act3_id', :'residente_id', 80, 10400,
     '[{"item":"Espesor uniforme","ok":true}]'::jsonb,
     '["r2://demo/aplanado-1.jpg"]'::jsonb, 'solicitada');

-- 4) En proceso, sin cierre todavía — solo avance simple (§6, auto-estatus).
insert into actividad
    (org_id, obra_id, descripcion, cant_base, cant_programada, cant_ejecutada,
     precio_unitario, precio_destajo, modo_pago)
values
    (:'org_id', :'obra2_id', 'Preliminares - trazo y nivelación', 20, 20, 18,
     300, 300, 'concepto')
returning id as act4_id \gset

-- ------------------------------------------------------------
-- Línea base en la bitácora (D5 · migración 0017).
--
-- `registro_avance` es la ÚNICA fuente de `cant_ejecutada`: el trigger
-- `app.registro_avance_agregar` la deriva de la suma de sus deltas. Una
-- actividad sembrada con avance pero sin bitácora quedaría inconsistente, y
-- la primera captura del móvil la reduciría a solo ese delta. Por eso cada
-- actividad de demo estrena su registro de línea base.
-- ------------------------------------------------------------
insert into registro_avance
    (org_id, actividad_id, fecha, delta_ejecutado, usuario_id, comentario)
values
    (:'org_id', :'act1_id', current_date, 95, :'residente_id', 'Línea base de demo'),
    (:'org_id', :'act2_id', current_date, 30, :'residente_id', 'Línea base de demo'),
    (:'org_id', :'act3_id', current_date, 80, :'residente_id', 'Línea base de demo'),
    (:'org_id', :'act4_id', current_date, 18, :'residente_id', 'Línea base de demo');

\endif

commit;

\echo ''
\echo '--- Listo ---'
\echo 'Usuario Control demo vinculado. Inicia sesión en la web con el correo'
\echo 'y contraseña que le diste en Supabase Auth Dashboard.'
