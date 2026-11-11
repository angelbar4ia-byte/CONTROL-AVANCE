/**
 * Las matrices internas de una actividad (cerebro WORKFLOWS.md §8.9, «Las hojas del árbol»; D-565,
 * D-583). El concepto es la matriz madre y un insumo puede ser otra matriz —nervaduras, trabes,
 * bastones—, a cualquier profundidad. Se dibujan como carpetas anidadas: cada una con su tipo de
 * medición (por su unidad), su cantidad medida contra la del catálogo, y un clic la vuelve lo que se
 * está midiendo. Lo que se mide son esas matrices; su cantidad es de esta obra y ajusta el importe
 * de la actividad sin tocar su cantidad base ni el catálogo.
 */

import { ChevronRight, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import type { MatricesDeActividadRespuesta } from '@/api/generado/modelo';
import { useQuitarMatrizDelConceptoApiV1ConceptosConceptoIdMatricesMatrizIdDelete } from '@/api/generado/catalogos/catalogos';
import {
  usePonerMatrizQueCuentaApiV1ActividadesActividadIdMatrizQueCuentaPut,
  useMatricesDeLaActividadApiV1ActividadesActividadIdMatricesGet,
} from '@/api/generado/cuantificacion/cuantificacion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { AltaDeMatriz } from './AltaDeMatriz';
import { CostoDelConcepto } from './CostoDelConcepto';
import { fmtMXN, fmtNum } from '@/lib/formato';
import { arbolDeMatrices, llavesConHijos, type NodoDeMatriz } from './matrices';
import { NOMBRE_DE_TIPO } from './tipos';

interface Props {
  readonly actividadId: string;
  /** La matriz que se está midiendo (`concepto_id`), si es una de esta actividad. */
  readonly matrizActivaId?: string | null;
  /** Clic en una matriz: pasa a ser lo que se mide. Otro clic la suelta. */
  readonly onActivar?: (matriz: { id: string; clave: string; unidad: string | null }) => void;
  /** Control de obra y Costos pueden agregar y quitar matrices: es composición del catálogo. */
  readonly puedeEditar?: boolean;
}

/** Lo que el nodo necesita para editar la composición de su concepto. */
interface Edicion {
  readonly onPuesta: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
  readonly quitar: (padreId: string, matrizId: string) => void;
}

function Nodo({
  nodo,
  cerradas,
  alternar,
  matrizActivaId,
  onActivar,
  padreId,
  edicion,
  cuentaId,
  onCuenta,
  enCurso = false,
}: {
  readonly nodo: NodoDeMatriz;
  readonly cerradas: ReadonlySet<string>;
  readonly alternar: (llave: string) => void;
  readonly matrizActivaId?: string | null;
  readonly onActivar?: Props['onActivar'];
  /** La matriz (o el concepto) de la que ésta es insumo directo. */
  readonly padreId: string | null;
  readonly edicion?: Edicion;
  /** La matriz que da la cantidad del concepto (D-636) y cómo cambiarla; sin `onCuenta` no se ofrece. */
  readonly cuentaId?: string | null;
  readonly onCuenta?: (matrizId: string | null) => void;
  /** Mientras una petición de «Que cuente» está en curso el botón espera: un clic con el estado viejo la desharía. */
  readonly enCurso?: boolean;
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
        {nodo.formula && (
          <span className="badge badge--outline" data-testid="formula-de-matriz" title="Cómo se formó la cantidad por unidad (piezas ÷ largo de la pieza comercial + desperdicio)">
            {nodo.formula}
          </span>
        )}
        {sinMedir && <span className="badge badge--outline">Sin medir</span>}
        {!sinMedir && nodo.origen === 'elemento' && (
          <span className="badge badge--outline" data-testid="origen-por-elemento" title="Su cantidad es lo que toma de los elementos colocados en el plano (D-630). Lo trazado directo sobre la matriz manda sobre esto.">
            Por elemento
          </span>
        )}
        {onCuenta && (
          <label
            className="arbol__casilla-cuenta"
            title={
              nodo.conceptoId === cuentaId
                ? 'Esta matriz da la cantidad del concepto. Desmárcala y cuentan sus trazos propios.'
                : 'Marca la casilla para que la cantidad del concepto sea la de esta matriz (debe ser de su misma unidad).'
            }
          >
            <input
              type="checkbox"
              data-cuenta={nodo.clave}
              checked={nodo.conceptoId === cuentaId}
              disabled={enCurso}
              aria-label={`Que cuente ${nodo.clave} para el concepto`}
              onChange={() => onCuenta(nodo.conceptoId === cuentaId ? null : nodo.conceptoId)}
            />
            cuenta
          </label>
        )}
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
        {edicion && padreId && (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            aria-label={`Quitar ${nodo.clave} de su concepto`}
            title="Quitar esta matriz del catálogo del concepto"
            onClick={() => edicion.quitar(padreId, nodo.conceptoId)}
          >
            <X size={12} aria-hidden />
          </button>
        )}
      </div>
      {edicion && (
        <div className="arbol__alta-matriz">
          <AltaDeMatriz padreId={nodo.conceptoId} padreClave={nodo.clave} onPuesta={edicion.onPuesta} onError={edicion.onError} />
        </div>
      )}
      {conHijos && abierto && (
        <ul role="group" className="arbol__hijos">
          {nodo.hijos.map((h) => (
            <Nodo key={h.llave} nodo={h} cerradas={cerradas} alternar={alternar} matrizActivaId={matrizActivaId} onActivar={onActivar} padreId={nodo.conceptoId} edicion={edicion} cuentaId={cuentaId} onCuenta={onCuenta} enCurso={enCurso} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function MatricesDeActividad({ actividadId, matrizActivaId, onActivar, puedeEditar = false }: Props) {
  const consulta = useMatricesDeLaActividadApiV1ActividadesActividadIdMatricesGet<
    MatricesDeActividadRespuesta,
    ErrorApi
  >(actividadId);
  const [cerradas, setCerradas] = useState<ReadonlySet<string>>(new Set());
  const nodos = useMemo(() => arbolDeMatrices(consulta.data?.matrices ?? []), [consulta.data]);
  const queryClient = useQueryClient();
  const quitarMatriz = useQuitarMatrizDelConceptoApiV1ConceptosConceptoIdMatricesMatrizIdDelete<ErrorApi>();
  const [mensaje, setMensaje] = useState<string | null>(null);
  const ponerCuenta = usePonerMatrizQueCuentaApiV1ActividadesActividadIdMatrizQueCuentaPut<ErrorApi>();
  /** Qué matriz da la cantidad del concepto (D-636); solo donde se puede trazar (hay `onActivar`). */
  const alCuenta = onActivar
    ? (matrizId: string | null) =>
        ponerCuenta
          .mutateAsync({ actividadId, data: { matriz_concepto_id: matrizId } })
          .then((r) => {
            setMensaje(
              matrizId === null
                ? `Cuentan los trazos propios del concepto: ${fmtNum(r.cantidad_total)}.`
                : `La cantidad del concepto es ahora la de esa matriz: ${fmtNum(r.cantidad_total)}. Lo trazado directo no suma hasta soltarla.`,
            );
            void queryClient.invalidateQueries({
              predicate: (q) => /\/matrices|\/cuantificacion|\/trazos|\/mediciones|\/actividades|\/avance/.test(JSON.stringify(q.queryKey)),
            });
          })
          .catch((err: unknown) => setMensaje(err instanceof Error ? err.message : 'No se pudo cambiar de dónde viene la cantidad.'))
    : undefined;
  const edicion: Edicion | undefined = puedeEditar
    ? {
        onPuesta: (aviso) => {
          setMensaje(aviso);
          void queryClient.invalidateQueries({ predicate: (q) => /\/matrices|\/cpu/.test(JSON.stringify(q.queryKey)) });
        },
        onError: (m) => setMensaje(m),
        quitar: (padre, matriz) =>
          quitarMatriz
            .mutateAsync({ conceptoId: padre, matrizId: matriz })
            .then(() => {
              setMensaje('Matriz quitada del catálogo del concepto.');
              void queryClient.invalidateQueries({ predicate: (q) => /\/matrices|\/cpu/.test(JSON.stringify(q.queryKey)) });
            })
            .catch((err: unknown) => setMensaje(err instanceof Error ? err.message : 'No se pudo quitar la matriz.')),
      }
    : undefined;

  if (consulta.isLoading) return <div className="text-mute text-xs">Cargando matrices…</div>;
  if (consulta.error) return <ErrorBanner mensaje={consulta.error.message} />;
  const datos = consulta.data;
  if (!datos || datos.matrices.length === 0) {
    return (
      <div className="col gap-4">
        <div className="text-mute text-xs">Este concepto no tiene matrices internas que medir.</div>
        {edicion && datos?.concepto_id && (
          <AltaDeMatriz
            padreId={datos.concepto_id}
            padreClave={datos.concepto_clave ?? 'el concepto'}
            onPuesta={edicion.onPuesta}
            onError={edicion.onError}
          />
        )}
        {mensaje && <div role="status" className="text-xs">{mensaje}</div>}
        {edicion && datos?.concepto_id && (
          <CostoDelConcepto conceptoId={datos.concepto_id} conceptoClave={datos.concepto_clave ?? 'el concepto'} />
        )}
      </div>
    );
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
          <Nodo key={n.llave} nodo={n} cerradas={cerradas} alternar={alternar} matrizActivaId={matrizActivaId} onActivar={onActivar} padreId={datos.concepto_id ?? null} edicion={edicion} cuentaId={datos.matriz_cuenta_id ?? null} onCuenta={alCuenta} enCurso={ponerCuenta.isPending} />
        ))}
      </ul>
      {edicion && datos.concepto_id && (
        <AltaDeMatriz
          padreId={datos.concepto_id}
          padreClave={datos.concepto_clave ?? 'el concepto'}
          onPuesta={edicion.onPuesta}
          onError={edicion.onError}
        />
      )}
      {mensaje && <div role="status" className="text-xs">{mensaje}</div>}
      {edicion && datos.concepto_id && (
        <CostoDelConcepto conceptoId={datos.concepto_id} conceptoClave={datos.concepto_clave ?? 'el concepto'} />
      )}
      {datos.medidas > 0 && (
        <div className="text-xs">
          Lo medido ajusta el importe: {fmtMXN(Number(datos.importe))} → <strong>{fmtMXN(Number(datos.importe_ajustado))}</strong>{' '}
          ({Number(datos.importe_ajuste) >= 0 ? '+' : ''}
          {fmtMXN(Number(datos.importe_ajuste))}).{' '}
          {datos.matriz_cuenta_id ? 'La cantidad de la actividad es la de la matriz que cuenta.' : 'La cantidad de la actividad no cambia.'}
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
