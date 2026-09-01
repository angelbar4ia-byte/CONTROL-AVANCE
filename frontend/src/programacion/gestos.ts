/**
 * Las herramientas que **cambian el programa**, traducidas a acciones del
 * borrador (§7.5, §7.6).
 *
 * ## Qué hace este módulo y por qué está separado del menú
 *
 * El menú de herramientas es un puñado de botones; lo que cada botón significa
 * en el modelo no es obvio en ninguno de los casos interesantes. "Aplazar tres
 * días" no es escribir una fecha —un renglón de programa base no tiene ninguna
 * (§7.5)—, es sumarle tres al lag de la precedencia que lo detiene. "Dividir"
 * no parte la actividad en dos: parte su tramo en dos y deja una pausa, porque
 * el concepto sigue teniendo una cantidad y un avance (§7.6). "Vincular" puede
 * cerrar un ciclo que el backend rechazaría con un 422 sobre el programa
 * entero.
 *
 * Toda esa traducción vive aquí, fuera de los componentes, y devuelve **o las
 * acciones o el motivo por el que no hay ninguna**. Un botón que no puede hacer
 * su trabajo tiene que decir por qué; deshabilitarlo en silencio deja al
 * usuario probando combinaciones para adivinar qué le falta, y moverlo en
 * pantalla y perder el gesto al guardar es peor todavía.
 *
 * ## La regla que atraviesa todo: sólo cabe lo que cabe en el POST
 *
 * `ItemProgramaBasePeticion` lleva duración, tramos y dependencias. Nada más.
 * No hay fecha, no hay desplazamiento propio y **no hay restricciones de
 * calendario**. Por eso "No iniciar antes de" no es aquí una restricción que se
 * guarde: se resuelve en el momento como un lag, y su docstring lo dice, porque
 * ofrecer un campo que el POST va a ignorar es peor que no ofrecerlo.
 *
 * ## Un gesto, un paso de deshacer
 *
 * Varias herramientas producen más de una acción —reiniciar una actividad quita
 * sus tramos y pone a cero los lags de todas sus predecesoras—. Se devuelven en
 * una lista y quien despacha usa `despacharVarias`, que las apila como un solo
 * paso atrás. Deshacer tiene que devolver el programa a donde estaba antes de
 * pulsar el botón, no a la mitad del botón.
 *
 * Módulo puro (§12.11).
 */

import { ataduraDe } from './arrastre';
import type { Accion } from './borrador';
import { alcanzablesDesde } from './ciclos';
import {
  aristas,
  buscarCable,
  esRenglon,
  spanDeCaja,
  type Borrador,
  type Caja,
  type TipoLiga,
} from './grafo';
import type { Colocacion } from './planificacion';
import {
  MINIMO_PAUSA,
  MINIMO_TRAMO,
  alargarPausa,
  partirTramo,
  tramosVisibles,
  unirTramo,
  type Tramo,
} from './tramos';

/**
 * Lo que produce una herramienta: las acciones a despachar, o la explicación.
 *
 * No hay un tercer caso "no pasó nada y da igual": si el usuario pulsó un botón
 * y el programa no cambió, hay algo que contarle.
 */
export type Gesto =
  | { readonly ok: true; readonly acciones: readonly Accion[] }
  | { readonly ok: false; readonly motivo: string };

function no(motivo: string): Gesto {
  return { ok: false, motivo };
}

function si(...acciones: readonly Accion[]): Gesto {
  return { ok: true, acciones };
}

function cajaDe(borrador: Borrador, cajaId: string): Caja | null {
  return borrador.cajas.find((caja) => caja.id === cajaId) ?? null;
}

/* ================================================================== *
 * Programar
 * ================================================================== */

/**
 * Corre la actividad `dias` días, positivo hacia adelante.
 *
 * Es el mismo camino que el arrastre del Gantt (`arrastre.ts`) y por el mismo
 * motivo: la única forma de expresar "más tarde" en un contrato sin fechas es
 * el lag de la precedencia que produce el arranque. De ahí la consecuencia
 * incómoda pero honesta: una actividad sin predecesoras no se puede aplazar,
 * porque arranca el día 1 y no hay dónde guardarle el retraso.
 */
