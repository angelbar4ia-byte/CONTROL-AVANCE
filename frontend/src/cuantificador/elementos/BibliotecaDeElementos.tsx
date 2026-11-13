/**
 * La biblioteca de elementos: plegable por categoría y subcategoría. «Expandir todo» y «Contraer todo» abren o cierran
 * todas; por defecto abre la categoría del elemento elegido.
 */

import { ChevronDown, ChevronRight } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import type { CategoriaDeBiblioteca } from '@/api/generado/modelo';

interface Props {
  readonly categorias: readonly CategoriaDeBiblioteca[];
  readonly elegida: string | null;
  readonly onElegir: (clave: string) => void;
}

/** Las llaves plegables: `cat:<clave>` y `sub:<cat>/<sub>`. */
function llavesDe(categorias: readonly CategoriaDeBiblioteca[]): string[] {
  return categorias.flatMap((c) => [`cat:${c.clave}`, ...c.subcategorias.map((s) => `sub:${c.clave}/${s.clave}`)]);
}

/** Las llaves que hay que abrir para que se vea un elemento. */
function llavesDelElemento(categorias: readonly CategoriaDeBiblioteca[], clave: string | null): string[] {
  if (!clave) return [];
  for (const c of categorias) {
    for (const s of c.subcategorias) {
      if (s.elementos.some((e) => e.clave === clave)) return [`cat:${c.clave}`, `sub:${c.clave}/${s.clave}`];
    }
  }
  return [];
}

export function BibliotecaDeElementos({ categorias, elegida, onElegir }: Props) {
  const [abiertas, setAbiertas] = useState<ReadonlySet<string>>(() => new Set(llavesDelElemento(categorias, elegida)));
  const todas = useMemo(() => llavesDe(categorias), [categorias]);

  // Abre la categoría del elemento elegido, también cuando llega la biblioteca o cambia el elegido.
  useEffect(() => {
    const abrir = llavesDelElemento(categorias, elegida);
    if (abrir.length > 0) setAbiertas((prev) => new Set([...prev, ...abrir]));
  }, [categorias, elegida]);

  function alternar(llave: string) {
    setAbiertas((prev) => {
      const sig = new Set(prev);
      if (sig.has(llave)) sig.delete(llave);
      else sig.add(llave);
      return sig;
    });
  }

  return (
    <nav className="biblioteca" aria-label="Biblioteca de elementos">
      <div className="biblioteca__acciones">
        <button type="button" className="btn btn--sm" onClick={() => setAbiertas(new Set(todas))}>
          Expandir todo
        </button>
        <button type="button" className="btn btn--sm" onClick={() => setAbiertas(new Set())}>
          Contraer todo
        </button>
      </div>
      <ul className="biblioteca__lista">
        {categorias.map((c) => {
          const abierta = abiertas.has(`cat:${c.clave}`);
          return (
            <li key={c.clave}>
              <button
                type="button"
                className="biblioteca__rama"
                aria-expanded={abierta}
                onClick={() => alternar(`cat:${c.clave}`)}
              >
                {abierta ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
                <strong>{c.nombre}</strong>
                <span className="estacion__contador">{c.subcategorias.reduce((n, s) => n + s.elementos.length, 0)}</span>
              </button>
              {abierta && (
                <ul className="biblioteca__lista biblioteca__lista--hija">
                  {c.subcategorias.map((s) => {
                    const llave = `sub:${c.clave}/${s.clave}`;
                    const subAbierta = abiertas.has(llave);
                    return (
                      <li key={s.clave}>
                        <button type="button" className="biblioteca__rama" aria-expanded={subAbierta} onClick={() => alternar(llave)}>
                          {subAbierta ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
                          {s.nombre}
                          <span className="estacion__contador">{s.elementos.length}</span>
                        </button>
                        {subAbierta && (
                          <ul className="biblioteca__lista biblioteca__lista--hija">
                            {s.elementos.map((e) => (
                              <li key={e.clave}>
                                <button
                                  type="button"
                                  className={e.clave === elegida ? 'biblioteca__elemento is-activo' : 'biblioteca__elemento'}
                                  aria-current={e.clave === elegida ? 'true' : undefined}
                                  onClick={() => onElegir(e.clave)}
                                >
                                  <span className="mono">{e.clave}</span> {e.nombre}
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
