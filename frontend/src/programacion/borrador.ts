/**
 * Borrador local del editor y su historial de deshacer/rehacer (§7.5).
 *
 * ## Por qué un borrador y no autoguardado
 *
 * Cada `POST /programas-base` **versiona**: crea la versión siguiente del
 * prototipo y retira la vigente. Guardar en cada arrastre dejaría cuarenta
 * versiones de una tarde de trabajo y ninguna forma de saber cuál es la buena.
 * Así que el canvas edita todo en memoria y el `POST` sale una sola vez, al
 * presionar Guardar: **una versión por sesión de trabajo, no una por gesto**.
 * El precio es que cerrar la pestaña pierde lo no guardado, y la pantalla
 * avisa de eso.
 *
 * ## Cómo se agrupan los gestos en el historial
 *
 * Arrastrar una caja dispara decenas de `mover` por segundo. Empujar cada uno
 * al historial haría que deshacer retrocediera píxel a píxel, que no es lo que
 * nadie espera. Por eso `mover` **reemplaza** el presente sin apilar, y el
 * punto de deshacer lo pone `marcar()` al arrancar el arrastre: un arrastre
 * completo es un solo paso atrás. El resto de las acciones —conectar, cambiar
 * duración, partir un tramo— sí apila una por una, porque cada una es un gesto
 * completo del usuario.
 *
 * Las acciones que el modelo no admite (un cable que cerraría un ciclo, un
 * tramo que se traslaparía) **no** se rechazan aquí con un error: `aplicar`
 * devuelve el borrador sin tocar. Quien tiene que explicarle al usuario por
 * qué el cable no se pegó es la pantalla, antes de despachar, con
 * `cerrariaCiclo`; esta capa solo garantiza que un estado ilegal no se pueda
 * construir aunque alguien se salte esa comprobación.
 *
 * Módulo puro (§12.11).
 */

import { cerrariaCiclo } from './ciclos';
import type { Posicion } from './acomodo';
import { aristas, type Borrador, type Caja, type TipoLiga } from './grafo';
import { normalizarTramos, trabajoDe, type Tramo } from './tramos';

export type Accion =
  | { readonly tipo: 'mover'; readonly cajaId: string; readonly x: number; readonly y: number }
  | { readonly tipo: 'acomodar'; readonly posiciones: ReadonlyMap<string, Posicion> }
  | {
      readonly tipo: 'duracion';
      readonly cajaId: string;
      readonly duracionDias: number | null;
    }
  | { readonly tipo: 'frente'; readonly cajaId: string; readonly frenteId: string | null }
  | {
      readonly tipo: 'conectar';
      readonly desde: string;
      readonly hasta: string;
      readonly tipoLiga: TipoLiga;
      readonly lagDias?: number;
    }
  | { readonly tipo: 'desconectar'; readonly desde: string; readonly hasta: string }
  | {
      readonly tipo: 'ligar';
      readonly desde: string;
      readonly hasta: string;
      readonly tipoLiga: TipoLiga;
    }
  | { readonly tipo: 'lag'; readonly desde: string; readonly hasta: string; readonly lagDias: number }
  | { readonly tipo: 'tramos'; readonly cajaId: string; readonly tramos: readonly Tramo[] }
  | { readonly tipo: 'nombre'; readonly nombre: string };

function conCaja(
  borrador: Borrador,
  cajaId: string,
  cambio: (caja: Caja) => Caja,
): Borrador {
  let toco = false;
  const cajas = borrador.cajas.map((caja) => {
    if (caja.id !== cajaId) return caja;
    const nueva = cambio(caja);
    if (nueva !== caja) toco = true;
    return nueva;
  });
  return toco ? { ...borrador, cajas } : borrador;
}

/**
 * Aplica una acción. Pura: devuelve un borrador nuevo, o el mismo si la acción
 * no cambia nada o el modelo no la admite.
 */