export function aplazar(
  borrador: Borrador,
  colocado: ReadonlyMap<string, Colocacion>,
  cajaId: string,
  dias: number,
): Gesto {
  const caja = cajaDe(borrador, cajaId);
  if (!caja) return no('La actividad ya no está en el programa.');
  if (!esRenglon(caja)) {
    return no('La actividad no tiene duración capturada: todavía no está en el programa (§7.5).');
  }
  if (dias === 0) return no('Aplazar cero días no cambia nada.');

  const atadura = ataduraDe(caja, colocado);
  if (atadura === null) {
    return no(
      'Esta actividad no depende de ninguna otra: arranca el día 1 y no hay dónde guardarle ' +
        'un retraso. Tiéndele una precedencia y muévela con su lag (§7.5).',
    );
  }

  return si({
    tipo: 'lag',
    desde: atadura.desde,
    hasta: caja.id,
    lagDias: redondear(atadura.lagDias + dias),
  });
}

/**
 * "No iniciar antes de": lleva el arranque de la actividad al día `dia`.
 *
 * ## Por qué no es una restricción
 *
 * En MS Project esto es una **constraint** con fecha propia que sobrevive a los
 * cambios: si la predecesora se adelanta, la actividad se queda donde la fecha
 * dice. Aquí no hay dónde guardar una: `ItemProgramaBasePeticion` no tiene
 * campo de restricción, y añadirle uno que el `POST` ignorase sería fingir que
 * el programa recuerda algo que no recuerda.
 *
 * Lo que sí cabe —y es lo que hace esta función— es resolverla **en el momento**
 * como lag: se calcula cuánto hay que aplazar para que la actividad arranque el
 * día pedido y se guarda esa cantidad. La diferencia se nota después: si la
 * predecesora se mueve, la actividad se mueve con ella, porque lo guardado es
 * la distancia y no la fecha. Es un desplazamiento, no un ancla, y se rotula
 * así en la barra.
 *
 * Sólo aplaza. Traer una actividad hacia atrás no es lo que "no iniciar antes
 * de" pide, y con un lag negativo el resultado además dependería de qué otra
 * predecesora tomara el relevo.
 */
export function noIniciarAntesDe(
  borrador: Borrador,
  colocado: ReadonlyMap<string, Colocacion>,
  cajaId: string,
  dia: number,
): Gesto {
  const puesto = colocado.get(cajaId);
  if (!puesto) {
    return no('La actividad no está colocada: captúrale una duración primero (§7.5).');
  }
  const delta = Math.round(dia - puesto.inicioDias);
  if (delta <= 0) {
    return no(
      `La actividad ya arranca el día ${puesto.inicioDias + 1}, que no es antes del día ` +
        `${dia + 1}. No hay nada que aplazar.`,
    );
  }
  return aplazar(borrador, colocado, cajaId, delta);
}

/**
 * Fija la duración de una actividad continua.
 *
 * Con la actividad partida la duración **es** la suma de sus tramos (§7.6) y no
 * se captura: dejar las dos cifras editables garantiza que un día discrepen, y
 * es el mismo criterio que ya aplica la celda de la tabla.
 */
export function fijarDuracion(borrador: Borrador, cajaId: string, dias: number | null): Gesto {
  const caja = cajaDe(borrador, cajaId);
  if (!caja) return no('La actividad ya no está en el programa.');
  if (caja.tramos.length > 0) {
    return no(
      'La actividad está interrumpida: su duración es la suma de sus tramos. Une los tramos ' +
        'o cambia el último estirando su barra (§7.6).',
    );
  }
  if (dias !== null && dias <= 0) {
    return no('La duración de un renglón del programa es positiva; vacíala para sacarlo (§7.5).');
  }
  return si({ tipo: 'duracion', cajaId, duracionDias: dias });
}

/**
 * Fija el día en que la actividad **cierra**, que es el último día trabajado.
 *
 * Se traduce a duración, que es lo que el contrato guarda: una actividad que
 * arranca el día 1 y cierra el día 3 dura tres días, no cuatro. Por eso la
 * cuenta lleva el `+ 1` y por eso la columna Término de la tabla rotula
 * `finDias - 1`.
 */
