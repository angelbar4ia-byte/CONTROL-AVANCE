/**
 * Multiselección de trazos (Mayús o Ctrl + clic). Hay un trazo **principal** —el que muestra su detalle— y los
 * **demás**; Mover, Girar y Borrar actúan sobre todos. Funciones puras: la pantalla guarda el resultado.
 */

export interface SeleccionDeTrazos {
  readonly principal: string | null;
  readonly extras: ReadonlySet<string>;
}

/**
 * Suma o quita `id` de la selección. Si ya estaba, se quita (y si era el principal, el siguiente lo releva); si no,
 * se suma (y si no había principal, él lo es).
 */
export function alternarEnSeleccion(principal: string | null, extras: ReadonlySet<string>, id: string): SeleccionDeTrazos {
  if (principal === null) return { principal: id, extras: new Set() };
  if (id === principal) {
    const [siguiente, ...resto] = [...extras];
    return { principal: siguiente ?? null, extras: new Set(resto) };
  }
  const nuevos = new Set(extras);
  if (nuevos.has(id)) nuevos.delete(id);
  else nuevos.add(id);
  return { principal, extras: nuevos };
}

/** Todos los trazos elegidos, el principal primero. */
export function trazosElegidos(principal: string | null, extras: ReadonlySet<string>): readonly string[] {
  return principal === null ? [] : [principal, ...[...extras].filter((id) => id !== principal)];
}
