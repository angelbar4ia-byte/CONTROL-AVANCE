/**
 * Arrastrar una barra del Gantt del programa base: mover y estirar (§7.5, §7.6).
 *
 * ## Por qué mover una barra es cambiar un lag
 *
 * Un renglón de programa base **no tiene fecha ni desplazamiento propio**:
 * `ItemProgramaBasePeticion` lleva duración, tramos y dependencias, y nada más.
 * El arranque de una actividad es lo que dictan sus ligas —lo que resuelve
 * `colocar` (`planificacion.ts`)— y por eso "correr la actividad tres días a la
 * derecha" sólo se puede expresar de una manera en este contrato: **sumarle
 * tres días al lag de la dependencia que la está deteniendo**. Es la misma
 * conclusión que ya deja escrita `tramos.ts` cuando prohíbe un hueco delante
 * del primer tramo: *"un hueco por delante no es una interrupción, es una fecha
 * de inicio más tarde — exprésala con el lag de su dependencia"*.
 *
 * Consecuencia honesta: una actividad **sin predecesoras** no se puede mover.
 * Arranca el día 1 porque no hay nada que la detenga, y no existe campo donde
 * guardar un retraso. El arrastre se rechaza con esa explicación en vez de
 * moverla en pantalla y perder el gesto al guardar, que es la forma en que un
 * editor pierde la confianza del usuario.
 *
 * ## Cuál lag se toca cuando hay varias predecesoras
 *
 * El de la que **manda**: la que produce el arranque más tardío, que es el
 * `argmax` de la misma cuenta que hace `colocar`. Las demás no están
 * deteniendo nada y tocarlas no movería la barra. Al empujar hacia la derecha
 * eso basta; al jalar hacia la izquierda la barra se frena en cuanto otra
 * predecesora toma el relevo, que es exactamente lo que hace MS Project y lo
 * que el usuario espera al ver la barra "chocar" con algo.
 *
 * ## Estirar
 *
 * El borde derecho cambia la duración. Con la actividad partida no cambia "la
 * duración" —que es la suma de los tramos y no se captura (§7.6)—: cambia el
 * **último tramo**, y de eso ya se encarga `redimensionarTramo`, que recorta al
 * hueco legal en vez de producir un traslape que el backend rechazaría.
 *
 * ## Por qué el arrastre cuadricula al día
 *
 * El modelo admite medios días (`numeric(8,2)`, `MINIMO_TRAMO = 0.5`) y el
 * panel de la actividad los deja capturar. El arrastre no: a 16 px por día, un
 * cuarto de día son cuatro píxeles y nadie los apunta a propósito. Cuadricular
 * al día convierte el ratón en un instrumento que produce el número que el
 * usuario quería, y deja las fracciones para donde se teclean.
 *
 * Módulo puro (§12.11): decide qué acción del borrador produce un gesto, sin
 * tocar el DOM ni el estado de React.
 */

import type { Accion } from './borrador';
import type { Borrador, Caja, TipoLiga } from './grafo';
import type { Colocacion } from './planificacion';
import { redimensionarTramo, trabajoDe, type Tramo } from './tramos';

/** Qué se está arrastrando de la barra. */
export type ClaseArrastre = 'mover' | 'estirar';

/** Duración mínima que el arrastre puede dejar. Menos de un día se teclea. */
export const MINIMO_ARRASTRE_DIAS = 1;

export interface Arrastre {
  readonly cajaId: string;
  readonly clase: ClaseArrastre;
  /** Coordenada X del puntero al empezar, en px del lienzo. */
  readonly xInicial: number;
  /** Días de trabajo de la caja al empezar; el estirado se mide contra esto. */
  readonly diasInicial: number;
  /** Lag del cable que manda al empezar; el movimiento se mide contra esto. */
  readonly lagInicial: number;
  /** Predecesora que detiene a la caja; `null` si no tiene ninguna. */
  readonly ataduraId: string | null;
}

export type ResultadoArrastre =
  | { readonly ok: true; readonly accion: Accion; readonly dias: number }
  /** El gesto no cambia nada (aún no se movió un día completo). */
  | { readonly ok: false; readonly motivo: null }
  | { readonly ok: false; readonly motivo: string };