export function fijarTermino(
  borrador: Borrador,
  colocado: ReadonlyMap<string, Colocacion>,
  cajaId: string,
  diaTermino: number,
): Gesto {
  const puesto = colocado.get(cajaId);
  if (!puesto) return no('La actividad no está colocada: captúrale una duración primero (§7.5).');
  const dias = Math.round(diaTermino - puesto.inicioDias) + 1;
  if (dias <= 0) {
    return no('El término quedaría antes del arranque. Mueve primero el inicio (§7.5).');
  }
  return fijarDuracion(borrador, cajaId, dias);
}

/**
 * Parte la actividad en el día `enDia` —medido desde su arranque— y deja una
 * pausa.
 *
 * El corte cae dentro del tramo que ocupe ese día; en una actividad continua no
 * hay más que uno, y `tramosVisibles` lo materializa para que este código no
 * tenga dos caminos. `partirTramo` recorta el corte a los bordes legales, así
 * que lo único que hay que comprobar aquí es que la actividad dé para dos
 * pedazos: partir una de medio día produciría dos tramos de cero, que el
 * backend rechaza (§7.6).
 */
export function dividir(
  borrador: Borrador,
  cajaId: string,
  enDia: number,
  pausaDias: number = MINIMO_PAUSA,
): Gesto {
  const caja = cajaDe(borrador, cajaId);
  if (!caja) return no('La actividad ya no está en el programa.');
  if (!esRenglon(caja)) {
    return no('La actividad no tiene duración capturada: no hay nada que partir (§7.5).');
  }

  const base = tramosVisibles(caja.duracionDias ?? 0, caja.tramos);
  const indice = tramoEnDia(base, enDia);
  const objetivo = base[indice];
  if (!objetivo) return no('El día en que se pide partir cae en una pausa, no en el trabajo.');
  if (objetivo.duracionDias <= MINIMO_TRAMO * 2) {
    return no(
      `El tramo dura ${objetivo.duracionDias} d y no da para dos pedazos de ` +
        `${MINIMO_TRAMO} d. Alárgalo antes de partirlo (§7.6).`,
    );
  }

  const tramos = partirTramo(base, indice, enDia - objetivo.offsetDias, pausaDias);
  if (mismosTramos(tramos, caja.tramos)) return no('El corte no cambia los tramos.');
  return si({ tipo: 'tramos', cajaId, tramos });
}

/**
 * Alarga la pausa que precede al tramo `indice`: "Interrumpir".
 *
 * Es lo que sigue a "Dividir" y no lo mismo: dividir abre la pausa mínima donde
 * no había ninguna, interrumpir la hace tan larga como haga falta. La actividad
 * tiene que estar ya partida —una continua no tiene pausa que alargar— y por
 * eso se explica en vez de partirla de oficio: partir por su cuenta decidiría
 * por el usuario en qué día se corta, que es justamente lo que él sabe.
 */
export function interrumpir(
  borrador: Borrador,
  cajaId: string,
  indice: number,
  dias: number,
): Gesto {
  const caja = cajaDe(borrador, cajaId);
  if (!caja) return no('La actividad ya no está en el programa.');
  if (caja.tramos.length < 2) {
    return no('La actividad es continua: divídela primero para que tenga una pausa (§7.6).');
  }
  if (indice < 1 || indice >= caja.tramos.length) {
    return no('Ese tramo no tiene una pausa delante: el primero arranca en el día 0 (§7.6).');
  }

  const tramos = alargarPausa(caja.tramos, indice, dias);
  if (mismosTramos(tramos, caja.tramos)) {
    return no(`La pausa ya está en su mínimo de ${MINIMO_PAUSA} d y no se puede acortar más.`);
  }
  return si({ tipo: 'tramos', cajaId, tramos });
}

/**
 * Cierra la pausa entre el tramo `indice` y el siguiente.
 *
 * Al quedar un solo tramo la actividad vuelve a ser continua: `aplicar`
 * normaliza a lista vacía y deja la duración en la suma, que es la invariante
 * que el backend comprueba (§7.6).
 */
