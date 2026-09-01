/**
 * Colocación relativa de las cajas del borrador, **solo para avisar** (§7.6).
 *
 * ## Qué no es esto
 *
 * No es el CPM. La ruta crítica, la holgura, el desfase y las fechas reales
 * los calcula el motor del backend (`domain/programacion/cpm.py`) contra el
 * calendario laboral de la obra, y llegan resueltos por la API; el editor de
 * programas base ni siquiera tiene fechas: un programa base es una plantilla
 * de duraciones sin origen de tiempo. Lo que hay aquí es una **pasada hacia
 * adelante en días relativos** —día 0 = arranque del programa— cuyo único
 * consumidor es el aviso visual del párrafo siguiente. Nada de esto se guarda
 * ni se muestra como fecha.
 *
 * ## El aviso que justifica el módulo
 *
 * La decisión de producto es explícita: las dependencias son a nivel
 * **actividad**, no a nivel tramo. Cuando una actividad está partida —el muro
 * que trabaja dos semanas, para para que se cuele la losa, y sigue con los
 * pretiles— la intención de quien liga la losa al muro es meterla en la
 * **pausa**. Pero la liga se resuelve contra la actividad entera, así que
 * nada impide que la losa caiga encima de un tramo de trabajo del muro. El
 * editor lo señala y no reacomoda nada: quien decide si eso es un problema es
 * el jefe de obra, no el programa.
 *
 * Por eso solo se avisa cuando la predecesora **tiene tramos**. Sin tramos no
 * hay pausa en la que caber, y un traslape entre una actividad y su sucesora
 * `SS` es lo normal, no un aviso.
 *
 * Módulo puro (§12.11).
 */

import { aristas, spanDeCaja, type Borrador, type Caja } from './grafo';
import { ordenTopologico } from './ciclos';
import { finDe } from './tramos';

export interface Colocacion {
  /** Día relativo en que arranca la caja; el arranque del programa es el 0. */
  readonly inicioDias: number;
  /** Cierre en calendario: `inicio + span` (con tramos, el fin del último). */
  readonly finDias: number;
}

/**
 * Arranque más temprano de cada caja, en días relativos.
 *
 * Las cuatro ligas se resuelven como en MS Project, sobre el **span** de la
 * sucesora (lo que ocupa en calendario), no sobre sus días de trabajo:
 *
 *   - `FS` la sucesora arranca al cerrar la predecesora,
 *   - `SS` arrancan juntas,
 *   - `FF` la sucesora no cierra antes que la predecesora,
 *   - `SF` la sucesora no cierra antes de que la predecesora arranque.
 *
 * Un `lag` negativo puede empujar un arranque antes del día 0; se recorta a 0,
 * porque nada arranca antes que el programa. El motor real hace lo mismo con
 * la fecha de inicio de la obra.
 *
 * Con un ciclo no hay orden en que recorrer el grafo: devuelve un mapa vacío.
 * El aviso de ciclo es de `ciclos.ts` y es el que la pantalla muestra.
 */
export function colocar(borrador: Borrador): ReadonlyMap<string, Colocacion> {
  const cajas = borrador.cajas;
  const orden = ordenTopologico(
    cajas.map((caja) => caja.id),
    aristas(borrador),
  );
  if (orden === null) return new Map();

  const porId = new Map(cajas.map((caja) => [caja.id, caja]));
  const colocado = new Map<string, Colocacion>();

  for (const id of orden) {
    const caja = porId.get(id);
    if (!caja) continue;
    const span = spanDeCaja(caja);

    let inicio = 0;
    for (const cable of caja.entradas) {
      const predecesora = colocado.get(cable.desde);
      if (!predecesora) continue;
      const lag = cable.lagDias;
      const minimo =
        cable.tipo === 'FS'
          ? predecesora.finDias + lag
          : cable.tipo === 'SS'
            ? predecesora.inicioDias + lag
            : cable.tipo === 'FF'
              ? predecesora.finDias + lag - span
              : predecesora.inicioDias + lag - span;
      inicio = Math.max(inicio, minimo);
    }

    const inicioDias = Math.max(inicio, 0);
    colocado.set(id, { inicioDias, finDias: inicioDias + span });
  }

  return colocado;
}

export interface TraslapeConTrabajo {
  /** Caja sucesora que cae encima del trabajo de su predecesora. */
  readonly cajaId: string;
  readonly predecesoraId: string;
  /** Días de trabajo de la predecesora que la sucesora pisa. */
  readonly diasPisados: number;
}

/**
 * Sucesoras que caen sobre un tramo de **trabajo** de su predecesora partida.
 *
 * Se compara la ventana en calendario de la sucesora contra cada tramo de
 * trabajo de la predecesora; lo que cae en las pausas no cuenta, que es
 * justamente el caso que el usuario quiere. El traslape se mide en días y se
 * ignora si es despreciable, para no señalar el contacto exacto de una `FS`
 * (la sucesora arranca el mismo día en que cierra el tramo).
 */
export function traslapesConTrabajo(
  borrador: Borrador,
  colocado: ReadonlyMap<string, Colocacion>,
): readonly TraslapeConTrabajo[] {
  const porId = new Map(borrador.cajas.map((caja) => [caja.id, caja]));
  const encontrados: TraslapeConTrabajo[] = [];

  for (const caja of borrador.cajas) {
    const propio = colocado.get(caja.id);
    if (!propio) continue;

    for (const cable of caja.entradas) {
      const predecesora = porId.get(cable.desde);
      const suyo = colocado.get(cable.desde);
      // Sin tramos no hay pausa que aprovechar: el traslape es lo normal.
      if (!predecesora || !suyo || predecesora.tramos.length === 0) continue;

      let pisados = 0;
      for (const tramo of predecesora.tramos) {
        const inicioTramo = suyo.inicioDias + tramo.offsetDias;
        const finTramo = suyo.inicioDias + finDe(tramo);
        pisados += Math.max(
          0,
          Math.min(propio.finDias, finTramo) - Math.max(propio.inicioDias, inicioTramo),
        );
      }

      if (pisados > TOLERANCIA_DIAS) {
        encontrados.push({
          cajaId: caja.id,
          predecesoraId: cable.desde,
          diasPisados: Math.round(pisados * 100) / 100,
        });
      }
    }
  }

  return encontrados;
}

/** Menos de esto es el redondeo de un `numeric(8,2)`, no un traslape. */
const TOLERANCIA_DIAS = 0.01;

/** Días que ocupa el programa completo; 0 si no hay nada colocado. */
export function duracionDelPrograma(colocado: ReadonlyMap<string, Colocacion>): number {
  let total = 0;
  for (const { finDias } of colocado.values()) total = Math.max(total, finDias);
  return total;
}

/** Etiqueta legible de una caja para los mensajes de aviso. */
export function nombreCorto(caja: Caja | undefined): string {
  if (!caja) return '—';
  return caja.clave ? `${caja.clave} · ${caja.nombre}` : caja.nombre;
}
