-- ============================================================
-- ObraCtrl · 0024 · Registro de respaldos y restauraciones probadas
-- Spec §11.7 (`/health` reporta el último respaldo) · §12.12 (respaldo con
-- restauración probada) · Fase 8 frente 5 del ROADMAP.
--
-- POR QUÉ HACE FALTA UNA TABLA
--
-- El §11.7 pide que `/health` diga cuándo fue el último respaldo, y la sonda
-- **no tiene forma de averiguarlo sola**: el respaldo lo hace un proceso de
-- fuera —el cron de Supabase, o `scripts/respaldar.sh`— y no deja ninguna
-- huella dentro de la base. Sin esta tabla, el campo tendría que ser una
-- variable de entorno con una fecha escrita a mano, que es exactamente el tipo
-- de dato que envejece mintiendo.
--
-- Así, la sonda responde con lo que sabe y no con lo que supone. Si nadie ha
-- registrado nunca un respaldo, lo dice: *sin registro* es un diagnóstico
-- verdadero y accionable, y no lo mismo que "hace mucho".
--
-- POR QUÉ EN `app` Y NO EN `public`
--
-- Es una tabla de operación, no de negocio: no pertenece a ninguna
-- organización y no tiene por qué existir para el multi-tenant. En `app` queda
-- fuera del alcance de PostgREST y de la ruta directa a Supabase (§10.7), así
-- que no necesita RLS para no filtrarse — no hay a quién filtrarse. El backend
-- la lee con un `grant` explícito; la escriben los scripts, que corren como
-- superusuario.
--
-- LAS DOS FILAS QUE IMPORTAN NO SON LA MISMA
--
-- `tipo` distingue el respaldo de la restauración probada porque son dos
-- garantías distintas y la segunda es la que vale: un respaldo que nunca se
-- restauró es una carpeta que crece. `/health` reporta las dos, y una
-- restauración vieja con respaldos recientes es justo la señal que hay que
-- poder ver.
-- ============================================================

create table app.respaldo (
  id           uuid primary key default gen_random_uuid(),
  tipo         text not null check (tipo in ('respaldo', 'restauracion_probada')),
  iniciado_en  timestamptz not null default now(),
  terminado_en timestamptz,
  ok           boolean not null default false,
  bytes        bigint,
  -- De dónde salió: nombre de la base, del entorno o del job que lo corrió.
  -- Sin cadenas de conexión: esto se acaba mostrando en `/health` (§12.4).
  origen       text,
  detalle      text
);

comment on table app.respaldo is
  'Bitácora de respaldos y de restauraciones probadas (§12.12). La escriben database/scripts/respaldar.sh y probar_respaldo.sh; la lee /health/dependencias (§11.7). Un respaldo que nunca se restauró no es un respaldo.';

create index ix_respaldo_reciente on app.respaldo (tipo, terminado_en desc);

-- El backend solo lee: quien respalda es un proceso de operación, no la API.
grant select on app.respaldo to obractrl_api;
