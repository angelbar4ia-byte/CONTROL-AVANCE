/**
 * Las matrices internas de una actividad (cerebro WORKFLOWS.md §8.9, «Las hojas del árbol»; D-565,
 * D-583). El concepto es la matriz madre y un insumo puede ser otra matriz —nervaduras, trabes,
 * bastones—, a cualquier profundidad. Se dibujan como carpetas anidadas: cada una con su tipo de
 * medición (por su unidad), su cantidad medida contra la del catálogo, y un clic la vuelve lo que se
 * está midiendo. Lo que se mide son esas matrices; su cantidad es de esta obra y ajusta el importe
 * de la actividad sin tocar su cantidad base ni el catálogo.
 */

import { ChevronRight } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import type { MatricesDeActividadRespuesta } from '@/api/generado/modelo';
import { useMatricesDeLaActividadApiV1ActividadesActividadIdMatricesGet } from '@/api/generado/cuantificacion/cuantificacion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtMXN, fmtNum } from '@/lib/formato';
import { arbolDeMatrices, llavesConHijos, type NodoDeMatriz } from './matrices';
import { NOMBRE_DE_TIPO } from './tipos';

interface Props {
  readonly actividadId: string;
  /** La matriz que se está midiendo (`concepto_id`), si es una de esta actividad. */
  readonly matrizActivaId?: string | null;
  /** Clic en una matriz: pasa a ser lo que se mide. Otro clic la suelta. */
  readonly onActivar?: (matriz: { id: string; clave: string; unidad: string | null }) => void;
}

