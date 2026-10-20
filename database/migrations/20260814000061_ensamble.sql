-- ============================================================
-- ObraCtrl · 0061 · Ensamble: el presupuesto paramétrico (§8.3, §12.4)
-- cerebro CONOCIMIENTO.md §5.7-§5.10 · skill erp-parametrico
--
-- QUÉ ES
--
-- "El mismo mecanismo del APU, un piso más arriba" (skill §0):
--
--   APU           concepto  → insumos    con cantidad
--   PARAMÉTRICO   ensamble  → conceptos  con cantidad
--
-- Un ensamble es una plantilla ("Recámara tipo A") — no se contrata ni se
-- programa, eso lo sigue haciendo el concepto real una vez que el ensamble
-- se aplica (skill §1). Es desglosable: un ensamble puede contener
-- sub-ensambles, por eso `ensamble_renglon` cuelga de un concepto O de otro
-- ensamble, nunca de los dos — mismo patrón que `ck_prototipo_nodo_concepto`
-- (migración 0006).
--
-- POR QUÉ NO HAY `ensamble.parent_id`
--
-- Un sub-ensamble ("Baño tipo B") se reusa dentro de varios ensambles
-- distintos ("Casa tipo A" y "Casa tipo B" pueden compartirlo) — exactamente
-- la misma razón por la que un concepto puede estar en varios ensambles sin
-- que sea doble contabilidad (skill §2, regla 3 de §8). Un `parent_id` en
-- `ensamble` forzaría un solo padre; la relación vive en `ensamble_renglon`.
--
-- LA REFERENCIA APUNTA AL CONCEPTO, NO AL RENGLÓN (skill §3)
--
-- `ensamble_renglon.concepto_id` referencia el catálogo compartido
-- (`concepto`), nunca una `partida_presupuesto` concreta: si el presupuesto
-- de origen se borra o se reordena, el ensamble sigue armable. El
-- presupuesto de origen se guarda en `presupuesto_origen_id` como
-- referencia informativa (ver su columna), no como liga estructural.
--
-- EL DIVISOR VIVE EN EL ENSAMBLE, CON SU PROPIO PARÁMETRO (§5.7)
--
-- Comprobado contra los siete prototipos reales: un parámetro global
-- (costo ÷ m² total) varía 36% entre prototipos y es inútil. Cimentación
-- escala con el área de **desplante** (la losa que realmente se cuela), no
-- con el m² total — ese error de denominador, no la partición por número de
-- plantas, era lo que rompía el ajuste (CV 21.5% contra 6.0%, B-52/D-312).
-- Por eso el divisor es explícito por ensamble (`divisor_concepto_id`,
-- `divisor_nombre`) y nunca un m² global de `prototipo`/`obra`: el
-- desplante de cada prototipo ya vive como la cantidad de su propio
-- concepto de losa, y ESE concepto es el divisor de "Cimentación", no
-- `prototipo.m2`.
--
-- COHORTE EXPLÍCITA, NUNCA UNA REGLA DERIVADA (§5.7, regla 8 del skill)
--
-- "Separar por número de plantas" parecía la cohorte correcta de
-- cimentación y no lo era: los dos Diamante (dos plantas) se comportan
-- como los de una planta. La cohorte se declara a mano, prototipo por
-- prototipo (`ensamble_cohorte`) — nunca una condición calculada sobre
-- niveles/m²/lo que sea, porque la condición que de verdad separa a los
-- prototipos no se adivina, se descubre con datos y se declara.
--
-- LA DISPERSIÓN SE GUARDA JUNTO AL VALOR (regla 9 del skill)
--
-- `ensamble.tasa` sin `ensamble.dispersion` sería "un número disfrazado de
-- certeza" (Herrería a $116 ±38% es una adivinanza; Acabados a $911 ±5% es
-- utilizable). Las dos columnas se calculan juntas, nunca una sin la otra
-- (dominio puro en `domain.catalogos.ensamble`, migración pendiente de
-- código — esta migración solo abre el espacio donde esas dos cifras
-- viven).
-- ============================================================

create type origen_cantidad_ensamble as enum (
  'heredada_concepto', 'heredada_destajo', 'manual'
);
comment on type origen_cantidad_ensamble is
  'De dónde sale la cantidad de un renglón de ensamble (skill erp-parametrico §2): heredada_concepto (la cantidad que el concepto tiene en el presupuesto de origen) · heredada_destajo (los m² de un destajo dentro del concepto auxiliar) · manual (capturada a mano). "Heredar es mejor que capturar": heredada, el ensamble se entera si el volumen de origen cambia; manual se desincroniza en silencio.';

create table ensamble (
  id                   uuid primary key default gen_random_uuid(),
  org_id               uuid not null references organizacion(id) on delete cascade,
  clave                text not null,
  nombre               text not null,
  divisor_concepto_id  uuid references concepto(id),
  divisor_nombre       text,
  tasa                 numeric(18,6),
  dispersion           numeric(7,4),
  tasa_calculada_en     timestamptz,
  estatus              estatus_registro not null default 'activo',
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  constraint uq_ensamble_clave unique (org_id, clave)
);
select app.attach_touch('ensamble');

