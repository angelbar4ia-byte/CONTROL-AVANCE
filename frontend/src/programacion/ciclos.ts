/**
 * Ciclos y orden topológico del grafo de precedencias (§6, §7.5).
 *
 * ## Por qué esto vive en el cliente
 *
 * El motor del CPM es del backend y sigue siéndolo: `POST /programas-base`
 * valida el cronograma completo y responde 422 **sin escribir nada** si hay
 * dependencias circulares. Pero en un canvas el ciclo se crea en el instante
 * en que se suelta un cable, y descubrirlo media hora después —al guardar—
 * significa perder la sesión entera de trabajo y además no saber cuál de los
 * treinta cables lo provocó. Detectarlo al tender el cable convierte un error
 * de servidor en un cable que sencillamente no se deja soltar.
 *
 * Esto **no** recalcula la ruta crítica ni la holgura: eso es del motor y
 * llega resuelto por la API. Aquí solo se responde "¿este cable cierra un
 * ciclo?" y "¿en qué orden se puede recorrer el grafo?".
 *
 * Módulo puro (§12.11).
 */

import type { Arista } from './grafo';

interface Adyacencia {
  readonly sucesoras: ReadonlyMap<string, readonly string[]>;
  readonly grados: ReadonlyMap<string, number>;
}

function adyacencia(nodos: readonly string[], aristas: readonly Arista[]): Adyacencia {
  const conocidos = new Set(nodos);
  const sucesoras = new Map<string, string[]>(nodos.map((id) => [id, []]));
  const grados = new Map<string, number>(nodos.map((id) => [id, 0]));

  for (const arista of aristas) {
    // Una arista con un extremo fuera del conjunto no es del grafo que se
    // está recorriendo (una ref a un nodo de otra versión, o a un nodo que ya
    // no está en el árbol): se ignora en vez de inventarle un nodo.
    if (!conocidos.has(arista.desde) || !conocidos.has(arista.hasta)) continue;
    sucesoras.get(arista.desde)?.push(arista.hasta);
    grados.set(arista.hasta, (grados.get(arista.hasta) ?? 0) + 1);
  }

  return { sucesoras, grados };
}

/**
 * Orden topológico (predecesoras antes que sucesoras), o `null` si el grafo
 * tiene un ciclo.
 *
 * Kahn con cola estable: a igualdad de grado se respeta el orden en que
 * llegaron los nodos, para que el auto-acomodo no baraje las cajas de una
 * pasada a otra sin que nada haya cambiado.
 */
export function ordenTopologico(
  nodos: readonly string[],
  aristas: readonly Arista[],
): readonly string[] | null {
  const { sucesoras, grados } = adyacencia(nodos, aristas);
  const restantes = new Map(grados);
  const cola = nodos.filter((id) => (restantes.get(id) ?? 0) === 0);
  const orden: string[] = [];

  for (let i = 0; i < cola.length; i += 1) {
    const actual = cola[i]!;
    orden.push(actual);
    for (const sucesora of sucesoras.get(actual) ?? []) {
      const grado = (restantes.get(sucesora) ?? 0) - 1;
      restantes.set(sucesora, grado);
      if (grado === 0) cola.push(sucesora);
    }
  }

  return orden.length === nodos.length ? orden : null;
}

/** ¿Hay camino de `origen` a `destino` siguiendo el sentido de las precedencias? */
export function alcanzable(
  aristas: readonly Arista[],
  origen: string,
  destino: string,
): boolean {
  if (origen === destino) return true;

  const sucesoras = new Map<string, string[]>();
  for (const arista of aristas) {
    const lista = sucesoras.get(arista.desde);
    if (lista) lista.push(arista.hasta);
    else sucesoras.set(arista.desde, [arista.hasta]);
  }

  const vistos = new Set<string>([origen]);
  const pila = [origen];
  while (pila.length > 0) {
    const actual = pila.pop()!;
    for (const sucesora of sucesoras.get(actual) ?? []) {
      if (sucesora === destino) return true;
      if (vistos.has(sucesora)) continue;
      vistos.add(sucesora);
      pila.push(sucesora);
    }
  }
  return false;
}

/**
 * ¿Tender el cable `desde → hasta` cerraría un ciclo?
 *
 * Es `true` también cuando los dos extremos son el mismo nodo: una actividad
 * que depende de sí misma es un ciclo de largo 1 y el backend lo rechaza
 * igual.
 */
export function cerrariaCiclo(
  aristas: readonly Arista[],
  desde: string,
  hasta: string,
): boolean {
  if (desde === hasta) return true;
  // El cable nuevo va de `desde` a `hasta`; cierra ciclo si ya se podía llegar
  // de `hasta` a `desde` por el camino contrario.
  return alcanzable(aristas, hasta, desde);
}

/**
 * Un ciclo del grafo, en orden de recorrido y cerrando sobre su primer nodo
 * (`['a', 'b', 'a']`), o `null` si no hay ninguno.
 *
 * Sirve para explicar un programa que ya venía torcido —importado de una
 * versión anterior—, no para la validación al tender un cable, que es
 * `cerrariaCiclo`.
 */
export function buscarCiclo(
  nodos: readonly string[],
  aristas: readonly Arista[],
): readonly string[] | null {
  const { sucesoras } = adyacencia(nodos, aristas);
  const estado = new Map<string, 'abierto' | 'cerrado'>();
  const camino: string[] = [];

  function visitar(id: string): readonly string[] | null {
    estado.set(id, 'abierto');
    camino.push(id);

    for (const sucesora of sucesoras.get(id) ?? []) {
      const marca = estado.get(sucesora);
      if (marca === 'abierto') {
        const desde = camino.indexOf(sucesora);
        return [...camino.slice(desde), sucesora];
      }
      if (marca === undefined) {
        const ciclo = visitar(sucesora);
        if (ciclo) return ciclo;
      }
    }

    camino.pop();
    estado.set(id, 'cerrado');
    return null;
  }

  for (const id of nodos) {
    if (estado.has(id)) continue;
    const ciclo = visitar(id);
    if (ciclo) return ciclo;
  }
  return null;
}
