-- ============================================================
-- ObraCtrl · 0050 · Dónde en la obra pasa una incidencia
-- Spec §7.4 (frente/sub-frente) · §7.8 (incidencias) · §12.4 (RLS)
--
-- POR QUÉ EL CAMBIO
--
-- `incidencia.frente_id` apunta a `frente` (0005): OBRA, INSTALACIONES,
-- SUBCONTRATOS, PINTURA — a quién se le compra. Es el eje correcto para
-- `actividad` y `control_cambio`, pero una incidencia no se reporta contra un
-- tipo de contratación: se reporta contra un lugar de la obra —"falta cemento
-- en planta baja", "el castillo del eje 3 quedó fuera de plomo"—, que es
-- justo el par nivel/etapa que ya usan `actividad` (0037, 0041) y
-- `control_cambio` (0049).
--
-- Sin este par, la bandeja de incidencias no puede agruparlas por dónde están
-- pasando: solo por el tipo de contratación, que no es la pregunta que hace
-- Control cuando mira la obra ("¿qué está pasando en planta baja?").
--
-- `frente_id` no se toca ni se retira: sigue siendo válido decir "esto es
-- cosa de instalaciones" además de "esto es en planta baja" — son ejes
-- distintos, la misma separación que ya existe entre frente y especialidad
-- (0047).
-- ============================================================

alter table incidencia add column nivel_id uuid references nivel(id);
alter table incidencia add column etapa_id uuid references etapa_constructiva(id);

comment on column incidencia.nivel_id is
  'Dónde en la obra: el nivel (§7.4) — cimentación, planta baja, azotea. Es el mismo eje que actividad.nivel_id y control_cambio.nivel_id; frente_id sigue siendo el tipo de contratación (0005) y no se toca.';

comment on column incidencia.etapa_id is
  'El sub-frente dentro del nivel (§7.4): la etapa constructiva. Mismo eje que actividad.etapa_id.';
