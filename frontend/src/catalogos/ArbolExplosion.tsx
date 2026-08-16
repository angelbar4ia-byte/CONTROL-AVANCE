/**
 * Explosión del APU: el árbol recursivo de un concepto (§7.3).
 *
 * Un concepto anida **insumos** (hojas) y **otros conceptos** —auxiliares y
 * matrices—, que a su vez traen su propia composición. Cada nodo con hijos
 * es un `button` con `aria-expanded`/`aria-controls` (patrón de disclosure),
 * igual que el árbol de proyectos, para poder recorrerlo completo con
 * teclado.
 *
 * Presentación pura: recibe el árbol ya armado (`explosion.ts`) y pinta las
 * cifras que el backend ya calculó. `es_destajo` viene por línea desde el
 * dominio (§7.3: "el destajo = mano de obra o subcontrato"); aquí no se
 * decide, solo se marca.
 */

import { useState } from 'react';
import { ChevronDown, ChevronRight, Layers, Package } from 'lucide-react';

import { fmtMXN, fmtNum } from '@/lib/formato';
import type { NodoExplosion } from './explosion';
import { etiquetaCategoria, tonoCategoria } from './reglas';

interface Props {
  readonly nodos: readonly NodoExplosion[];
  /** Clave del concepto raíz, para etiquetar el encabezado del árbol. */
  readonly clave: string;
}

export function ArbolExplosion({ nodos, clave }: Props) {
  if (nodos.length === 0) {
    return (
      <div className="text-mute text-sm" style={{ padding: '16px 8px' }}>
        <span className="mono">{clave}</span> no tiene composición cargada: su explosión está
        vacía, así que su CPU es cero por sí mismo (§7.3).
      </div>
    );
  }

  return (
    <div className="tree">
      {nodos.map((nodo) => (
        <Nodo key={`${nodo.linea.ruta.join('>')}>${nodo.linea.referencia}`} nodo={nodo} />
      ))}
    </div>
  );
}

function Nodo({ nodo }: { readonly nodo: NodoExplosion }) {
  // Los auxiliares y matrices arrancan plegados: un APU real anida dos o
  // tres niveles y abrirlo todo de golpe entierra el primer nivel, que es el
  // que se lee primero.
  const [abierto, setAbierto] = useState(false);

  const { linea } = nodo;
  const anidable = nodo.hijos.length > 0;
  const id = `explosion-${linea.ruta.join('-')}-${linea.referencia}`;

  const contenido = (
    <>
      <span className="tree__caret" aria-hidden>
        {anidable ? abierto ? <ChevronDown size={14} /> : <ChevronRight size={14} /> : null}
      </span>
      {linea.tipo_hijo === 'concepto' ? (
        <Layers className="tree__icon" size={16} strokeWidth={1.6} aria-hidden />
      ) : (
        <Package className="tree__icon" size={16} strokeWidth={1.6} aria-hidden />
      )}
      <span className="tree__name mono">{linea.referencia}</span>
      <span className={`badge badge--${tonoCategoria(linea.categoria)}`}>
        {etiquetaCategoria(linea.categoria)}
      </span>
      {linea.es_destajo && (
        <span className="badge badge--accent" title="Lo cobra la cuadrilla (§7.3).">
          destajo
        </span>
      )}
      <span className="tree__meta tnum" title="Cantidad por unidad del concepto raíz">
        {fmtNum(linea.cantidad)}
      </span>
      <span className="tree__meta tnum" title="Costo unitario">
        {fmtMXN(linea.costo_unitario)}
      </span>
      <span className="tree__meta tnum" title="Importe">
        {fmtMXN(linea.importe)}
      </span>
    </>
  );

  return (
    <div>
      {anidable ? (
        <button
          type="button"
          className="tree__node w-full"
          aria-expanded={abierto}
          aria-controls={id}
          onClick={() => setAbierto((previo) => !previo)}
        >
          {contenido}
        </button>
      ) : (
        <div className="tree__node">{contenido}</div>
      )}

      {anidable && abierto && (
        <div className="tree__children" id={id}>
          {nodo.hijos.map((hijo) => (
            <Nodo key={`${hijo.linea.ruta.join('>')}>${hijo.linea.referencia}`} nodo={hijo} />
          ))}
        </div>
      )}
    </div>
  );
}
