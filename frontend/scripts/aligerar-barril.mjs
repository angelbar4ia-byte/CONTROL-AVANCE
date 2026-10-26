/**
 * Aligera el barril de modelos que genera Orval.
 *
 * Orval escribe `src/api/generado/modelo/index.ts` con un `export * from
 * "./x"` por cada esquema del contrato: ~740. Casi todos son interfaces o
 * alias de tipo, es decir, **no tienen código en ejecución**, pero el servidor
 * de desarrollo de Vite no lo sabe: sirve el barril, ve 740 `export *` y el
 * navegador pide los 740 módulos —que salen vacíos— antes de pintar nada. Con
 * varias sesiones abiertas a la vez agota los recursos de Chromium
 * (`net::ERR_INSUFFICIENT_RESOURCES`, ver `playwright.config.ts`).
 *
 * `export type * from` (TypeScript 5) se borra por completo al compilar: el
 * navegador no pide esos módulos. Solo conservan `export *` los archivos que sí
 * exportan un valor (los `const` de las enumeraciones, que se usan en
 * ejecución: `MedidaCuantificacion.area`).
 *
 * Los tipos se resuelven igual —`tsc` ve los mismos nombres—; cambia solo lo
 * que llega al navegador. Se corre después de Orval (`npm run api:generar`) y
 * es idempotente.
 */

import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const carpeta = new URL('../src/api/generado/modelo/', import.meta.url).pathname;
const indice = join(carpeta, 'index.ts');

const modulos = readdirSync(carpeta)
  .filter((f) => f.endsWith('.ts') && f !== 'index.ts')
  .map((f) => f.slice(0, -3))
  .sort();

/** ¿El módulo exporta algo que existe en ejecución (const/function/class/enum)? */
function tieneValores(modulo) {
  const codigo = readFileSync(join(carpeta, `${modulo}.ts`), 'utf8');
  return /^export\s+(const|let|var|function|class|enum)\s/m.test(codigo);
}

const original = readFileSync(indice, 'utf8');
// Lo que no sea una línea `export … from` (la cabecera de Orval) se conserva.
const cabecera = original
  .split('\n')
  .filter((l) => !/^export\s+(type\s+)?\*\s+from\s/.test(l))
  .join('\n')
  .trimEnd();

const lineas = modulos.map((m) =>
  tieneValores(m) ? `export * from "./${m}";` : `export type * from "./${m}";`,
);

writeFileSync(indice, `${cabecera}\n\n${lineas.join('\n')}\n`);

const conValores = lineas.filter((l) => !l.startsWith('export type')).length;
console.log(
  `Barril aligerado: ${modulos.length} módulos, ${conValores} con valores en ejecución ` +
    `y ${modulos.length - conValores} solo de tipos.`,
);
