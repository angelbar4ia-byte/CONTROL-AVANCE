/**
 * Árbol WBS de un prototipo: prototipo → nivel → etapa → concepto/concepto
 * auxiliar (§7.4, §10.1), con los estilos `.tree*` del sistema de diseño —
 * mismo patrón que `ArbolProyecto` y `ArbolExplosion`.
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
import {
  Building2,
  ChevronDown,
  ChevronRight,
  Home,
  Layers,
  Milestone,
  Puzzle,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type { PartidaRespuesta, PresupuestoRespuesta } from '@/api/generado/modelo';
import { fmtMXN, fmtNum } from '@/lib/formato';
import {
  sumarImportesPorNodo,
  type NodoArbolPrototipo,
  type TipoNodoArbol,
} from './nodosPrototipo';

interface Props {
  readonly raiz: NodoArbolPrototipo;
  /**
   * El presupuesto vigente del prototipo (§7.3): de aquí salen las columnas
   * de unidad/cantidad/PU/importe de cada concepto —unidas por
   * `prototipo_nodo_id`— y el importe acumulado de prototipo/nivel/etapa.
   * El importe de la raíz usa `monto_total` directo (la cifra que ya
   * calculó y guardó el backend) en vez de sumar en el cliente. Sin
   * presupuesto —prototipo todavía sin cargar— el concepto solo muestra su
   * cantidad del árbol, si trae una.
   */
  readonly presupuesto?: PresupuestoRespuesta;
  /** Contenido extra a la derecha del nombre (renglón de programa, etc). */
  readonly extra?: (nodo: NodoArbolPrototipo) => ReactNode;
  /** Árboles chicos se leen mejor todos desplegados de entrada. */
  readonly expandirTodo?: boolean;
}

const ICONO_POR_TIPO: Record<TipoNodoArbol, LucideIcon> = {
  prototipo: Home,
  nivel: Building2,
  etapa: Milestone,
  concepto: Layers,
  concepto_auxiliar: Puzzle,
};

export function ArbolPrototipo({ raiz, presupuesto, extra, expandirTodo = false }: Props) {
  const partidaPorNodo = useMemo(() => {
    const mapa = new Map<string, PartidaRespuesta>();
    for (const partida of presupuesto?.partidas ?? []) {
      if (partida.prototipo_nodo_id) mapa.set(partida.prototipo_nodo_id, partida);
    }
    return mapa;
  }, [presupuesto]);

  const importePorNodo = useMemo(() => {
    const mapa = new Map(sumarImportesPorNodo(raiz, partidaPorNodo));
    // La raíz usa el monto_total que ya calculó el backend, no la suma del
    // cliente: es la cifra vigente y persistida, no una re-derivación.
    if (presupuesto) mapa.set(raiz.id, Number(presupuesto.monto_total));
    return mapa;
  }, [raiz, partidaPorNodo, presupuesto]);

  if (raiz.hijos.length === 0) {
    return (
      <div className="text-mute text-sm" style={{ padding: '16px 8px' }}>
        Este prototipo no tiene ingeniería cargada todavía: su árbol está vacío (§7.4).
      </div>
    );
  }

  return (
    <div className="tree tree--tabla">
      <div className="tree__header">
        <span className="tree__header-label">Concepto</span>
        <span className="tree__col-clave">Clave</span>
        <span className="tree__col-unidad">Unidad</span>
        <span className="tree__col-cantidad">Cantidad</span>
        <span className="tree__col-pu">P.U.</span>
        <span className="tree__col-importe">Importe</span>
      </div>

      <Nodo
        nodo={raiz}
        partidaPorNodo={partidaPorNodo}
        importePorNodo={importePorNodo}
        extra={extra}
        expandirTodo={expandirTodo}
        abiertoDeEntrada
      />
    </div>
  );
}

function Nodo({
  nodo,
  partidaPorNodo,
  importePorNodo,
  extra,
  expandirTodo,
  abiertoDeEntrada = false,
}: {
  readonly nodo: NodoArbolPrototipo;
  readonly partidaPorNodo: ReadonlyMap<string, PartidaRespuesta>;
  readonly importePorNodo: ReadonlyMap<string, number>;
  readonly extra?: ((nodo: NodoArbolPrototipo) => ReactNode) | undefined;
  readonly expandirTodo: boolean;
  /** La raíz (el prototipo) arranca abierta: sin eso el árbol se ve vacío. */
  readonly abiertoDeEntrada?: boolean;
}) {
  const [abierto, setAbierto] = useState(expandirTodo || abiertoDeEntrada);
  const anidable = nodo.hijos.length > 0;
  const id = `prototipo-nodo-${nodo.id}`;
  const Icono = ICONO_POR_TIPO[nodo.tipo];
  const esConcepto = nodo.tipo === 'concepto' || nodo.tipo === 'concepto_auxiliar';
  const partida = esConcepto ? partidaPorNodo.get(nodo.id) : undefined;
  const cantidadCruda = nodo.cantidad;
  const importe = importePorNodo.get(nodo.id) ?? 0;

  const cantidadMostrada =
    partida?.cantidad ??
    (cantidadCruda !== null && Number(cantidadCruda) !== 0 ? cantidadCruda : null);

  const contenido = (
    <>
      <span className="tree__caret" aria-hidden>
        {anidable ? abierto ? <ChevronDown size={14} /> : <ChevronRight size={14} /> : null}
      </span>
      <Icono className="tree__icon" size={16} strokeWidth={1.6} aria-hidden />
      <span className={`tree__name${esConcepto ? ' tree__name--justificado' : ''}`}>
        {nodo.wbs && (
          <span className="mono text-mute" style={{ marginRight: 6 }}>
            {nodo.wbs}
          </span>
        )}
        {nodo.nombre}
        {nodo.tipo === 'concepto_auxiliar' && (
          <span className="badge badge--outline" style={{ marginLeft: 6 }}>
            auxiliar
          </span>
        )}
      </span>
      <span className="tree__meta tree__col-clave mono" title="Clave">
        {nodo.clave ?? ''}
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
      {extra?.(nodo)}
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
              key={hijo.id}
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
