/**
 * El árbol del presupuesto como carpetas: nivel → etapa → concepto (D-565).
 *
 * Se elige con la casilla de cada concepto (o la de una carpeta, que elige todo lo
 * que contiene) y lo elegido alimenta la herramienta «Solo los trazos de los
 * conceptos elegidos». Las carpetas se abren y se cierran; la búsqueda abre lo que
 * coincide. Cada concepto muestra lo medido contra lo base y, si hace falta,
 * sus matrices internas (D-583).
 */

import { ChevronRight, Layers, Folder, FolderOpen } from 'lucide-react';
import { useMemo, useState } from 'react';

import { fmtNum } from '@/lib/formato';
import { idsDeEtapa, idsDeNivel, type HojaDelArbol, type NivelDelArbol } from './arbol';
import { MatricesDeActividad } from './MatricesDeActividad';

interface Props {
  readonly arbol: readonly NivelDelArbol[];
  readonly elegidos: ReadonlySet<string>;
  readonly onElegir: (ids: readonly string[], marcar: boolean) => void;
  readonly actividadFocoId?: string;
}

const norm = (t: string) => t.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

function Casilla({
  ids,
  elegidos,
  etiqueta,
  onElegir,
}: {
  readonly ids: readonly string[];
  readonly elegidos: ReadonlySet<string>;
  readonly etiqueta: string;
  readonly onElegir: (ids: readonly string[], marcar: boolean) => void;
}) {
  const n = ids.filter((id) => elegidos.has(id)).length;
  const todos = ids.length > 0 && n === ids.length;
  return (
    <input
      type="checkbox"
      className="arbol__casilla"
      aria-label={`Elegir ${etiqueta}`}
      checked={todos}
      ref={(el) => {
        if (el) el.indeterminate = n > 0 && !todos;
      }}
      onChange={() => onElegir(ids, !todos)}
    />
  );
}