export function unirTramos(borrador: Borrador, cajaId: string, indice: number): Gesto {
  const caja = cajaDe(borrador, cajaId);
  if (!caja) return no('La actividad ya no está en el programa.');
  if (caja.tramos.length < 2) return no('La actividad no está partida: no hay tramos que unir.');
  if (indice < 0 || indice >= caja.tramos.length - 1) {
    return no('No hay un tramo siguiente con el que unir ése.');
  }
  return si({ tipo: 'tramos', cajaId, tramos: unirTramo(caja.tramos, indice) });
}

/**
 * Devuelve una actividad a su forma **sin ajustes**: continua y en su arranque
 * natural.
 *
 * Quita los tramos —cerrando las pausas, sin tocar los días de trabajo, que es
 * lo que el usuario capturó— y pone a cero el lag de todas sus precedencias, lo
 * que la devuelve a arrancar en cuanto sus predecesoras se lo permiten. Lo que
 * **no** toca es la duración ni los vínculos: reiniciar no es borrar, es
 * deshacer los acomodos manuales.
 */
export function reiniciarActividad(borrador: Borrador, cajaId: string): Gesto {
  const caja = cajaDe(borrador, cajaId);
  if (!caja) return no('La actividad ya no está en el programa.');

  const acciones = accionesDeReinicio(caja);
  if (acciones.length === 0) {
    return no('La actividad ya está continua y en su arranque natural: no hay nada que reiniciar.');
  }
  return { ok: true, acciones };
}

/** Lo mismo sobre el programa completo, como un solo paso de deshacer. */
export function reiniciarPrograma(borrador: Borrador): Gesto {
  const acciones = borrador.cajas.flatMap(accionesDeReinicio);
  if (acciones.length === 0) {
    return no('El programa ya está sin interrupciones ni desplazamientos manuales.');
  }
  return { ok: true, acciones };
}

function accionesDeReinicio(caja: Caja): readonly Accion[] {
  const acciones: Accion[] = [];
  if (caja.tramos.length > 0) {
    acciones.push({ tipo: 'tramos', cajaId: caja.id, tramos: [] });
  }
  for (const cable of caja.entradas) {
    if (cable.lagDias === 0) continue;
    acciones.push({ tipo: 'lag', desde: cable.desde, hasta: caja.id, lagDias: 0 });
  }
  return acciones;
}

/* ================================================================== *
 * Vínculos
 * ================================================================== */

/**
 * Tiende la precedencia `desde → hasta`.
 *
 * El ciclo se comprueba **antes** de despachar y no sólo dentro de `aplicar`:
 * aquélla es la red que impide construir un estado ilegal aunque alguien se
 * salte la comprobación, y devuelve el borrador sin tocar —en silencio—. Quien
 * tiene que explicarle al usuario por qué el vínculo no se pegó es esta capa,
 * porque un botón que no hace nada y no dice nada es indistinguible de uno
 * roto. El backend responde 422 sobre el programa **entero** si hay un ciclo
 * (§6), así que enterarse aquí es la diferencia entre un aviso y perder la
 * sesión.
 */
export function vincular(
  borrador: Borrador,
  desde: string,
  hasta: string,
  tipoLiga: TipoLiga,
  lagDias = 0,
): Gesto {
  if (desde === '' || hasta === '') return no('Falta elegir los dos extremos del vínculo.');
  if (desde === hasta) {
    return no('Una actividad no puede depender de sí misma: es un ciclo de largo 1 (§6).');
  }
  if (!cajaDe(borrador, desde) || !cajaDe(borrador, hasta)) {
    return no('Uno de los dos extremos ya no está en el árbol.');
  }
  if (buscarCable(borrador, desde, hasta) !== null) {
    return no('Ese vínculo ya existe. Cambia su tipo o su retraso en vez de tenderlo otra vez.');
  }
  if (alcanzablesDesde(aristas(borrador), hasta).has(desde)) {
    return no(
      'Ese vínculo cerraría un ciclo de precedencias: ya se puede llegar de la sucesora a la ' +
        'predecesora. El backend rechazaría el programa completo (§6).',
    );
  }
  return si({ tipo: 'conectar', desde, hasta, tipoLiga, lagDias });
}

export function desvincular(borrador: Borrador, desde: string, hasta: string): Gesto {
  if (buscarCable(borrador, desde, hasta) === null) return no('Ese vínculo ya no existe.');
  return si({ tipo: 'desconectar', desde, hasta });
}

