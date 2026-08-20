-- down · 0024 · Registro de respaldos
--
-- Se pierde la constancia de qué se respaldó y qué se restauró: `/health`
-- volvería a decir "sin registro" aunque haya respaldos reales. No es un
-- problema de datos —los respaldos siguen existiendo— sino de saber de ellos,
-- que era justamente el punto.

drop table if exists app.respaldo cascade;