comment on table ensamble is
  'Plantilla paramétrica (skill erp-parametrico): "Recámara tipo A", no contratable ni programable. Su tasa/dispersión se publican juntas (regla 9) sobre un divisor propio, nunca un m² global.';
comment on column ensamble.divisor_concepto_id is
  'El concepto cuya cantidad, en el presupuesto de cada prototipo de la cohorte, normaliza la tasa de este ensamble (§5.7: para "Cimentación" es la losa de desplante, nunca prototipo.m2). Nulable mientras el ensamble no tiene tasa publicada.';
comment on column ensamble.divisor_nombre is
  'Etiqueta legible del divisor ("m² de desplante", "número de salidas") para la pantalla — el cálculo usa divisor_concepto_id, esto es solo presentación.';
comment on column ensamble.dispersion is
  'Coeficiente de variación de la tasa sobre la cohorte (§5.7). Nunca se guarda tasa sin dispersion ni dispersion sin tasa (regla 9 del skill) — lo exige el dominio, no un CHECK: una tasa en construcción (sin cohorte suficiente todavía) legítimamente no tiene ninguna de las dos.';

create table ensamble_cohorte (
  ensamble_id   uuid not null references ensamble(id) on delete cascade,
  org_id        uuid not null references organizacion(id) on delete cascade,
  prototipo_id  uuid not null references prototipo(id) on delete cascade,
  created_at    timestamptz not null default now(),
  primary key (ensamble_id, prototipo_id)
);

comment on table ensamble_cohorte is
  'A qué prototipos aplica este ensamble (skill §5, regla 8 y 10): declarada a mano, prototipo por prototipo — nunca una condición derivada (m², número de plantas, …). Fuera de su cohorte, un ensamble no se usa.';

create table ensamble_renglon (
  id                     uuid primary key default gen_random_uuid(),
  org_id                 uuid not null references organizacion(id) on delete cascade,
  ensamble_id            uuid not null references ensamble(id) on delete cascade,
  concepto_id            uuid references concepto(id),
  sub_ensamble_id        uuid references ensamble(id),
  cantidad               numeric(18,6) not null,
  origen                 origen_cantidad_ensamble not null,
  presupuesto_origen_id  uuid references presupuesto(id) on delete set null,
  orden                  integer not null default 0,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),

  -- El hijo es un concepto O un sub-ensamble, nunca los dos ni ninguno
  -- (mismo patrón que ck_prototipo_nodo_concepto, migración 0006).
  constraint ck_ensamble_renglon_hijo check (
    (concepto_id is not null and sub_ensamble_id is null) or
    (concepto_id is null and sub_ensamble_id is not null)
  ),
  -- Un ensamble no se contiene a sí mismo directamente. No cierra ciclos
  -- más profundos (A contiene B contiene A) — eso lo valida el dominio al
  -- recorrer el árbol (mismo criterio que CicloEnExplosion de APU), no un
  -- CHECK de Postgres, que no puede recorrer recursión contra otra fila.
  constraint ck_ensamble_renglon_no_autoref check (
    sub_ensamble_id is null or sub_ensamble_id <> ensamble_id
  )
);
select app.attach_touch('ensamble_renglon');
create index ix_ensamble_renglon_ensamble on ensamble_renglon (org_id, ensamble_id);
create unique index uq_ensamble_renglon_concepto
  on ensamble_renglon (ensamble_id, concepto_id) where concepto_id is not null;
create unique index uq_ensamble_renglon_sub_ensamble
  on ensamble_renglon (ensamble_id, sub_ensamble_id) where sub_ensamble_id is not null;

comment on table ensamble_renglon is
  'Un concepto o sub-ensamble dentro de un ensamble, con su propia cantidad (skill §2-§3): la referencia apunta al concepto, nunca a una partida de presupuesto concreta, para que el ensamble sobreviva aunque ese presupuesto se borre o reordene.';
comment on column ensamble_renglon.presupuesto_origen_id is
  'De qué presupuesto se extrajo este renglón (si vino de una Extracción) — referencia informativa (skill §3), nunca liga estructural: borrar ese presupuesto no borra este renglón (on delete set null).';

-- RLS de catálogo: mismo predicado que especialidad/contratista_especialidad
-- (migración 0047) — alcance de organización, escritura solo para quien
-- configura (§5.1: Control de obra, Super intendente).
do $$
declare
  t text;
begin
  foreach t in array array['ensamble', 'ensamble_cohorte', 'ensamble_renglon'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format($p$
      create policy %1$s_select on public.%1$I
        for select using (org_id = app.current_org_id())
    $p$, t);
    perform app.crear_policies_escritura(
      t, 'org_id = app.current_org_id() and app.es_config()');
  end loop;
end;
$$;

grant select, insert, update, delete
  on ensamble, ensamble_cohorte, ensamble_renglon to authenticated, obractrl_api;