/**
 * Le da la vuelta al vínculo conservando tipo y lag.
 *
 * A diferencia de retipar —que no toca el conjunto de aristas—, invertir sí lo
 * cambia y por eso puede cerrar un ciclo: si ya había otro camino de la
 * predecesora a la sucesora, darle la vuelta lo cierra. Se comprueba **sin** el
 * cable actual, que si no el camino que se busca sería él mismo.
 */
export function invertirVinculo(borrador: Borrador, desde: string, hasta: string): Gesto {
  if (buscarCable(borrador, desde, hasta) === null) return no('Ese vínculo ya no existe.');
  if (buscarCable(borrador, hasta, desde) !== null) {
    return no('El vínculo contrario ya existe: invertirlo dejaría los dos y eso es un ciclo (§6).');
  }
  const restantes = aristas(borrador).filter(
    (arista) => !(arista.desde === desde && arista.hasta === hasta),
  );
  if (alcanzablesDesde(restantes, desde).has(hasta)) {
    return no(
      'Invertirlo cerraría un ciclo: hay otro camino que ya lleva de la predecesora a la ' +
        'sucesora (§6).',
    );
  }
  return si({ tipo: 'invertir', desde, hasta });
}

/** Cambia el tipo de un vínculo entre los cuatro de MS Project (§7.5). */
export function retipar(
  borrador: Borrador,
  desde: string,
  hasta: string,
  tipoLiga: TipoLiga,
): Gesto {
  const cable = buscarCable(borrador, desde, hasta);
  if (cable === null) return no('Ese vínculo ya no existe.');
  if (cable.tipo === tipoLiga) return no(`El vínculo ya es ${tipoLiga}.`);
  return si({ tipo: 'ligar', desde, hasta, tipoLiga });
}

/**
 * Cambia el retraso de un vínculo. Admite negativo: un lag de −2 en una `FS` es
 * el solape de dos días que el jefe de obra llama "entrar antes de que acabe".
 */
export function retrasar(
  borrador: Borrador,
  desde: string,
  hasta: string,
  lagDias: number,
): Gesto {
  const cable = buscarCable(borrador, desde, hasta);
  if (cable === null) return no('Ese vínculo ya no existe.');
  const redondeado = redondear(lagDias);
  if (cable.lagDias === redondeado) return no('El retraso ya es ése.');
  return si({ tipo: 'lag', desde, hasta, lagDias: redondeado });
}

/**
 * Predecesoras que se le pueden tender a `cajaId` sin cerrar un ciclo.
 *
 * Se resuelve con una sola pasada de alcanzabilidad y no con una pregunta por
 * candidata: son ~155 nodos y la lista se recalcula en cada render del menú.
 * Se excluyen la propia caja, las que ya son predecesoras suyas y todo lo que
 * cuelga de ella hacia adelante.
 */
export function candidatasAPredecesora(
  borrador: Borrador,
  cajaId: string,
): readonly Caja[] {
  const caja = cajaDe(borrador, cajaId);
  if (!caja) return [];
  const cerradas = alcanzablesDesde(aristas(borrador), cajaId);
  const yaLigadas = new Set(caja.entradas.map((cable) => cable.desde));
  return borrador.cajas.filter(
    (otra) => !cerradas.has(otra.id) && !yaLigadas.has(otra.id),
  );
}

/* ================================================================== *
 * Auxiliares
 * ================================================================== */

/**
 * Índice del tramo que ocupa el día `enDia`, medido desde el arranque de la
 * actividad. Un día que cae en una pausa devuelve el tramo **anterior**, que es
 * el que el usuario ve a la izquierda de donde hizo clic.
 */
function tramoEnDia(tramos: readonly Tramo[], enDia: number): number {
  let indice = 0;
  for (let i = 0; i < tramos.length; i += 1) {
    const tramo = tramos[i];
    if (tramo && tramo.offsetDias <= enDia) indice = i;
  }
  return indice;
}

/** Día del programa a la mitad de la actividad; el corte que propone el menú. */
export function diaMedioDe(caja: Caja): number {
  return Math.round(spanDeCaja(caja) / 2);
}

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
