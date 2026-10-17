-- ============================================================
-- ObraCtrl · 0057 · Cuantificador: plano, trazo, enlace, nota
-- cerebro MODELO.md §1b (líneas 257-430, "Cuantificación — de dónde sale
-- la cantidad") · CONOCIMIENTO.md §5.10 (cuantificador vs. paramétrico) ·
-- HALLAZGO 12 de MODELO.md §1 (modo_cantidad='medida', ya declarado en la
-- migración 0055, sin nada que lo produjera hasta ahora).
--
-- QUÉ ES Y PARA QUÉ
--
-- `plano → medida → cantidad`: alguien traza sobre un plano ejecutivo
-- (polígono/línea/punto/conteo) y esa medida produce una cantidad real
-- para un elemento del árbol de presupuesto — a diferencia del
-- paramétrico (que estima) o de la ingeniería del lote (que reconstruye
-- por destajo, ya construido, migración 0056). Es la única vía que cerebro
-- reconoce para confirmar un elemento de "matriz dentro de otra matriz"
-- sin ancla propia en ningún archivo (CONOCIMIENTO.md D-318, una
-- contratrabe dentro de la matriz de una losa).
--
-- POSTGIS
--
-- Ya instalado y habilitado a mano en este Postgres de desarrollo
-- (`apt-get install postgresql-16-postgis-3`, `create extension postgis`);
-- esta migración lo deja formal, mismo patrón que la 0001 con
-- pgcrypto/pg_trgm/unaccent. Producción se confirma aparte, fuera de esta
-- tarea.
--
-- DOS HUECOS REALES QUE NI CEREBRO NI OBRACTRL TENÍAN RESUELTOS
-- (decisiones ya tomadas con el usuario, no se reabren aquí):
--
-- 1) `PLANO` no existe como entidad en ningún lado: cerebro referencia
--    `plano_id`/`version_plano`/`capa` en TRAZO/ENLACE_CUANTIFICACION/
--    NOTA_PLANO pero nunca define esa tabla (MODELO.md §1b). Se llena
--    inspirada en el patrón ya existente de `expediente_doc` (migración
--    0010: archivo ya subido a R2 por `POST /evidencias/presigned`, el
--    binario nunca viaja por la API) pero con `version` y `capas`, que
--    `expediente_doc` no necesita.
--
-- 2) A qué "nodo" se liga `ENLACE_CUANTIFICACION`: cerebro tiene un solo
--    árbol NODO que es plantilla E instancia a la vez; ObraCtrl los separa
--    en `prototipo_nodo` (plantilla compartida por muchas obras) y
--    `actividad` (instancia por obra, con `cant_base` copiado de
--    `prototipo_nodo.cantidad` al generar la obra,
--    `casos_uso/generar_obra_desde_prototipo.py`). `enlace_cuantificacion`
--    distingue los dos casos con `tipo_nodo` + `actividad_id`/
--    `prototipo_nodo_id` mutuamente excluyentes — mismo patrón que
--    `desviacion.tipo_nodo`/`insumo_id`/`concepto_id` (migración 0054):
--      · `actividad_id`      -> obra con presupuesto ya congelado: la
--        medida se COMPARA contra `actividad.cant_base`, nunca la
--        reemplaza (`adapters/repos/actividades_sql.py` ~línea 373: "No
--        toca cant_base ni cant_ejecutada"). Si se desvía, nace una
--        `Desviacion` candidata (migración 0054), `causa=null` siempre.
--      · `prototipo_nodo_id` -> prototipo "diseño_nuevo" de un solo uso
--        (el que `AplicadorIngenieriaLote._aplicar_diseno_nuevo` crea,
--        `application/casos_uso/aplicar_carga.py`): ahí SÍ se sobreescribe
--        `prototipo_nodo.cantidad` directo, con `modo_cantidad='medida'`
--        — mismo mecanismo que ya usa esa clase para `modo_cantidad=
--        'cargada'`, porque ese prototipo es exclusivo de una sola obra
--        (no hay presupuesto congelado de muchas casas que proteger).
--
-- CÓMO VIAJA LA GEOMETRÍA (MODELO.md §1b, Decisiones 2 y 3 de 3)
--
-- GeoJSON para transportar varios trazos ya existentes (lectura, borde de
-- la API) y WKT para capturar uno nuevo mientras se dibuja (escritura,
-- borde de la API) — PostGIS nativo en los dos sentidos (`ST_AsGeoJSON`/
-- `ST_GeomFromGeoJSON`, `ST_GeomFromText`). Lo que persiste SIEMPRE es el
-- tipo nativo `geometry` de PostGIS, nunca texto: así conserva el índice
-- `GiST` y los `ST_*` no reparsean texto en cada cálculo.
--
-- Coordenadas de PLANO, no geográficas: SRID 0 — no es lon/lat WGS84, es
-- local al plano, con su propia escala (MODELO.md §1b).
-- ============================================================

create extension if not exists "postgis";

-- --- Enums ----------------------------------------------------------

create type fuente_trazo as enum ('pdf', 'dwg', 'ifc');
comment on type fuente_trazo is
  'De qué archivo salió el trazo (MODELO.md §1b, TRAZO.fuente). Determina la precedencia al reemplazar un enlace: IFC > DWG > PDF — esa comparación de precedencia es trabajo de quien llama a ReemplazarEnlace (acción manual, nunca automática), no un CHECK de esta tabla.';

create type medida_cuantificacion as enum ('area', 'perimetro', 'longitud', 'conteo');
comment on type medida_cuantificacion is
  'Qué métrica del trazo alimenta la cantidad (MODELO.md §1b, ENLACE_CUANTIFICACION.medida): area/perimetro/longitud se calculan en SQL con ST_Area/ST_Perimeter/ST_Length sobre trazo.geometria; conteo no es una función de PostGIS, es "este trazo cuenta como una instancia" (valor 1 por enlace, sumado entre los vigentes del nodo).';

create type tipo_nodo_cuantificacion as enum ('actividad', 'prototipo_nodo');
comment on type tipo_nodo_cuantificacion is
  'A qué mitad del NODO de cerebro apunta este enlace (ver cabecera, hueco 2): actividad (instancia por obra, presupuesto ya congelado -> compara, nunca pisa) o prototipo_nodo (plantilla de un prototipo "diseño_nuevo" de un solo uso -> sí se sobreescribe, mismo mecanismo que modo_cantidad=cargada).';

-- --- plano ------------------------------------------------------------

create table plano (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references organizacion(id) on delete cascade,
  obra_id     uuid not null references obra(id) on delete cascade,
  nombre      text not null,
  archivo_url text not null,
  version     integer not null default 1 check (version > 0),
  capas       text[],
  subido_por  uuid references usuario(id),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
select app.attach_touch('plano');
create index ix_plano_obra on plano (org_id, obra_id);

comment on table plano is
  'Entidad que cerebro nunca definió (ver cabecera, hueco 1): el plano ejecutivo sobre el que se traza. archivo_url es la CLAVE del objeto ya subido a R2 con POST /evidencias/presigned (mismo patrón que expediente_doc.url, migración 0010) — el binario nunca viaja por esta tabla ni por la API.';
comment on column plano.version is
  'A diferencia de expediente_doc, un plano se reexporta con cambios: version distingue qué trazos corresponden a qué estado del archivo (MODELO.md §1b, "Si el plano cambia").';
comment on column plano.capas is
  'Nombres de capa del archivo CAD/BIM de origen, informativo — trazo.capa es independiente y puede no coincidir 1 a 1 si el trazo se redibuja a mano sobre el plano.';

-- --- trazo --------------------------------------------------------------

create table trazo (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  plano_id      uuid not null references plano(id) on delete cascade,
  version_plano integer not null,
  capa          text,
  geometria     geometry(Geometry, 0) not null,
  fuente        fuente_trazo not null,
  autor_id      uuid references usuario(id),
  created_at    timestamptz not null default now()
);
create index ix_trazo_plano on trazo (org_id, plano_id);
create index ix_trazo_geometria on trazo using gist (geometria);

comment on table trazo is
  'Un polígono/línea/punto trazado sobre un plano (MODELO.md §1b). Cuarenta trabes físicas son cuarenta filas de trazo —una por instancia, para auditar "la trabe 17 mide tanto"—, nunca una sola fila con una cantidad agregada.';
comment on column trazo.geometria is
  'Tipo nativo de PostGIS, SRID 0: coordenadas de PLANO, no geográficas (MODELO.md §1b). Se persiste la geometría nativa, nunca el texto WKT/GeoJSON con el que se capturó o se transporta — eso se descarta en el borde de la API (D-218 del cerebro).';
comment on column trazo.version_plano is
  'Copia de plano.version al momento de trazar (no una FK a una tabla de versiones, que no existe): si el plano se reexporta con otra version, los trazos de la version anterior quedan identificables para marcarse a revisión (MODELO.md §1b, "Si el plano cambia") sin recalcularse solos.';

-- --- enlace_cuantificacion -----------------------------------------------

create table enlace_cuantificacion (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references organizacion(id) on delete cascade,
  trazo_id          uuid not null references trazo(id) on delete cascade,
  tipo_nodo         tipo_nodo_cuantificacion not null,
  actividad_id      uuid references actividad(id) on delete cascade,
  prototipo_nodo_id uuid references prototipo_nodo(id) on delete cascade,
  medida            medida_cuantificacion not null,
  factor            numeric(18,6) not null check (factor > 0),
  vigente           boolean not null default true,
  created_at        timestamptz not null default now(),

  -- El nodo es exactamente uno: actividad XOR prototipo_nodo, mismo
  -- criterio que ck_desviacion_nodo (migración 0054) y ck_explosion_hijo
  -- (migración 0005).
  constraint ck_enlace_cuantificacion_nodo check (
    (tipo_nodo = 'actividad'       and actividad_id is not null and prototipo_nodo_id is null) or
    (tipo_nodo = 'prototipo_nodo'  and prototipo_nodo_id is not null and actividad_id is null)
  )
);
create index ix_enlace_cuantificacion_trazo on enlace_cuantificacion (org_id, trazo_id);
create index ix_enlace_cuantificacion_actividad
  on enlace_cuantificacion (org_id, actividad_id) where actividad_id is not null;
create index ix_enlace_cuantificacion_prototipo_nodo
  on enlace_cuantificacion (org_id, prototipo_nodo_id) where prototipo_nodo_id is not null;
-- Solo los vigentes se suman (MODELO.md §1b): la consulta de agregación
-- siempre filtra por esto, así que es el índice que de verdad importa.
create index ix_enlace_cuantificacion_vigentes
  on enlace_cuantificacion (org_id, tipo_nodo, actividad_id, prototipo_nodo_id)
  where vigente;

comment on table enlace_cuantificacion is
  'medida × factor = cantidad (MODELO.md §1b). Un nodo puede tener MUCHOS enlaces vigentes a la vez —una instancia física cada uno— y todos suman entre sí; lo que no puede haber es dos enlaces vigentes de la MISMA instancia física. Cómo el sistema sabe que dos trazos son la misma instancia queda SIN resolver, igual que en cerebro: depende de que quien traza reemplace el enlace a mano (ReemplazarEnlace), nunca de un emparejamiento automático por cercanía espacial.';
comment on column enlace_cuantificacion.vigente is
  'Falso si otra fuente de mayor precedencia (IFC > DWG > PDF) lo reemplazó: queda como evidencia, nunca se borra ni se vuelve a sumar (MODELO.md §1b).';
comment on column enlace_cuantificacion.factor is
  'medida × factor = cantidad. No tiene columna propia de "cantidad": se calcula leyendo trazo.geometria en el momento (ST_Area/ST_Perimeter/ST_Length) en vez de guardarla congelada, porque la geometría de un trazo nunca cambia después de creado (un cambio real es un trazo nuevo con su propio enlace, nunca un UPDATE de geometria).';

-- --- nota_plano -----------------------------------------------------------

create table nota_plano (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  plano_id      uuid not null references plano(id) on delete cascade,
  version_plano integer not null,
  ubicacion     geometry(Point, 0) not null,
  autor_id      uuid references usuario(id),
  texto         text not null,
  actividad_id  uuid references actividad(id) on delete set null,
  created_at    timestamptz not null default now()
);
create index ix_nota_plano_plano on nota_plano (org_id, plano_id);

comment on table nota_plano is
  'Anotación flotante sobre el plano (MODELO.md §1b): nunca produce cantidad, nunca tiene enlace_cuantificacion. Si algún día una nota necesita generar cantidad, no se amplía esta tabla: se convierte en un trazo, que ya sabe hacer eso.';
comment on column nota_plano.actividad_id is
  'Nullable a propósito: la nota puede ser sobre un lugar del plano sin ser sobre ningún concepto en particular (MODELO.md §1b). Solo actividad —nunca prototipo_nodo—: una nota de obra siempre habla de la ejecución de ESA obra, no de la plantilla que comparten otras.';

-- --- RLS -------------------------------------------------------------
--
-- plano tiene obra_id directo: mismo patrón "por_obra" que expediente_doc
-- (migración 0012). trazo/enlace_cuantificacion/nota_plano llegan a la obra
-- por su padre —mismo criterio que registro_avance llegando por actividad
-- (migración 0012)—, encadenando el EXISTS hasta plano cuando hace falta.
-- Ninguna tiene es_config(): a diferencia de los catálogos compartidos
-- (prototipo_nodo incluido), cuantificar es una acción operativa ligada a
-- una obra, abierta a cualquier rol que la vea (MODELO.md §1b, "trazar:
-- Costos·Control·Residente·Supervisor" — ver nota de alcance de roles en
-- domain.cuantificacion/los endpoints: la escritura real sobre
-- prototipo_nodo queda limitada aparte, por la política ya existente de
-- esa tabla, es_config() en su UPDATE, migración 0012).

alter table plano enable row level security;
create policy plano_scope on plano
  for all
  using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));