function Nodo({
  nodo,
  cerradas,
  alternar,
  matrizActivaId,
  onActivar,
}: {
  readonly nodo: NodoDeMatriz;
  readonly cerradas: ReadonlySet<string>;
  readonly alternar: (llave: string) => void;
  readonly matrizActivaId?: string | null;
  readonly onActivar?: Props['onActivar'];
}) {
  const conHijos = nodo.hijos.length > 0;
  const abierto = !cerradas.has(nodo.llave);
  const sinMedir = nodo.cantidadMedida === null;
  const etiqueta = `${nodo.clave} · ${nodo.descripcion}`;
  return (
    <li role="treeitem" aria-level={nodo.nivel + 1} aria-label={etiqueta} aria-expanded={conHijos ? abierto : undefined} aria-selected={false}>
      <div className={['arbol__fila arbol__fila--matriz', nodo.conceptoId === matrizActivaId && 'is-foco'].filter(Boolean).join(' ')}>
        {conHijos ? (
          <button
            type="button"
            className="arbol__giro"
            aria-label={`${abierto ? 'Contraer' : 'Expandir'} ${etiqueta}`}
            onClick={() => alternar(nodo.llave)}
          >
            <ChevronRight size={13} className={abierto ? 'is-abierto' : undefined} aria-hidden />
          </button>
        ) : (
          <span className="arbol__giro" aria-hidden />
        )}
        {onActivar ? (
          <button
            type="button"
            className="arbol__texto arbol__activar"
            title={etiqueta}
            aria-pressed={nodo.conceptoId === matrizActivaId}
            onClick={() => onActivar({ id: nodo.conceptoId, clave: nodo.clave, unidad: nodo.unidad })}
          >
            <span className="mono">{nodo.clave}</span> · {nodo.descripcion}
          </button>
        ) : (
          <span className="arbol__texto" title={etiqueta}>
            <span className="mono">{nodo.clave}</span> · {nodo.descripcion}
          </span>
        )}
        {nodo.tipo && (
          <span className="badge badge--outline" data-testid="tipo-de-matriz" title="Cómo se mide: sale de su unidad">
            {NOMBRE_DE_TIPO[nodo.tipo]}
          </span>
        )}
        {sinMedir && <span className="badge badge--outline">Sin medir</span>}
        <span
          className="arbol__cuenta"
          title={`Catálogo ${fmtNum(nodo.cantidadCatalogo)} · medido ${sinMedir ? '—' : fmtNum(nodo.cantidadMedida)}${nodo.diferencia != null ? ` · dif. ${fmtNum(nodo.diferencia)}` : ''}`}
        >
          {sinMedir ? '—' : fmtNum(nodo.cantidadMedida)} / {fmtNum(nodo.cantidadCatalogo)}
          {nodo.unidad ? ` ${nodo.unidad}` : ''}
        </span>
        {conHijos && (
          <span className="arbol__cuenta" title="Matrices medidas en esta rama">
            {nodo.medidas} de {nodo.total}
          </span>
        )}
      </div>
      {conHijos && abierto && (
        <ul role="group" className="arbol__hijos">
          {nodo.hijos.map((h) => (
            <Nodo key={h.llave} nodo={h} cerradas={cerradas} alternar={alternar} matrizActivaId={matrizActivaId} onActivar={onActivar} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function MatricesDeActividad({ actividadId, matrizActivaId, onActivar }: Props) {
  const consulta = useMatricesDeLaActividadApiV1ActividadesActividadIdMatricesGet<
    MatricesDeActividadRespuesta,
    ErrorApi
  >(actividadId);
  const [cerradas, setCerradas] = useState<ReadonlySet<string>>(new Set());
  const nodos = useMemo(() => arbolDeMatrices(consulta.data?.matrices ?? []), [consulta.data]);

  if (consulta.isLoading) return <div className="text-mute text-xs">Cargando matrices…</div>;
  if (consulta.error) return <ErrorBanner mensaje={consulta.error.message} />;
  const datos = consulta.data;
  if (!datos || datos.matrices.length === 0) {
    return <div className="text-mute text-xs">Este concepto no tiene matrices internas que medir.</div>;
  }

  const conHijos = llavesConHijos(nodos);
  const algunaCerrada = conHijos.some((l) => cerradas.has(l));
  const alternar = (llave: string) =>
    setCerradas((actual) => {
      const siguiente = new Set(actual);
      if (siguiente.has(llave)) siguiente.delete(llave);
      else siguiente.add(llave);
      return siguiente;
    });

  return (
    <div className="col gap-4" role="region" aria-label={`Matrices de ${datos.concepto_clave ?? 'la actividad'}`}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="text-xs text-mute">
          {datos.medidas} de {datos.matrices.length} {datos.matrices.length === 1 ? 'matriz medida' : 'matrices medidas'}
        </span>
        {conHijos.length > 0 && (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setCerradas(algunaCerrada ? new Set() : new Set(conHijos))}
          >
            {algunaCerrada ? 'Expandir matrices' : 'Contraer matrices'}
          </button>
        )}
      </div>
      <ul role="tree" className="arbol__hijos arbol__matrices-arbol" aria-label={`Árbol de matrices de ${datos.concepto_clave ?? 'la actividad'}`}>
        {nodos.map((n) => (
          <Nodo key={n.llave} nodo={n} cerradas={cerradas} alternar={alternar} matrizActivaId={matrizActivaId} onActivar={onActivar} />
        ))}
      </ul>
      {datos.medidas > 0 && (
        <div className="text-xs">
          Lo medido ajusta el importe: {fmtMXN(Number(datos.importe))} → <strong>{fmtMXN(Number(datos.importe_ajustado))}</strong>{' '}
          ({Number(datos.importe_ajuste) >= 0 ? '+' : ''}
          {fmtMXN(Number(datos.importe_ajuste))}). La cantidad de la actividad no cambia.
        </div>
      )}
    </div>
  );
}

/** Opciones para elegir qué se mide dentro de una actividad: ella entera o una de sus matrices. */
export function OpcionesDeMatriz({ actividadId }: { readonly actividadId: string }) {
  const consulta = useMatricesDeLaActividadApiV1ActividadesActividadIdMatricesGet<
    MatricesDeActividadRespuesta,
    ErrorApi
  >(actividadId);
  const vistas = new Set<string>();
  return (
    <>
      {(consulta.data?.matrices ?? [])
        .filter((m) => (vistas.has(m.concepto_id) ? false : (vistas.add(m.concepto_id), true)))
        .map((m) => (
          <option key={m.concepto_id} value={m.concepto_id}>
            {'— '.repeat(m.nivel - 1)}
            {m.clave} · {m.descripcion}
          </option>
        ))}
    </>
  );
}
