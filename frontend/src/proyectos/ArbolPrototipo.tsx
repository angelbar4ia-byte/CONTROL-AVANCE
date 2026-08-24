/**
 * Árbol WBS de un prototipo: nivel → etapa → concepto (§7.4), con los
 * estilos `.tree*` del sistema de diseño — mismo patrón que `ArbolProyecto`
 * y `ArbolExplosion`.
 *
 * Se detiene en concepto: sus componentes (material/mano de obra/
 * subcontrato) arman su APU, pero eso es la explosión del CPU (§7.3,
 * `ArbolExplosion`), no un nivel más de este árbol — mezclar los dos
 * enterraría la estructura del prototipo bajo cientos de insumos.
 *
 * Presentación pura: recibe el árbol ya armado (`nodosPrototipo.ts`). No
 * sabe nada de programas base — quien necesite pegarle algo más a cada nodo
 * (un renglón de programa) lo hace con `extra`, sin que este componente
 * tenga que conocer ese contrato.
 */

import { useMemo, useState, type ReactNode } from 'react';
import { Building2, ChevronDown, ChevronRight, Layers, Milestone } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type {
  NodoPrototipoRespuesta,
  PartidaRespuesta,
  PresupuestoRespuesta,
} from '@/api/generado/modelo';
import { fmtMXN, fmtNum } from '@/lib/formato';
import { sumarImportesPorNodo, type NodoArbolPrototipo } from './nodosPrototipo';

interface Props {
  readonly nodos: readonly NodoArbolPrototipo[];
  /**
   * El presupuesto vigente del prototipo (§7.3): de aquí salen las columnas
   * de unidad/cantidad/PU/importe de cada concepto —unidas por
   * `prototipo_nodo_id`—, el importe acumulado de cada nivel/etapa y el
   * total del pie. Sin él —prototipo todavía sin presupuesto cargado— el
   * concepto solo muestra su cantidad del árbol, si trae una.
   */
  readonly presupuesto?: PresupuestoRespuesta;
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

export function ArbolPrototipo({ nodos, presupuesto, extra, expandirTodo = false }: Props) {
  const partidaPorNodo = useMemo(() => {
    const mapa = new Map<string, PartidaRespuesta>();
    for (const partida of presupuesto?.partidas ?? []) {
      if (partida.prototipo_nodo_id) mapa.set(partida.prototipo_nodo_id, partida);
    }
    return mapa;
  }, [presupuesto]);

  const importePorNodo = useMemo(
    () => sumarImportesPorNodo(nodos, partidaPorNodo),
    [nodos, partidaPorNodo],
  );

  if (nodos.length === 0) {
    return (
      <div className="text-mute text-sm" style={{ padding: '16px 8px' }}>
        Este prototipo no tiene ingeniería cargada todavía: su árbol está vacío (§7.4).
      </div>
    );
  }

  return (
    <div className="tree">
      <div className="tree__header">
        <span className="tree__header-label">Concepto</span>
        <span className="tree__col-unidad">Unidad</span>
        <span className="tree__col-cantidad">Cantidad</span>
        <span className="tree__col-pu">P.U.</span>
        <span className="tree__col-importe">Importe</span>
      </div>

      {nodos.map((nodo) => (
        <Nodo
          key={nodo.nodo.id}
          nodo={nodo}
          partidaPorNodo={partidaPorNodo}
          importePorNodo={importePorNodo}
          extra={extra}
          expandirTodo={expandirTodo}
        />
      ))}

      {presupuesto && (
        <div className="tree__total">
          <span className="tree__caret" aria-hidden />
          <span className="tree__name text-mute">
            Presupuesto vigente · versión {presupuesto.version}
          </span>
          <span className="tree__col-unidad" aria-hidden />
          <span className="tree__col-cantidad" aria-hidden />
          <span className="tree__col-pu" aria-hidden />
          <span className="tree__col-importe tnum">{fmtMXN(presupuesto.monto_total)}</span>
        </div>
      )}
    </div>
  );
}

function Nodo({
  nodo,
  partidaPorNodo,
  importePorNodo,
  extra,
  expandirTodo,
}: {
  readonly nodo: NodoArbolPrototipo;
  readonly partidaPorNodo: ReadonlyMap<string, PartidaRespuesta>;
  readonly importePorNodo: ReadonlyMap<string, number>;
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
  const importe = importePorNodo.get(nodo.nodo.id) ?? 0;

  const cantidadMostrada =
    partida?.cantidad ??
    (cantidadCruda !== undefined && cantidadCruda !== null && Number(cantidadCruda) !== 0
      ? cantidadCruda
      : null);

  const contenido = (
    <>
      <span className="tree__caret" aria-hidden>
        {anidable ? abierto ? <ChevronDown size={14} /> : <ChevronRight size={14} /> : null}
      </span>
      <Icono className="tree__icon" size={16} strokeWidth={1.6} aria-hidden />
      <span className="tree__name">
        {nodo.nodo.clave && <span className="mono">{nodo.nodo.clave}</span>} {nodo.nodo.nombre}
      </span>
      <span className="tree__meta tree__col-unidad" title="Unidad">
        {esConcepto ? (partida?.unidad_clave ?? '') : ''}
      </span>
      <span className="tree__meta tnum tree__col-cantidad" title="Cantidad">
        {esConcepto && cantidadMostrada !== null ? fmtNum(cantidadMostrada) : ''}
      </span>
      <span className="tree__meta tnum tree__col-pu" title="Precio unitario">
        {esConcepto && partida ? fmtMXN(partida.precio_unitario) : ''}
      </span>
      <span className="tree__meta tnum tree__col-importe" title="Importe">
        {importe > 0 ? fmtMXN(importe) : ''}
      </span>
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
              importePorNodo={importePorNodo}
              extra={extra}
              expandirTodo={expandirTodo}
            />
          ))}
        </div>
      )}
    </div>
  );
}
