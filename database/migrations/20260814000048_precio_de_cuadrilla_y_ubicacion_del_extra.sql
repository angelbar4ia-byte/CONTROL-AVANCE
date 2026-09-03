-- ============================================================
-- ObraCtrl · 0048 · El precio de la cuadrilla y dónde cae un extra
-- Spec §7.6 (Cuadrilla) · §11.2 (alta extra) · §7.4 (WBS) · §12.4 (RLS)
--
-- POR QUÉ EL CAMBIO
--
-- Dos huecos que impiden dar de alta trabajo fuera de catálogo como el jefe de
-- obra lo describe: *"el residente dice qué cuadrilla va a utilizar, cuántas y
-- el tiempo, también el material, y se crea el precio"*.
--
-- 1. `cuadrilla` NO TIENE PRECIO
--
-- Tiene `rendimiento` —cuánto hace en un día— pero no cuánto cuesta ese día.
-- Con rendimiento y sin costo se puede calcular cuánto tarda y no cuánto vale,
-- que es justo la mitad que hace falta para armar un precio.
--
-- El costo de mano de obra existe hoy en `insumo` (439 de tipo `mano_obra`,
-- 264 ligados a una cuadrilla): ahí el APU ya cruza cantidad por costo. Pero
-- eso es el costo del **concepto de catálogo**, y un trabajo que no está en el
-- catálogo no tiene APU del cual sacarlo. Para armarlo desde cero hace falta el
-- precio de la cuadrilla como tal.
--
-- Nulable: el catálogo tiene 92 cuadrillas y ninguna con precio todavía. Un
-- precio en cero mentiría —diría que la cuadrilla es gratis— mientras que nulo
-- dice lo que pasa: no se ha capturado, y el precio armado lo reporta en vez de
-- devolver una cifra falsa.
--
-- 2. UN EXTRA NO SABE DÓNDE CAE
--
-- `crear_extra` guarda `frente_id` y nada más. El residente mira su obra por
-- **nivel** (el frente: cimentación, planta baja) y **etapa** (el sub-frente),
-- así que un extra sin ninguno de los dos no aparece en ningún grupo de su
-- pantalla: queda como trabajo huérfano que solo se ve filtrando por «fuera de
-- catálogo».
--
-- Las columnas ya existen en `actividad` —las usan las actividades generadas
-- desde el prototipo—; lo que falta es que el alta manual las escriba. Eso es
-- código, no esquema. Aquí solo se documenta que ese es su uso, porque el
-- comentario actual no lo dice y el próximo que lea la tabla no lo sabrá.
-- ============================================================

alter table cuadrilla add column costo_jornada numeric(18,6)
  check (costo_jornada is null or costo_jornada >= 0);

comment on column cuadrilla.costo_jornada is
  'Lo que cuesta un día de esta cuadrilla (§7.6). Con `rendimiento` se sabe cuánto hace en un día; con esto, cuánto vale — las dos mitades del precio que el residente arma para un trabajo fuera de catálogo. Nulo = no capturado: un cero diría que la cuadrilla es gratis.';

comment on column actividad.nivel_id is
  'El **frente** con el que el residente mira su obra (§7.4): cimentación, planta baja, azotea. Lo copia el workflow A del árbol del prototipo, y el alta fuera de catálogo lo captura — sin él la actividad no cae en ningún grupo de su pantalla.';

comment on column actividad.etapa_id is
  'El **sub-frente**: la etapa constructiva dentro del nivel (§7.4). Es donde las cosas pasan juntas —si se atrasa la albañilería de planta baja, se atrasan sus tres actividades— y por eso es la unidad con la que se reprograma.';
