/**
 * Toda clase que se pinta existe en el sistema de diseño (§12.10).
 *
 * ## El fallo que esta prueba habría evitado
 *
 * `AppShell` pintó durante varias fases `nav-item`, `topbar-actions`,
 * `badge-ok` y `sidebar-brand`. La hoja las llama `sidebar__item`,
 * `topbar__actions`, `badge--ok` y `topbar__brand`. **El navegador no avisa**
 * de una clase que no existe: no aplica nada y sigue. El sidebar quedó sin
 * fondo, sin marca de activo y sin hover, y el layout aguantó solo por el
 * `grid` de `.app` — lo bastante como para que nadie lo llamara "roto".
 *
 * Ningún typecheck ni ninguna prueba de reglas puede ver eso: `className` es
 * una cadena. Esto sí.
 *
 * ## Qué NO comprueba
 *
 * Que la pantalla se vea bien. Comprueba que las clases usadas estén
 * definidas, que es la mitad verificable sin un navegador. Lo otro se mira.
 *
 * ## Por qué la lista de excepciones está vacía
 *
 * Si mañana hace falta una clase de una librería externa, va aquí con su
 * motivo escrito. Una excepción sin motivo es la forma en que una prueba así
 * deja de servir.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * `src/` desde el directorio de trabajo, que Vitest fija en `frontend/`.
 *
 * No se deriva de `import.meta.url`: Vitest transforma el módulo y esa URL no
 * siempre es `file:`, así que la resolución falla en Windows por un motivo que
 * no tiene nada que ver con lo que esta prueba vigila. Que la ruta sea la
 * correcta lo comprueba el primer `it`.
 */
const RAIZ = join(process.cwd(), 'src');
const CSS = join(RAIZ, 'estilos', 'obractrl-design.css');

/** Clases de terceros o generadas que no viven en la hoja. Ninguna, por ahora. */
const EXCEPCIONES = new Set<string>();

function archivosTsx(directorio: string): string[] {
  return readdirSync(directorio).flatMap((entrada) => {
    const ruta = join(directorio, entrada);
    if (statSync(ruta).isDirectory()) {
      // `api/generado` es de Orval y no pinta nada; `pruebas` es esto mismo.
      if (entrada === 'generado' || entrada === 'pruebas') return [];
      return archivosTsx(ruta);
    }
    return ruta.endsWith('.tsx') ? [ruta] : [];
  });
}

/**
 * Clases definidas en la hoja.
 *
 * Se leen los selectores tal cual: basta con que la clase aparezca en alguno,
 * porque lo que se busca es un nombre inventado, no una regla mal anidada.
 */
function clasesDefinidas(): Set<string> {
  const css = readFileSync(CSS, 'utf8');
  return new Set([...css.matchAll(/\.([A-Za-z][\w-]*)/g)].map((m) => m[1]!));
}

export interface UsoDeClase {
  readonly clase: string;
  readonly archivo: string;
}

/**
 * ¿Este texto parece el nombre de una clase del sistema de diseño?
 *
 * Se exige que sea **compuesto** —que lleve `-` o `_`— y ahí está el criterio
 * entero: en esta hoja toda clase que se puede escribir mal es compuesta
 * (`sidebar__item`, `badge--ok`, `empty-title`, `is-num`), y las de una sola
 * palabra son cuatro o cinco tan centrales que un typo se ve al abrir la
 * pantalla. A cambio, el análisis deja de confundir con clases los nombres de
 * variable y los valores de un `===`, que es lo que un lector de expresiones
 * hecho con expresiones regulares no puede distinguir.
 *
 * Un fragmento suelto de interpolación (`badge--`) tampoco cuenta: no es una
 * clase, es la mitad de una.
 */
function pareceClase(texto: string): boolean {
  return (
    /^[A-Za-z][\w-]*$/.test(texto) &&
    /[-_]/.test(texto) &&
    !/[-_]$/.test(texto)
  );
}

/**
 * Clases que un archivo pinta.
 *
 * Antes de partir por espacios se borran dos cosas que no son clases aunque
 * estén dentro de un `className`:
 *
 * - las **interpolaciones** (`${...}`), que son código;
 * - los **operandos de comparación** (`enVivo === 'en-vivo'`), que son valores
 *   de dominio y aparecen justo al lado de las clases en cada ternario.
 */