export function ArbolPresupuesto({ arbol, elegidos, onElegir, actividadFocoId }: Props) {
  // Todo abierto al empezar: el árbol de una obra cabe y lo que se busca no debe esconderse.
  const [cerradas, setCerradas] = useState<ReadonlySet<string>>(new Set());
  const [conMatrices, setConMatrices] = useState<ReadonlySet<string>>(new Set());
  const [busqueda, setBusqueda] = useState('');

  const q = norm(busqueda.trim());
  const coincide = (h: HojaDelArbol) => q === '' || norm(h.etiqueta).includes(q);

  const alternar = (clave: string) =>
    setCerradas((actual) => {
      const siguiente = new Set(actual);
      if (siguiente.has(clave)) siguiente.delete(clave);
      else siguiente.add(clave);
      return siguiente;
    });

  const todasLasClaves = useMemo(
    () => arbol.flatMap((n) => [n.clave, ...n.etapas.map((e) => `${n.clave}/${e.clave}`)]),
    [arbol],
  );
  const algunaCerrada = todasLasClaves.some((c) => cerradas.has(c));

  return (
    <div className="arbol">
      <div className="arbol__herramientas">
        <input
          className="input arbol__buscar"
          type="search"
          placeholder="Buscar concepto"
          aria-label="Buscar en el presupuesto"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
        <button
          type="button"
          className="btn-icono"
          aria-label={algunaCerrada ? 'Expandir todo el árbol' : 'Contraer todo el árbol'}
          title={algunaCerrada ? 'Expandir todo' : 'Contraer todo'}
          onClick={() => setCerradas(algunaCerrada ? new Set() : new Set(todasLasClaves))}
        >
          <Layers size={15} aria-hidden />
        </button>
      </div>

      <ul className="arbol__lista" role="tree" aria-label="Árbol de la cuantificación">
        {arbol.map((nivel) => {
          const abierto = q !== '' || !cerradas.has(nivel.clave);
          return (
            <li key={nivel.clave} role="treeitem" aria-label={nivel.etiqueta} aria-expanded={abierto} aria-selected={false}>
              <div className="arbol__fila arbol__fila--carpeta">
                <button
                  type="button"
                  className="arbol__giro"
                  aria-label={`${abierto ? 'Contraer' : 'Expandir'} ${nivel.etiqueta}`}
                  onClick={() => alternar(nivel.clave)}
                >
                  <ChevronRight size={13} className={abierto ? 'is-abierto' : undefined} aria-hidden />
                </button>
                <Casilla ids={idsDeNivel(nivel)} elegidos={elegidos} etiqueta={nivel.etiqueta} onElegir={onElegir} />
                {abierto ? <FolderOpen size={14} aria-hidden /> : <Folder size={14} aria-hidden />}
                <span className="arbol__texto">{nivel.etiqueta}</span>
                <span className="arbol__cuenta">
                  {nivel.medidas} de {nivel.total} medidos
                </span>
              </div>
              {abierto && (
                <ul role="group" className="arbol__hijos">
                  {nivel.etapas.map((etapa) => {
                    const clave = `${nivel.clave}/${etapa.clave}`;
                    const hojas = etapa.hojas.filter(coincide);
                    if (hojas.length === 0) return null;
                    const abiertaEtapa = q !== '' || !cerradas.has(clave);
                    return (
                      <li key={clave} role="treeitem" aria-label={etapa.etiqueta} aria-expanded={abiertaEtapa} aria-selected={false}>
                        <div className="arbol__fila arbol__fila--carpeta">
                          <button
                            type="button"
                            className="arbol__giro"
                            aria-label={`${abiertaEtapa ? 'Contraer' : 'Expandir'} ${etapa.etiqueta}`}
                            onClick={() => alternar(clave)}
                          >
                            <ChevronRight size={13} className={abiertaEtapa ? 'is-abierto' : undefined} aria-hidden />
                          </button>
                          <Casilla ids={idsDeEtapa(etapa)} elegidos={elegidos} etiqueta={etapa.etiqueta} onElegir={onElegir} />
                          {abiertaEtapa ? <FolderOpen size={14} aria-hidden /> : <Folder size={14} aria-hidden />}
                          <span className="arbol__texto">{etapa.etiqueta}</span>
                          <span className="arbol__cuenta">
                            {etapa.medidas} de {etapa.hojas.length}
                          </span>
                        </div>
                        {abiertaEtapa && (
                          <ul role="group" className="arbol__hijos">
                            {hojas.map((hoja) => (
                              <li
                                key={hoja.id}
                                role="treeitem"
                                aria-selected={elegidos.has(hoja.id)}
                                aria-label={hoja.etiqueta}
                              >
                                <div
                                  className={[
                                    'arbol__fila arbol__fila--hoja',
                                    elegidos.has(hoja.id) && 'is-elegida',
                                    hoja.id === actividadFocoId && 'is-foco',
                                  ]
                                    .filter(Boolean)
                                    .join(' ')}
                                >
                                  <span className="arbol__giro" aria-hidden />
                                  <Casilla ids={[hoja.id]} elegidos={elegidos} etiqueta={hoja.etiqueta} onElegir={onElegir} />
                                  <span className="arbol__texto" title={hoja.etiqueta}>
                                    {hoja.etiqueta}
                                  </span>
                                  <span className="arbol__meta">
                                  {!hoja.medido && <span className="badge badge--outline">Sin medir</span>}
                                  {hoja.porRevisar > 0 && (
                                    <span className="badge badge--warn">{hoja.porRevisar} por revisar</span>
                                  )}
                                  <span
                                    className="arbol__cuenta"
                                    title={
                                      hoja.medido
                                        ? `Medido ${fmtNum(hoja.medida)} de ${fmtNum(hoja.base)} · dif. ${fmtNum(hoja.diferencia)}`
                                        : `Base ${fmtNum(hoja.base)}`
                                    }
                                  >
                                    {hoja.medido ? fmtNum(hoja.medida) : '—'} / {fmtNum(hoja.base)}
                                  </span>
                                  <button
                                    type="button"
                                    className="btn btn--ghost btn--sm arbol__matrices"
                                    aria-expanded={conMatrices.has(hoja.id)}
                                    aria-label={`Matrices de ${hoja.etiqueta}`}
                                    onClick={() =>
                                      setConMatrices((actual) => {
                                        const siguiente = new Set(actual);
                                        if (siguiente.has(hoja.id)) siguiente.delete(hoja.id);
                                        else siguiente.add(hoja.id);
                                        return siguiente;
                                      })
                                    }
                                  >
                                    {conMatrices.has(hoja.id) ? '▾ Matrices' : '▸ Matrices'}
                                  </button>
                                  </span>
                                </div>
                                {conMatrices.has(hoja.id) && (
                                  <div className="arbol__matrices-cuerpo">
                                    <MatricesDeActividad actividadId={hoja.id} />
                                  </div>
                                )}
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
    </div>
  );
}
