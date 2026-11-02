/**
 * Deshacer y rehacer: una pila de acciones, cada una con cómo se deshace y cómo se rehace.
 *
 * Es del que está trabajando y de esta sesión: no se guarda, y al cambiar de plano se vacía. Una
 * acción nueva descarta lo que se podía rehacer, como en cualquier programa de dibujo. Si deshacer
 * falla (el servidor dice que no, porque el trazo se aprobó entretanto), la acción se queda donde
 * estaba y el error sube a quien llamó.
 */

export interface Accion {
  /** Lo que se hizo, para decirlo: «Trazo guardado», «Hueco abierto»… */
  readonly etiqueta: string;
  readonly deshacer: () => Promise<void>;
  readonly rehacer: () => Promise<void>;
}

export interface Historial {
  /** Anota una acción ya hecha. Lo que se podía rehacer se descarta. */
  registrar: (accion: Accion) => void;
  deshacer: () => Promise<Accion | null>;
  rehacer: () => Promise<Accion | null>;
  limpiar: () => void;
  /** Lo siguiente que se deshace / rehace, o `null` si no hay. */
  siguienteAdeshacer: () => Accion | null;
  siguienteArehacer: () => Accion | null;
}

/** Cuántas acciones se recuerdan: lo viejo se olvida. */
const MAXIMO = 100;

export function crearHistorial(): Historial {
  let pasadas: Accion[] = [];
  let futuras: Accion[] = [];
  return {
    registrar(accion) {
      pasadas = [...pasadas, accion].slice(-MAXIMO);
      futuras = [];
    },
    async deshacer() {
      const accion = pasadas[pasadas.length - 1];
      if (!accion) return null;
      await accion.deshacer(); // si falla, sigue como estaba
      pasadas = pasadas.slice(0, -1);
      futuras = [...futuras, accion];
      return accion;
    },
    async rehacer() {
      const accion = futuras[futuras.length - 1];
      if (!accion) return null;
      await accion.rehacer();
      futuras = futuras.slice(0, -1);
      pasadas = [...pasadas, accion];
      return accion;
    },
    limpiar() {
      pasadas = [];
      futuras = [];
    },
    siguienteAdeshacer: () => pasadas[pasadas.length - 1] ?? null,
    siguienteArehacer: () => futuras[futuras.length - 1] ?? null,
  };
}