export function clasesDe(fuente: string): string[] {
  const limpia = fuente
    .replace(/\$\{[^}]*\}/g, ' ')
    .replace(/(?:===|!==|==|!=)\s*['"`][^'"`]*['"`]/g, ' ')
    .replace(/['"`][^'"`]*['"`]\s*(?:===|!==|==|!=)/g, ' ');

  const salida: string[] = [];

  for (const [, bloque] of limpia.matchAll(/className=\{?[`"']([\s\S]*?)[`"']\}?/g)) {
    for (const clase of (bloque ?? '').split(/\s+/)) {
      if (pareceClase(clase)) salida.push(clase);
    }
  }

  // Las cadenas de un `className={...}` con lógica —ternarios y las funciones
  // de `NavLink`— son el otro lugar donde vive una clase, y es justo donde
  // estaba `nav-item`.
  for (const [, bloque] of limpia.matchAll(/className=\{([\s\S]*?)\}\s*\n?\s*(?:>|\/>|[a-z-]+=)/g)) {
    for (const [, literal] of (bloque ?? '').matchAll(/['"]([^'"]*)['"]/g)) {
      for (const clase of (literal ?? '').split(/\s+/)) {
        if (pareceClase(clase)) salida.push(clase);
      }
    }
  }

  return salida;
}

describe('sistema de diseño', () => {
  const definidas = clasesDefinidas();
  const archivos = archivosTsx(RAIZ);

  it('encuentra la hoja y las pantallas', () => {
    // Si el parser deja de encontrar archivos, todo lo de abajo pasaría por
    // vacío — que es la forma más común en que una prueba así muere.
    expect(definidas.size).toBeGreaterThan(100);
    expect(archivos.length).toBeGreaterThan(15);
  });

  it('no pinta ninguna clase que la hoja no defina', () => {
    const huerfanas: UsoDeClase[] = [];

    for (const archivo of archivos) {
      const fuente = readFileSync(archivo, 'utf8');
      for (const clase of new Set(clasesDe(fuente))) {
        if (!definidas.has(clase) && !EXCEPCIONES.has(clase)) {
          huerfanas.push({ clase, archivo: relative(RAIZ, archivo) });
        }
      }
    }

    expect(huerfanas).toEqual([]);
  });

  it('el shell usa los nombres BEM de la hoja, no unos parecidos', () => {
    // Los cuatro que estuvieron mal. Se nombran uno por uno porque son los
    // que se rompen al copiar markup de otro lado.
    const shell = readFileSync(join(RAIZ, 'shell', 'AppShell.tsx'), 'utf8');
    const usadas = new Set(clasesDe(shell));

    for (const clase of ['sidebar__item', 'topbar__actions', 'badge--ok', 'topbar__brand']) {
      expect(usadas.has(clase)).toBe(true);
    }
    for (const inventada of ['nav-item', 'topbar-actions', 'badge-ok', 'sidebar-brand']) {
      expect(usadas.has(inventada)).toBe(false);
    }
  });
});

describe('responsive', () => {
  const css = readFileSync(CSS, 'utf8');

  it('el sidebar tiene cómo abrirse cuando el CSS lo esconde', () => {
    // El `@media` de 880px esconde `.sidebar` y la muestra con
    // `.app.is-mobile-nav-open`. Si nadie renderiza esa clase ni el botón que
    // la activa, por debajo de 880px la app se queda **sin navegación**: eso
    // fue exactamente lo que pasó hasta la revisión de pantallas.
    expect(css).toContain('.app.is-mobile-nav-open .sidebar');

    const shell = readFileSync(join(RAIZ, 'shell', 'AppShell.tsx'), 'utf8');
    expect(shell).toContain('is-mobile-nav-open');
    expect(shell).toContain('topbar__nav-toggle');
  });

  it('la barra de tabs del móvil existe en los dos lados', () => {
    expect(css).toContain('.mobile-tabbar');
    const shell = readFileSync(join(RAIZ, 'shell', 'AppShell.tsx'), 'utf8');
    expect(shell).toContain('mobile-tabbar');
  });

  it('hay un tramo intermedio, no solo escritorio y teléfono', () => {
    // Una laptop chica o una tablet apaisada es el ancho más común en obra, y
    // saltaba de 232px de sidebar a nada.
    expect(css).toContain('@media (max-width: 1180px)');
  });

  it('una tabla ancha se desplaza dentro de su caja, no empuja la página', () => {
    expect(css).toMatch(/\.table-wrap\s*\{\s*overflow-x:\s*auto/);
  });
});
