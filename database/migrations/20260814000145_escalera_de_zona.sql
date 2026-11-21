-- ============================================================
-- ObraCtrl · 0145 · La escalera como ELEMENTO (Fase 4a: escaleras con cotas)
--
-- La escalera sale de la DIFERENCIA DE COTAS de las zonas de losa (0137: cotas relativas al piso terminado de PB = 0). El elemento paramétrico
-- (`ESC-FORJADA`, biblioteca › Escaleras) calcula el número de peldaños, la contrahuella y la huella, el recorrido y el descanso entre rampas, y paga con el
-- concepto que YA existe en el catálogo (EST-01510, «escalón forjado de 1.20 m», por pieza) y con un concepto nuevo propuesto para el descanso (EJ-820, clave
-- provisional, sin precio: se registra como PROPUESTA en `propuesta_de_estructura`, 0131, clase `concepto_nuevo`; no hay tabla nueva para él ni se toca el
-- catálogo). Sin precios ni destajos con importe.
--
--   · `escalera_zona`: una escalera que ARRANCA en una zona de losa (`zona_id`: de ahí sale la cota del piso de arranque) y llega a otra cota:
--       - `zona_llegada_id`  : la zona cuyo piso es el de llegada (su cota de piso). Sin ella ni `cota_llegada_m`, la escalera llega a la cara alta de la losa
--                              de su propia zona (cota del piso + altura libre + espesor): sube al nivel de arriba.
--       - `cota_arranque_m` / `cota_llegada_m`: cotas explícitas que mandan sobre las de las zonas (relativas al mismo cero).
--       - `peldanos`          : sin él, salen del desnivel y de la contrahuella máxima (contrahuella real = desnivel / peldaños).
--       - `contrahuella_max_m`, `huella_m`, `ancho_m`, `espesor_m` (de la rampa y del descanso), `rampas` y `largo_descanso_m`: parámetros editables con
--                              valores por omisión conservadores (ver `escalera.PENDIENTES`).
--       - `trazo_id`          : MEDICIÓN DERIVADA: una línea del plano (el recorrido horizontal de las rampas); su longitud, con la escala, da la huella al
--                              calcular (no se guarda). Una línea no sirve a dos escaleras.
--       - `espacio_id` (0143) : el espacio donde está; su cantidad se escribe en la partida de ese espacio, sin doble conteo.
-- Solo Control de obra escribe (igual que las zonas y sus elementos); los demás roles que ven el plano leen. Aditiva y reversible: una zona sin escaleras se
-- comporta exactamente como hasta hoy.
-- ============================================================

