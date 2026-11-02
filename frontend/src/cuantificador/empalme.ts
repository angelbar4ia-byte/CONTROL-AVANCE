/**
 * Empalme de versiones del plano (Fase 2): ver la versión anterior de un plano como un fantasma
 * sobre la nueva, alinearla y traer sus trazos. Las versiones de un plano son los planos de la obra
 * que comparten nombre (la más nueva tiene el número mayor).
 *
 * Funciones puras, sin DOM ni React.
 */

export interface PlanoVersionable {
  readonly id: string;
  readonly nombre: string;
  readonly version: number;
}

/** Las versiones **anteriores** del plano, de la más cercana a la más antigua. */
export function versionesAnteriores<T extends PlanoVersionable>(planos: readonly T[], actualId: string): T[] {
  const actual = planos.find((p) => p.id === actualId);
  if (!actual) return [];
  return planos
    .filter((p) => p.nombre === actual.nombre && p.version < actual.version)
    .sort((a, b) => b.version - a.version);
}

interface EnlaceConVigencia {
  readonly vigente: boolean;
}

/**
 * Los trazos de la versión anterior que todavía hay por traer: los que ya se trajeron en esta sesión
 * y los que perdieron todos sus enlaces (porque se trajeron antes) ya no estorban.
 */
export function porTraer<T extends { readonly id: string; readonly properties: { readonly enlaces: readonly EnlaceConVigencia[] } }>(
  trazos: readonly T[],
  traidos: ReadonlySet<string>,
): T[] {
  return trazos.filter((t) => {
    if (traidos.has(t.id)) return false;
    const enlaces = t.properties.enlaces;
    return enlaces.length === 0 || enlaces.some((e) => e.vigente);
  });
}

/** Un número escrito a mano (con coma o punto) o `0` si no es un número. */
export function desfaseDeTexto(texto: string): number {
  const n = Number(texto.trim().replace(',', '.'));
  return Number.isFinite(n) ? n : 0;
}