alter table trazo enable row level security;
create policy trazo_scope on trazo
  for all
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from plano p
       where p.id = plano_id and app.obra_visible(p.obra_id)
    )
  )
  with check (
    org_id = app.current_org_id()
    and exists (
      select 1 from plano p
       where p.id = plano_id and app.obra_visible(p.obra_id)
    )
  );

alter table enlace_cuantificacion enable row level security;
create policy enlace_cuantificacion_scope on enlace_cuantificacion
  for all
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from trazo t
      join plano p on p.id = t.plano_id
       where t.id = trazo_id and app.obra_visible(p.obra_id)
    )
  )
  with check (
    org_id = app.current_org_id()
    and exists (
      select 1 from trazo t
      join plano p on p.id = t.plano_id
       where t.id = trazo_id and app.obra_visible(p.obra_id)
    )
  );

alter table nota_plano enable row level security;
create policy nota_plano_scope on nota_plano
  for all
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from plano p
       where p.id = plano_id and app.obra_visible(p.obra_id)
    )
  )
  with check (
    org_id = app.current_org_id()
    and exists (
      select 1 from plano p
       where p.id = plano_id and app.obra_visible(p.obra_id)
    )
  );

-- Mismo criterio que la 0054/0020: se otorga explícito, sin depender de
-- que el rol que corre esta migración sea el que fijó los defaults.
grant select, insert, update, delete on plano, trazo, enlace_cuantificacion, nota_plano
  to authenticated, obractrl_api;
