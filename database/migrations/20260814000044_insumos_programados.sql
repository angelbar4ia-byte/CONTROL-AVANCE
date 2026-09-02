-- ============================================================
-- ObraCtrl · 0044 · Lo que hace falta para los insumos programados
-- Spec §7.3 (APU) · §7.5 (cronograma) · §7.6 (Actividad) · §10.1 (catálogo)
--
-- POR QUÉ EL CAMBIO
--
-- Se está armando el módulo de **insumos programados**: cruzar el cronograma
-- de una obra con la explosión del APU para contestar la pregunta que decide
-- una compra, "¿cuánto cemento necesito la semana 22 y cuándo lo pido?".
--
-- Al escribirlo aparecieron dos huecos en datos que ya existían.
--
-- 1 · `cant_programada` NACÍA EN CERO
--
-- El INSERT de `crear_actividades` (workflow A, §11.3 A.2) no la mandaba, así
-- que tomaba el default 0 en toda actividad generada. Consecuencias que nadie
-- había notado porque las semillas y las pruebas sí la ponen:
--
--   · el check `cant_ejecutada <= cant_programada` dejaba la obra sin poder
--     capturar avance hasta que alguien escribiera la cifra a mano;
--   · el tope `cant_programada <= cant_base * 1.2` no se ejercía nunca;
--   · cualquier cálculo derivado de "lo que se mandó hacer" salía en cero.
--
-- Una actividad se genera ya **programada** —es su `estatus` inicial— y con la
-- cantidad que el presupuesto le dio. `crear_extra` ya lo hacía así para los
-- extra-catálogo; el workflow A era el que discrepaba. El `update` de abajo
-- sana lo ya generado; el arreglo del INSERT va en el repositorio.
--
-- 2 · NO HABÍA DÓNDE GUARDAR EL PLAZO DE ENTREGA
--
-- "Lo requiero 10 días antes de la semana en que se usa" es la mitad útil del
-- módulo: sirve para pedir, no solo para saber. Ese plazo no es el mismo para
-- todos —el cemento llega en dos días, la cancelería en seis semanas— así que
-- vive en el insumo y no en una constante.
--
-- Nulable a propósito: son 780 insumos y nadie va a capturarlos de una
-- sentada. Mientras esté vacío manda el control global de la pantalla, que es
-- el default que Control de obra elige para toda la consulta. Se va llenando
-- por los que importan, y cada uno que se llena deja de usar el global.
-- ============================================================

update actividad
   set cant_programada = cant_base
 where cant_programada = 0
   and cant_base > 0;

alter table insumo
  add column dias_entrega smallint;

-- Cero es un dato —"llega el mismo día"— y por eso se admite; negativo sería
-- pedirlo después de usarlo. El tope superior no se acota: hay insumos de
-- importación que se piden con medio año.
alter table insumo
  add constraint ck_insumo_dias_entrega
  check (dias_entrega is null or dias_entrega >= 0);

comment on column insumo.dias_entrega is
  'Plazo de entrega en días: con cuánta anticipación hay que pedir este insumo para tenerlo cuando el cronograma lo pide (§7.3, §10.1). `null` = usa la anticipación global que elige quien consulta. Cero = llega el mismo día.';