create table if not exists escalera_zona (
  id                 uuid primary key default gen_random_uuid(),
  org_id             uuid not null references organizacion(id) on delete cascade,
  zona_id            uuid not null references losa_zona(id) on delete cascade,
  elemento_clave     text not null,
  zona_llegada_id    uuid references losa_zona(id) on delete set null,
  cota_arranque_m    numeric(8,3),
  cota_llegada_m     numeric(8,3),
  peldanos           smallint,
  contrahuella_max_m numeric(5,3) not null default 0.18,
  huella_m           numeric(5,3) not null default 0.25,
  ancho_m            numeric(5,3) not null default 1.20,
  espesor_m          numeric(5,3) not null default 0.12,
  rampas             smallint not null default 1,
  largo_descanso_m   numeric(5,3),
  trazo_id           uuid references trazo(id) on delete set null,
  espacio_id         uuid references espacio(id) on delete set null,
  autor_id           uuid references usuario(id) on delete set null,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  constraint ck_escalera_zona_clave check (elemento_clave in ('ESC-FORJADA')),
  constraint ck_escalera_zona_cotas check (
    (cota_arranque_m is null or cota_arranque_m between -30 and 100) and (cota_llegada_m is null or cota_llegada_m between -30 and 100)
  ),
  constraint ck_escalera_zona_una_llegada check (zona_llegada_id is null or cota_llegada_m is null),
  constraint ck_escalera_zona_otra_zona check (zona_llegada_id is null or zona_llegada_id <> zona_id),
  constraint ck_escalera_zona_peldanos check (peldanos is null or (peldanos between 2 and 120)),
  constraint ck_escalera_zona_contrahuella check (contrahuella_max_m between 0.10 and 0.30),
  constraint ck_escalera_zona_huella check (huella_m between 0.15 and 0.60),
  constraint ck_escalera_zona_ancho check (ancho_m between 0.40 and 5.00),
  constraint ck_escalera_zona_espesor check (espesor_m between 0.05 and 0.50),
  constraint ck_escalera_zona_rampas check (rampas between 1 and 4),
  constraint ck_escalera_zona_descanso check (largo_descanso_m is null or largo_descanso_m between 0.40 and 6.00)
);
-- Una línea del plano da el recorrido de UNA escalera: dos escaleras sobre la misma línea contarían lo mismo dos veces.
create unique index if not exists ux_escalera_zona_trazo on escalera_zona (trazo_id) where trazo_id is not null;
create index if not exists ix_escalera_zona_zona on escalera_zona (org_id, zona_id, created_at);
create index if not exists ix_escalera_zona_llegada on escalera_zona (zona_llegada_id) where zona_llegada_id is not null;
create index if not exists ix_escalera_zona_espacio on escalera_zona (espacio_id) where espacio_id is not null;
select app.attach_touch('escalera_zona');

comment on table escalera_zona is
  'Una escalera forjada que arranca en una zona de losa: sus cotas salen de las zonas (o son explícitas), los peldaños del desnivel, y su recorrido puede salir de una línea del plano (0145).';
comment on column escalera_zona.zona_id is 'Zona de arranque: de ahí sale la cota del piso de arranque (cota_piso_m) (0145).';
comment on column escalera_zona.zona_llegada_id is 'Zona cuyo piso es el de llegada; sin ella ni cota_llegada_m, la escalera llega a la cara alta de la losa de su zona (0145).';
comment on column escalera_zona.cota_arranque_m is 'Cota explícita del arranque (relativa al piso terminado de PB = 0); null = la del piso de la zona (0145).';
comment on column escalera_zona.cota_llegada_m is 'Cota explícita de la llegada; null = la de la zona de llegada o la cara alta de la losa de la zona (0145).';
comment on column escalera_zona.peldanos is 'Número de peldaños; null = el que sale del desnivel y de la contrahuella máxima (0145).';
comment on column escalera_zona.trazo_id is 'Medición derivada: línea del plano cuya longitud (con la escala) es el recorrido horizontal de las rampas y da la huella al calcular (0145).';
comment on column escalera_zona.espacio_id is 'El espacio donde está la escalera: su cantidad se escribe en la partida de ese espacio; null = sin espacio (no se escribe) (0145).';

alter table escalera_zona enable row level security;
drop policy if exists escalera_zona_lectura on escalera_zona;
create policy escalera_zona_lectura on escalera_zona
  for select
  using (
    org_id = app.current_org_id()
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  );
drop policy if exists escalera_zona_alta on escalera_zona;
create policy escalera_zona_alta on escalera_zona
  for insert
  with check (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  );
drop policy if exists escalera_zona_cambio on escalera_zona;
create policy escalera_zona_cambio on escalera_zona
  for update
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  )
  with check (org_id = app.current_org_id() and app.current_rol() = 'control_obra');
drop policy if exists escalera_zona_baja on escalera_zona;
create policy escalera_zona_baja on escalera_zona
  for delete
  using (
    org_id = app.current_org_id() and app.current_rol() = 'control_obra'
    and exists (
      select 1 from losa_zona z join plano p on p.id = z.plano_id where z.id = zona_id and app.obra_visible(p.obra_id)
    )
  );
grant select, insert, update, delete on escalera_zona to authenticated, obractrl_api;