/**
 * El cable que está deteniendo a la caja: el que produce el arranque que
 * `colocar` le puso. Con varias predecesoras empatadas gana la primera, que es
 * la que el usuario tendió antes.
 *
 * Devuelve `null` si la caja no tiene predecesoras colocadas — arranca en el
 * día 0 porque nada la detiene.
 */
export function ataduraDe(
  caja: Caja,
  colocado: ReadonlyMap<string, Colocacion>,
): { readonly desde: string; readonly lagDias: number } | null {
  const propio = colocado.get(caja.id);
  if (!propio) return null;

  const span = propio.finDias - propio.inicioDias;
  let mejor: { desde: string; lagDias: number } | null = null;
  let mayor = Number.NEGATIVE_INFINITY;

  for (const cable of caja.entradas) {
    const previa = colocado.get(cable.desde);
    if (!previa) continue;
    const impuesto = inicioImpuesto(cable.tipo, cable.lagDias, previa, span);
    if (impuesto > mayor) {
      mayor = impuesto;
      mejor = { desde: cable.desde, lagDias: cable.lagDias };
    }
  }

  // Ninguna predecesora llega a empujar la barra de su día 0: no la detiene
  // nadie, aunque tenga cables (todos con lag negativo, por ejemplo).
  if (mejor === null || mayor < propio.inicioDias) return null;
  return mejor;
}

/** La misma cuenta que hace `colocar` para una liga; ver `planificacion.ts`. */
function inicioImpuesto(
  tipo: TipoLiga,
  lag: number,
  previa: Colocacion,
  span: number,
): number {
  switch (tipo) {
    case 'FS':
      return previa.finDias + lag;
    case 'SS':
      return previa.inicioDias + lag;
    case 'FF':
      return previa.finDias + lag - span;
    case 'SF':
      return previa.inicioDias + lag - span;
  }
}

/** Estado inicial del arrastre, capturado al presionar el botón del ratón. */
export function empezarArrastre(
  caja: Caja,
  colocado: ReadonlyMap<string, Colocacion>,
  clase: ClaseArrastre,
  xInicial: number,
): Arrastre {
  const atadura = ataduraDe(caja, colocado);
  return {
    cajaId: caja.id,
    clase,
    xInicial,
    diasInicial: trabajoDe(caja.duracionDias ?? 0, caja.tramos),
    lagInicial: atadura?.lagDias ?? 0,
    ataduraId: atadura?.desde ?? null,
  };
}

/**
 * La acción que produce el arrastre, dado cuántos días (ya cuadriculados) se
 * ha desplazado el puntero desde donde empezó.
 *
 * Devuelve `{ ok: false, motivo: null }` cuando el gesto todavía no cambia
 * nada: es el caso normal a mitad de un arrastre y no tiene por qué avisar de
 * nada. Un `motivo` con texto sí es algo que explicarle al usuario.
 */
export function resolverArrastre(
  borrador: Borrador,
  arrastre: Arrastre,
  deltaDias: number,
): ResultadoArrastre {
  const caja = borrador.cajas.find((c) => c.id === arrastre.cajaId);
  if (!caja) return { ok: false, motivo: null };

  if (arrastre.clase === 'estirar') return estirar(caja, arrastre, deltaDias);
  return mover(caja, arrastre, deltaDias);
}

function mover(caja: Caja, arrastre: Arrastre, deltaDias: number): ResultadoArrastre {
  if (arrastre.ataduraId === null) {
    return {
      ok: false,
      motivo:
        'Esta actividad no depende de ninguna otra: arranca el día 1 y no hay dónde ' +
        'guardarle un retraso. Tiéndele una precedencia y muévela con su lag (§7.5).',
    };
  }
  if (deltaDias === 0) return { ok: false, motivo: null };

  const lagDias = redondear(arrastre.lagInicial + deltaDias);
  if (lagDias === caja.entradas.find((c) => c.desde === arrastre.ataduraId)?.lagDias) {
    return { ok: false, motivo: null };
  }

  return {
    ok: true,
    dias: deltaDias,
    accion: { tipo: 'lag', desde: arrastre.ataduraId, hasta: caja.id, lagDias },
  };
}

