/**
 * Árbol WBS de un prototipo: nivel → etapa → concepto (§7.4), con los
 * estilos `.tree*` del sistema de diseño — mismo patrón que `ArbolProyecto`
 * y `ArbolExplosion`.
 *
 * Presentación pura: recibe el árbol ya armado (`arbolPrototipo.ts`). No
 * sabe nada de programas base ni de presupuesto — quien necesite pegarle
 * algo a cada nodo (un renglón de programa, un precio) lo hace con `extra`,
 * sin que este componente tenga que conocer esos contratos.
 */

import { useMemo, useState, type ReactNode } from 'react';
import { Building2, ChevronDown, ChevronRight, Layers, Milestone } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type { NodoPrototipoRespuesta, PartidaRespuesta } from '@/api/generado/modelo';
import { fmtMXN, fmtNum } from '@/lib/formato';
import type { NodoArbolPrototipo } from './nodosPrototipo';

interface Props {
  readonly nodos: readonly NodoArbolPrototipo[];
  /**
   * Partidas del presupuesto vigente del prototipo (§7.3): de aquí salen
   * las columnas de unidad/cantidad/PU/importe de cada concepto, unidas por
   * `prototipo_nodo_id`. Sin ellas —prototipo todavía sin presupuesto
   * cargado— el concepto solo muestra su cantidad del árbol, si trae una.
   */
  readonly partidas?: readonly PartidaRespuesta[];
  /** Contenido extra a la derecha del nombre (renglón de programa, etc). */
  readonly extra?: (nodo: NodoPrototipoRespuesta) => ReactNode;
  /** Árboles chicos se leen mejor todos desplegados de entrada. */
  readonly expandirTodo?: boolean;
}

const ICONO_POR_TIPO: Record<NodoPrototipoRespuesta['tipo'], LucideIcon> = {
  nivel: Building2,
  etapa: Milestone,
  concepto: Layers,
};

export function ArbolPrototipo({ nodos, partidas, extra, expandirTodo = false }: Props) {
  const partidaPorNodo = useMemo(() => {
    const mapa = new Map<string, PartidaRespuesta>();
    for (const partida of partidas ?? []) {
      if (partida.prototipo_nodo_id) mapa.set(partida.prototipo_nodo_id, partida);
    }
    return mapa;
  }, [partidas]);

  if (nodos.length === 0) {
    return (
      <div className="text-mute text-sm" style={{ padding: '16px 8px' }}>
        Este prototipo no tiene ingeniería cargada todavía: su árbol está vacío (§7.4).
      </div>
    );
  }

  return (
    <div className="tree">
      {nodos.map((nodo) => (
        <Nodo
          key={nodo.nodo.id}
          nodo={nodo}
          partidaPorNodo={partidaPorNodo}
          extra={extra}
          expandirTodo={expandirTodo}
        />
      ))}
    </div>
  );
}

function Nodo({
  nodo,
  partidaPorNodo,
  extra,
  expandirTodo,
}: {
  readonly nodo: NodoArbolPrototipo;
  readonly partidaPorNodo: ReadonlyMap<string, PartidaRespuesta>;
  readonly extra?: ((nodo: NodoPrototipoRespuesta) => ReactNode) | undefined;
  readonly expandirTodo: boolean;
}) {
  const [abierto, setAbierto] = useState(expandirTodo);
  const anidable = nodo.hijos.length > 0;
  const id = `prototipo-nodo-${nodo.nodo.id}`;
  const Icono = ICONO_POR_TIPO[nodo.nodo.tipo];
  const esConcepto = nodo.nodo.tipo === 'concepto';
  const partida = esConcepto ? partidaPorNodo.get(nodo.nodo.id) : undefined;
  const cantidadCruda = nodo.nodo.cantidad;

  const contenido = (
    <>
      <span className="tree__caret" aria-hidden>
        {anidable ? abierto ? <ChevronDown size={14} /> : <ChevronRight size={14} /> : null}
      </span>
      <Icono className="tree__icon" size={16} strokeWidth={1.6} aria-hidden />
      <span className="tree__name">
        {nodo.nodo.clave && <span className="mono">{nodo.nodo.clave}</span>} {nodo.nodo.nombre}
      </span>
      {esConcepto &&
        (partida ? (
          <>
            {partida.unidad_clave && (
              <span className="tree__meta" title="Unidad">
                {partida.unidad_clave}
              </span>
            )}
            <span className="tree__meta tnum" title="Cantidad">
              {fmtNum(partida.cantidad)}
            </span>
            <span className="tree__meta tnum" title="Precio unitario">
              {fmtMXN(partida.precio_unitario)}
            </span>
            <span className="tree__meta tnum" title="Importe">
              {fmtMXN(partida.importe)}
            </span>
          </>
        ) : (
          cantidadCruda !== undefined &&
          cantidadCruda !== null &&
          Number(cantidadCruda) !== 0 && (
            <span className="tree__meta tnum" title="Cantidad en este nodo del árbol">
              {fmtNum(cantidadCruda)}
            </span>
          )
        ))}
      {extra?.(nodo.nodo)}
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
            <Nodo
              key={hijo.nodo.id}
              nodo={hijo}
              partidaPorNodo={partidaPorNodo}
              extra={extra}
              expandirTodo={expandirTodo}
            />
          ))}
        </div>
      )}
    </div>
  );
}