export function aplicar(borrador: Borrador, accion: Accion): Borrador {
  switch (accion.tipo) {
    case 'mover':
      return conCaja(borrador, accion.cajaId, (caja) =>
        caja.x === accion.x && caja.y === accion.y
          ? caja
          : { ...caja, x: accion.x, y: accion.y },
      );

    case 'acomodar': {
      let toco = false;
      const cajas = borrador.cajas.map((caja) => {
        const posicion = accion.posiciones.get(caja.id);
        if (!posicion || (posicion.x === caja.x && posicion.y === caja.y)) return caja;
        toco = true;
        return { ...caja, x: posicion.x, y: posicion.y };
      });
      return toco ? { ...borrador, cajas } : borrador;
    }

    case 'duracion':
      return conCaja(borrador, accion.cajaId, (caja) => {
        // Con tramos la duración no se captura: es la suma de los tramos, y
        // dejar las dos cifras editables garantiza que un día discrepen (§7.6).
        if (caja.tramos.length > 0) return caja;
        const duracionDias =
          accion.duracionDias === null || accion.duracionDias <= 0
            ? null
            : redondear(accion.duracionDias);
        return caja.duracionDias === duracionDias ? caja : { ...caja, duracionDias };
      });

    case 'frente':
      return conCaja(borrador, accion.cajaId, (caja) =>
        caja.frenteId === accion.frenteId ? caja : { ...caja, frenteId: accion.frenteId },
      );

    case 'conectar': {
      const existe = borrador.cajas.some(
        (caja) =>
          caja.id === accion.hasta &&
          caja.entradas.some((cable) => cable.desde === accion.desde),
      );
      const conocidas = new Set(borrador.cajas.map((caja) => caja.id));
      if (
        existe ||
        !conocidas.has(accion.desde) ||
        !conocidas.has(accion.hasta) ||
        cerrariaCiclo(aristas(borrador), accion.desde, accion.hasta)
      ) {
        return borrador;
      }
      return conCaja(borrador, accion.hasta, (caja) => ({
        ...caja,
        entradas: [
          ...caja.entradas,
          { desde: accion.desde, tipo: accion.tipoLiga, lagDias: accion.lagDias ?? 0 },
        ],
      }));
    }

    case 'desconectar':
      return conCaja(borrador, accion.hasta, (caja) => {
        const entradas = caja.entradas.filter((cable) => cable.desde !== accion.desde);
        return entradas.length === caja.entradas.length ? caja : { ...caja, entradas };
      });

    case 'ligar':
      return conCaja(borrador, accion.hasta, (caja) => ({
        ...caja,
        entradas: caja.entradas.map((cable) =>
          cable.desde === accion.desde ? { ...cable, tipo: accion.tipoLiga } : cable,
        ),
      }));

    case 'lag':
      return conCaja(borrador, accion.hasta, (caja) => ({
        ...caja,
        entradas: caja.entradas.map((cable) =>
          cable.desde === accion.desde
            ? { ...cable, lagDias: redondear(accion.lagDias) }
            : cable,
        ),
      }));

    case 'tramos':
      return conCaja(borrador, accion.cajaId, (caja) => {
        const tramos = normalizarTramos(accion.tramos);
        // La duración pasa a ser la suma de los tramos: es la invariante que
        // el backend comprueba, y derivarla aquí es el gesto natural del
        // editor (§7.6).
        if (tramos.length > 0) {
          return { ...caja, tramos, duracionDias: redondear(trabajoDe(0, tramos)) };
        }
        // Al volver a continua —unir hasta dejar un solo tramo— la duración es
        // la del tramo que quedó, no la que hubiera antes de partir.
        const suma = redondear(trabajoDe(0, accion.tramos));
        return { ...caja, tramos, duracionDias: suma > 0 ? suma : caja.duracionDias };
      });

    case 'nombre':
      return borrador.nombre === accion.nombre
        ? borrador
        : { ...borrador, nombre: accion.nombre };
  }
}

export interface Historial {
  readonly pasado: readonly Borrador[];
  readonly presente: Borrador;
  readonly futuro: readonly Borrador[];
}

/** Cuántos pasos atrás se guardan; más que eso solo retiene memoria. */
const PROFUNDIDAD = 60;

export function historialInicial(borrador: Borrador): Historial {
  return { pasado: [], presente: borrador, futuro: [] };
}

function apilar(historial: Historial, presente: Borrador): Historial {
  return {
    pasado: [...historial.pasado, historial.presente].slice(-PROFUNDIDAD),
    presente,
    futuro: [],
  };
}

/**
 * Despacha una acción sobre el historial.
 *
 * `mover` reemplaza el presente sin apilar —el punto de deshacer del arrastre
 * lo puso `marcar()` al empezar—; el resto apila. Una acción que no cambia
 * nada tampoco apila: deshacer no debe gastarse en pasos vacíos.
 */
export function despachar(historial: Historial, accion: Accion): Historial {
  const presente = aplicar(historial.presente, accion);
  if (presente === historial.presente) return historial;
  if (accion.tipo === 'mover') return { ...historial, presente, futuro: [] };
  return apilar(historial, presente);
}

/**
 * Deja un punto de deshacer con el estado actual, sin cambiar nada.
 *
 * Es lo que convierte un arrastre entero —decenas de `mover`— en un solo paso
 * atrás: se llama al empezar a arrastrar, no al soltar.
 */
export function marcar(historial: Historial): Historial {
  return apilar(historial, historial.presente);
}

export function puedeDeshacer(historial: Historial): boolean {
  return historial.pasado.length > 0;
}

export function puedeRehacer(historial: Historial): boolean {
  return historial.futuro.length > 0;
}

export function deshacer(historial: Historial): Historial {
  const previo = historial.pasado[historial.pasado.length - 1];
  if (!previo) return historial;
  return {
    pasado: historial.pasado.slice(0, -1),
    presente: previo,
    futuro: [historial.presente, ...historial.futuro],
  };
}

export function rehacer(historial: Historial): Historial {
  const siguiente = historial.futuro[0];
  if (!siguiente) return historial;
  return {
    pasado: [...historial.pasado, historial.presente],
    presente: siguiente,
    futuro: historial.futuro.slice(1),
  };
}

function redondear(valor: number): number {
  return Math.round(valor * 100) / 100;
}
