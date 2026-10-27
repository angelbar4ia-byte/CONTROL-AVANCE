-- ============================================================
-- ObraCtrl · 0071 · El cierre de un frente
--
-- QUÉ FALTABA
--
-- El cerebro cierra en dos candados (MODELO.md, D-515/D-522): **por frente** y, si
-- se requiere, por actividad; el segundo cierra todo el lote. ObraCtrl solo tenía el
-- cierre por actividad y la entrega de la obra: nada entre las dos.
--
-- El frente es el **nivel constructivo** (D-450): cimentación, planta baja, azotea;
-- se lee subiendo por el árbol desde la partida (`actividad.nivel_id`, con la etapa
-- como respaldo, igual que la Torre). Su avance es el de sus actividades ponderado
-- por costo —el mismo peso que el de la obra (0064)—.
--
-- LAS MANOS: el residente **solicita**, al 90 % de avance (D-261); el supervisor
-- **aprueba**; control de obra **valida**. Es el mismo molde que el cierre de
-- actividad (0009). Rechaza el supervisor o control, con motivo.
--
-- QUÉ SIGNIFICA CERRAR UN FRENTE (D-516): cierra **al residente** —ya no registra
-- avance ahí—; para los demás roles sigue abierto hasta la entrega de la casa. La
-- regla vive en el caso de uso de captura.
--
-- UN CIERRE ABIERTO POR FRENTE
--
-- Mientras haya una solicitud viva (solicitada, aprobada o validada) de un frente de
-- una obra no cabe otra: la validada es definitiva. Una rechazada no estorba: el
-- residente vuelve a solicitar cuando corrija lo que se le señaló.
--
-- `incidencia_calidad_id` es del cerebro («si el cierre levantó una»): una calidad
-- baja es una alerta y una persona decide si origina la incidencia. Queda la columna
-- para ligarla; todavía nada la escribe.
-- ============================================================

create type estatus_cierre_frente as enum ('solicitado', 'aprobado', 'validado', 'rechazado');

create table cierre_frente (
  id                    uuid primary key default gen_random_uuid(),
  org_id                uuid not null references organizacion(id) on delete cascade,
  obra_id               uuid not null references obra(id) on delete cascade,
  nivel_id              uuid not null references nivel(id),
  estatus               estatus_cierre_frente not null default 'solicitado',
  -- El avance del frente **cuando se solicitó**: la constancia de que llegó al 90 %.
  avance_pct            numeric(5,2) not null check (avance_pct between 0 and 100),
  solicitado_por        uuid not null references usuario(id),
  solicitado_en         timestamptz not null default now(),
  aprobado_por          uuid references usuario(id),
  aprobado_en           timestamptz,
  validado_por          uuid references usuario(id),
  validado_en           timestamptz,
  comentarios           text,
  incidencia_calidad_id uuid references incidencia(id),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  -- Cada paso deja a su autor y su momento juntos.
  constraint ck_cierre_frente_aprobacion check ((aprobado_por is null) = (aprobado_en is null)),
  constraint ck_cierre_frente_validacion check ((validado_por is null) = (validado_en is null)),
  -- Lo validado pasó por la aprobación: no se valida lo que no se aprobó.
  constraint ck_cierre_frente_cadena check (validado_por is null or aprobado_por is not null)
);
select app.attach_touch('cierre_frente');

create unique index uq_cierre_frente_vivo
  on cierre_frente (obra_id, nivel_id)
  where estatus <> 'rechazado';
create index ix_cierre_frente_obra on cierre_frente (org_id, obra_id, nivel_id, created_at desc);

comment on table cierre_frente is
  'Cierre de un frente (nivel) de una obra (0071, D-515/D-522): el residente solicita al 90 %, el supervisor aprueba, control valida. Cerrado el frente, el residente ya no registra avance ahí.';

alter table cierre_frente enable row level security;
create policy cierre_frente_scope on cierre_frente
  for all
  using      (org_id = app.current_org_id() and app.obra_visible(obra_id))
  with check (org_id = app.current_org_id() and app.obra_visible(obra_id));

-- Los pasos son UPDATE; el borrado no: un cierre solicitado es rastro de quién y cuándo.
grant select, insert, update on cierre_frente to authenticated, obractrl_api;
revoke delete, truncate on cierre_frente from authenticated, obractrl_api;