function estirar(caja: Caja, arrastre: Arrastre, deltaDias: number): ResultadoArrastre {
  if (deltaDias === 0) return { ok: false, motivo: null };

  // Partida, el borde derecho es el del último tramo: la duración total no se
  // captura, se deriva de los tramos (§7.6).
  if (caja.tramos.length > 0) {
    const ultimo = caja.tramos.length - 1;
    const actual = caja.tramos[ultimo];
    if (!actual) return { ok: false, motivo: null };
    const tramos = redimensionarTramo(
      caja.tramos,
      ultimo,
      Math.max(MINIMO_ARRASTRE_DIAS, actual.duracionDias + deltaDias),
    );
    // `redimensionarTramo` recorta al hueco legal y devuelve un arreglo nuevo
    // aunque el recorte deje el mismo número, así que la igualdad se compara
    // por valor: despachar un cambio vacío gastaría un paso de deshacer.
    if (mismosTramos(tramos, caja.tramos)) return { ok: false, motivo: null };
    return { ok: true, dias: deltaDias, accion: { tipo: 'tramos', cajaId: caja.id, tramos } };
  }

  const duracionDias = Math.max(
    MINIMO_ARRASTRE_DIAS,
    redondear(arrastre.diasInicial + deltaDias),
  );
  if (duracionDias === caja.duracionDias) return { ok: false, motivo: null };
  return { ok: true, dias: deltaDias, accion: { tipo: 'duracion', cajaId: caja.id, duracionDias } };
}

/**
 * Días cuadriculados que se ha movido el puntero. `pxPorDia` viene del eje, así
 * que el mismo desplazamiento en píxeles produce más o menos días según el
 * zoom, que es lo que hace que el arrastre se sienta igual de fino a cualquier
 * escala.
 */
export function diasDeDesplazamiento(deltaPx: number, pxPorDia: number): number {
  if (pxPorDia <= 0) return 0;
  const dias = deltaPx / pxPorDia;
  // Se redondea **alejándose del cero**, no con `Math.round` a secas: en
  // JavaScript `Math.round(-2.5)` es `-2` y `Math.round(2.5)` es `3`, así que
  // el mismo arrastre daría tres días a la derecha y dos a la izquierda. Una
  // asimetría de un día en un gesto simétrico se siente como un fallo del
  // ratón.
  return Math.sign(dias) * Math.round(Math.abs(dias));
}

/**
 * Ancho de la zona sensible del borde de la barra, en px.
 *
 * Es fijo y no proporcional al zoom: es el tamaño del gesto del usuario, no del
 * dato. A 6 px/día una barra de dos días mide 12 px y las dos asas se comerían
 * la barra entera, así que quien dibuja recorta el asa a un tercio del ancho.
 */
export const ASA_PX = 6;

/**
 * Ventana que la barra ocupa **mientras** se arrastra, antes de soltar.
 *
 * El arrastre no despacha en cada `pointermove`: cada acción del borrador apila
 * su propio paso de deshacer (`borrador.ts`), así que correr una barra tres
 * días dejaría tres pasos atrás en vez de uno, y recolocar el grafo entero en
 * cada píxel redibujaría 155 renglones sesenta veces por segundo. Se despacha
 * una sola acción al soltar, y mientras tanto lo que se ve es esto: la misma
 * ventana corrida o estirada, sin tocar el modelo.
 */
export function previsualizar(
  puesto: Colocacion,
  clase: ClaseArrastre,
  deltaDias: number,
): Colocacion {
  if (clase === 'estirar') {
    const span = Math.max(MINIMO_ARRASTRE_DIAS, puesto.finDias - puesto.inicioDias + deltaDias);
    return { inicioDias: puesto.inicioDias, finDias: puesto.inicioDias + span };
  }
  // Nada arranca antes que el programa: el mismo recorte que hace `colocar`.
  const inicioDias = Math.max(0, puesto.inicioDias + deltaDias);
  return { inicioDias, finDias: inicioDias + (puesto.finDias - puesto.inicioDias) };
}

/** ¿Son los mismos tramos, valor por valor? */
function mismosTramos(a: readonly Tramo[], b: readonly Tramo[]): boolean {
  return (
    a.length === b.length &&
    a.every(
      (tramo, i) =>
        tramo.duracionDias === b[i]?.duracionDias && tramo.offsetDias === b[i]?.offsetDias,
    )
  );
}

/** Dos decimales, los que la columna `numeric(8,2)` guarda de verdad. */
function redondear(valor: number): number {
  return Math.round(valor * 100) / 100;
}
