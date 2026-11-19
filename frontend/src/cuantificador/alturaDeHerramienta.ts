/**
 * La altura de la HERRAMIENTA de trazo de muro (3.00 m).
 *
 * El plano NO lee el driver `altura_estandar` del Paramétrico (ese driver es solo de las recetas de elementos). La altura de un muro
 * trazado sale, en este orden: la explícita del trazo (partes o altura tecleada) > la zona de losa > la ALTURA BASE del artefacto
 * (la plantilla de muro elegida) > esta constante, que fija la herramienta y se ve y se corrige en el panel de la línea.
 * Q1: solo lo que NACE sin altura la toma de aquí; un trazo ya guardado conserva la suya.
 */
export const ALTURA_DE_HERRAMIENTA_M = 3;

/** La altura base de una plantilla (artefacto) tal como la devuelve la API (`null` = sin altura: manda la de la herramienta). */
export function alturaBaseDeLaPlantilla(altura: string | number | null | undefined): number | null {
  const n = altura === null || altura === undefined ? NaN : Number(String(altura).replace(',', '.'));
  return Number.isFinite(n) && n > 0 ? n : null;
}
