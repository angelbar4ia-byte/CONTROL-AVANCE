-- ============================================================
-- ObraCtrl · Semilla del diccionario canónico
-- Spec §8.3 (frentes) · §8.4 (unidades) · §3.5 (IVA) · §10.5 (motivos)
--
-- SEMILLA EDITABLE (§8.7): el código siembra el valor por defecto,
-- pero la lista viva vive aquí en BD y el usuario la extiende desde
-- Configuración, sin tocar código.
--
-- Uso:  psql "$DATABASE_URL" -v org_id="'<uuid>'" -f 01_semilla_canonica.sql
-- ============================================================

\set ON_ERROR_STOP on

begin;

-- ------------------------------------------------------------
-- §8.4 · Unidades canónicas (con sinónimos para los cargadores §8.6)
-- ------------------------------------------------------------
insert into unidad (org_id, clave, nombre, sinonimos) values
  (:org_id, 'm2',     'Metro cuadrado', array['M2','mt2','m²','MTS2']),
  (:org_id, 'm3',     'Metro cúbico',   array['M3','mt3','m³','MTS3']),
  (:org_id, 'ml',     'Metro lineal',   array['ML','mts','m.l.','METRO']),
  (:org_id, 'pza',    'Pieza',          array['PZ','PZA','PIEZA','pz']),
  (:org_id, 'kg',     'Kilogramo',      array['KG','kgs','KILO']),
  (:org_id, 'ton',    'Tonelada',       array['TON','tons','TONELADA']),
  (:org_id, 'lote',   'Lote',           array['LOTE','LT']),
  (:org_id, 'jornal', 'Jornal',         array['JOR','JORNAL','JOR.']),
  (:org_id, 'global', 'Global',         array['GLB','GLOBAL','LOT']),
  (:org_id, 'viaje',  'Viaje',          array['VJE','VIAJE']),
  (:org_id, '%',      'Porcentaje',     array['PCT','PORC','%'])
on conflict (org_id, clave) do nothing;

-- ------------------------------------------------------------
-- §8.3 · Frentes canónicos
-- ------------------------------------------------------------
insert into frente (org_id, clave, nombre, orden, color) values
  (:org_id, 'PRE', 'Preliminares',     1, 'var(--c-text-mute)'),
  (:org_id, 'CIM', 'Cimentación',      2, 'var(--c-accent)'),
  (:org_id, 'EST', 'Estructura',       3, 'var(--c-info)'),
  (:org_id, 'ALB', 'Albañilería',      4, 'var(--c-warn)'),
  (:org_id, 'HID', 'Hidrosanitaria',   5, 'var(--c-info)'),
  (:org_id, 'ELE', 'Eléctrica',        6, 'var(--c-warn)'),
  (:org_id, 'ACA', 'Acabados',         7, 'var(--c-ok)'),
  (:org_id, 'HER', 'Herrería / carpintería', 8, 'var(--c-text-soft)')
on conflict (org_id, clave) do nothing;

-- ------------------------------------------------------------
-- §3.5 · Familias base. El IVA sale de la familia; Pétreos y
-- Jardinería nacen exentas y se pueden sobreescribir por material.
-- ------------------------------------------------------------
insert into familia (org_id, clave, nombre, aplica_a, iva_aplica) values
  (:org_id, 'FAM-CEM', 'Cementantes',        'material', true),
  (:org_id, 'FAM-ACE', 'Acero',              'material', true),
  (:org_id, 'FAM-PET', 'Pétreos',            'material', false),
  (:org_id, 'FAM-JAR', 'Jardinería',         'material', false),
  (:org_id, 'FAM-INS', 'Instalaciones',      'material', true),
  (:org_id, 'FAM-ACA', 'Acabados',           'material', true),
  (:org_id, 'FAM-MAD', 'Madera y cimbra',    'material', true),
  (:org_id, 'FAM-VAR', 'Varios',             'material', true),
  (:org_id, 'FAM-C-OBRA', 'Conceptos de obra', 'concepto', true)
on conflict (org_id, clave) do nothing;

-- ------------------------------------------------------------
-- §10.5 · Motivos de almacén con su signo y bucket de KPI
-- ------------------------------------------------------------
insert into motivo_almacen (org_id, clave, descripcion, signo, bucket) values
  (:org_id, 'REC', 'Recepción de material',        1, 'ingresos'),
  (:org_id, 'INI', 'Inventario inicial',           1, 'importe_total'),
  (:org_id, 'SOB', 'Sobrantes',                    1, 'ajustes'),
  (:org_id, 'SAL', 'Salida para producción',      -1, 'salidas'),
  (:org_id, 'IMP', 'Implosión de materiales',     -1, 'salidas'),
  (:org_id, 'CON', 'Consumos internos',           -1, 'importe_total'),
  (:org_id, 'DEV', 'Devolución cliente',          -1, 'importe_total'),
  (:org_id, 'FAL', 'Faltantes',                   -1, 'ajustes'),
  (:org_id, 'AJU', 'Ajuste de inventario',        -1, 'ajustes')
on conflict (org_id, clave) do nothing;

-- ------------------------------------------------------------
-- §3.5, §3.6 · Configurables. El código solo trae el default;
-- en runtime SIEMPRE se lee de aquí primero (§8.7 caveat).
-- ------------------------------------------------------------
-- NOTA: el tope de sobre-programación (1.2) y el umbral de "casi" (90%) del
-- §6 NO están aquí a propósito. El §6 los escribe como fórmula fija, no como
-- parámetro de §8.7, y un CHECK de Postgres no puede leer esta tabla (no
-- admite subconsultas) — así que si fueran "configurables" solo de palabra,
-- la BD (última frontera en la ruta offline, §12.5) y la app divergirían en
-- silencio para cualquier org que los cambiara. Quedan fijos en ambos lados:
-- `ck_actividad_programada_vs_base` / `app.actividad_recalcular` (BD) y
-- `TOPE_SOBREPROGRAMA` / `UMBRAL_CASI_PCT` (dominio).
insert into configuracion (org_id, clave, valor, ambito) values
  (:org_id, 'iva_tasa',            '0.16'::jsonb,        'global'),
  (:org_id, 'umbral_desviacion',   '0.05'::jsonb,        'global'),
  (:org_id, 'similitud_minima',    '0.90'::jsonb,        'global'),
  (:org_id, 'semana_tipo_default', '"obra"'::jsonb,      'global'),
  (:org_id, 'moneda',              '"MXN"'::jsonb,       'global'),
  (:org_id, 'densidad_default',    '"comfy"'::jsonb,     'global')
on conflict do nothing;

-- ------------------------------------------------------------
-- §6 · Criterios de evaluación por sujeto (configurables)
-- ------------------------------------------------------------
insert into criterio_evaluacion (org_id, aplica_a, clave, nombre, peso) values
  (:org_id, 'obra',        'OBR-AVA', 'Cumplimiento de programa',   1.0),
  (:org_id, 'obra',        'OBR-CAL', 'Calidad de ejecución',       1.0),
  (:org_id, 'obra',        'OBR-ORD', 'Orden y limpieza',           0.5),
  (:org_id, 'obra',        'OBR-SEG', 'Seguridad',                  1.0),
  (:org_id, 'residente',   'RES-CAP', 'Oportunidad en captura',     1.0),
  (:org_id, 'residente',   'RES-INC', 'Gestión de incidencias',     1.0),
  (:org_id, 'residente',   'RES-DOC', 'Expediente al día',          0.5),
  (:org_id, 'contratista', 'CON-CUM', 'Cumplimiento de entrega',    1.0),
  (:org_id, 'contratista', 'CON-CAL', 'Calidad del trabajo',        1.0),
  (:org_id, 'contratista', 'CON-PER', 'Personal y cuadrilla',       0.5)
on conflict (org_id, clave) do nothing;

commit;
