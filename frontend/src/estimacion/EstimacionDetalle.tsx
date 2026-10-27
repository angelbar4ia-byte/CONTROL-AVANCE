/**
 * Guía de estimación — el detalle de una estimación, agrupado por frente
 * (§11.3 E).
 *
 * Antes de esto, ver qué lleva una semana significaba encolar el `.xlsx` y
 * esperar el job. `GET /estimaciones/{id}` arma el mismo reporte
 * (`ArmarReporteDeEstimacion`) sin dibujar el archivo, así que se sirve
 * síncrono: es la vista de entrada, y el Excel sigue disponible para cuando
 * hace falta el papel.
 *
 * ## Las tres pestañas leen el mismo dato
 *
 * «Resumen por frente» es `por_frente` (domain, ya redondeado); «Detalle» es
 * `conceptos` completo; «Extra-catálogo» es el mismo arreglo filtrado por
 * `fuera_catalogo`. Ninguna tabla recalcula nada — si el resumen y el
 * detalle sumaran distinto, sería un defecto de datos, no de vista.
 *
 * ## El acumulado no es de esta estimación
 *
 * `acumulado_proyecto` sale de sumar lo *enviado y validado* de toda la obra,
 * no de esta semana: por eso viaja aparte de `monto_total` y no se mezcla
 * con `por_frente`, que sí es exclusivo de esta estimación.
 */

import { useMemo, useState } from 'react';

import {
  useDetalleDeEstimacionApiV1EstimacionesEstimacionIdGet,
  useEnviarEstimacionApiV1EstimacionesEstimacionIdPatch,
  useValidarEstimacionApiV1EstimacionesEstimacionIdValidarPost,
} from '@/api/generado/estimacion/estimacion';
import { useExportarEstimacionApiV1EstimacionesEstimacionIdExportGet } from '@/api/generado/reportes/reportes';
import type {
  ConceptoDelReporteRespuesta,
  EstimacionDetalleRespuesta,
  FrenteDelReporteRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import type { Rol } from '@/shell/navegacion';
import { useClavesPorRecurso } from '@/lib/idempotencia';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtEntero, fmtMXN, fmtNum, fmtPct, fmtSemana } from '@/lib/formato';
import { SeguimientoDeReporte } from '@/reportes/SeguimientoDeReporte';
import { accionesDisponiblesEstimacion, etiquetaModo, tonoEstatusEstimacion } from './reglas';

type Pestana = 'resumen' | 'detalle' | 'extra';

interface Props {
  readonly estimacionId: string;
  readonly rol: Rol;
  readonly onVolver: () => void;
}

export function EstimacionDetalle({ estimacionId, rol, onVolver }: Props) {
  const [pestana, setPestana] = useState<Pestana>('resumen');
  const [error, setError] = useState<string | null>(null);
  const [reporteId, setReporteId] = useState<string | null>(null);
  const idempotente = useClavesPorRecurso();

  const consulta = useDetalleDeEstimacionApiV1EstimacionesEstimacionIdGet<
    EstimacionDetalleRespuesta,
    ErrorApi
  >(estimacionId);

  const enviar = useEnviarEstimacionApiV1EstimacionesEstimacionIdPatch<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
    ...idempotente,
  });

  const validar = useValidarEstimacionApiV1EstimacionesEstimacionIdValidarPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
    ...idempotente,
  });

  const exportar = useExportarEstimacionApiV1EstimacionesEstimacionIdExportGet(estimacionId, {
    query: { enabled: false },
  });

  async function encolarExport() {
    setError(null);
    const resultado = await exportar.refetch();
    if (resultado.error) {
      setError((resultado.error as ErrorApi).message);
      return;
    }
    if (resultado.data) setReporteId(resultado.data.id);
  }

  const datos = consulta.data;
  const acciones = datos ? accionesDisponiblesEstimacion(rol, datos.estatus) : [];

  const pctPresupuesto = useMemo(() => {
    if (!datos || datos.presupuesto_base === null || datos.presupuesto_base === undefined) {
      return null;
    }
    const base = Number(datos.presupuesto_base);
    if (base <= 0) return null;
    return (Number(datos.acumulado_proyecto) / base) * 100;
  }, [datos]);

  const alertas = datos?.n_alertas_de_respaldo ?? 0;

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <button type="button" className="btn btn--ghost btn--sm" onClick={onVolver}>
            ← Bandeja de estimaciones
          </button>
          <div className="page__eyebrow mono">Guía de estimación</div>
          {datos && (
            <>
              <h1 className="page__title">{datos.folio ?? datos.id.slice(0, 8)}</h1>
              <div className="page__subtitle">
                {fmtSemana(datos.semana, datos.anio)} · {datos.obra_clave} ·{' '}
                {etiquetaModo(datos.modo)}
                {!datos.cuadra && (
                  <>
                    {' '}
                    <span className="badge badge--danger">No cuadra con sus renglones</span>
                  </>
                )}
              </div>
            </>
          )}
        </div>
        {datos && (
          <div className="page__actions">
            {acciones.includes('enviar') && (
              <button
                type="button"
                className="btn btn--accent"
                disabled={enviar.isPending}
                onClick={() => enviar.mutate({ estimacionId: datos.id })}
              >
                {enviar.isPending ? 'Enviando…' : 'Enviar para validación'}
              </button>
            )}
            {acciones.includes('validar') && (
              <button
                type="button"
                className="btn btn--accent"
                disabled={validar.isPending}
                onClick={() => validar.mutate({ estimacionId: datos.id })}
              >
                {validar.isPending ? 'Validando…' : 'Validar'}
              </button>
            )}
            <button
              type="button"
              className="btn"
              disabled={exportar.isFetching}
              onClick={() => void encolarExport()}
            >
              Descargar como Excel
            </button>
          </div>
        )}
      </div>

      {error && <ErrorBanner mensaje={error} />}
      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}

      {reporteId && (
        <SeguimientoDeReporte
          reporteId={reporteId}
          titulo="Estimación en Excel"
          onCerrar={() => setReporteId(null)}
        />
      )}

      {consulta.isLoading || !datos ? (
        <div className="text-mute text-sm" style={{ padding: 24 }}>
          Cargando…
        </div>
      ) : (
        <>
          <div className="kpi-grid">
            <div className="kpi">
              <div className="kpi__label">Monto de la estimación</div>
              <div className="kpi__value">{fmtMXN(datos.monto_total)}</div>
              <div className="kpi__sub">
                <span className={`badge badge--${tonoEstatusEstimacion(datos.estatus)}`}>
                  {datos.estatus}
                </span>
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">Conceptos incluidos</div>
              <div className="kpi__value">{fmtEntero(datos.conceptos.length)}</div>
              <div className="kpi__sub">
                {fmtEntero(datos.n_conceptos_catalogo)} de catálogo ·{' '}
                {fmtEntero(datos.n_conceptos_extra)} fuera de catálogo
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">Acumulado del proyecto</div>
              <div className="kpi__value">{fmtMXN(datos.acumulado_proyecto)}</div>
              <div className="kpi__sub">
                {datos.presupuesto_base
                  ? `${fmtPct(pctPresupuesto)} de ${fmtMXN(datos.presupuesto_base)} base`
                  : 'Sin presupuesto base cargado'}
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">Respaldo del avance</div>
              <div className="kpi__value">{fmtEntero(alertas)}</div>
              <div className="kpi__sub">
                {alertas === 0 ? (
                  'Todo lo estimado está confirmado'
                ) : (
                  <span className="badge badge--warn">
                    renglones estimados por encima de lo confirmado
                  </span>
                )}
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">Semana</div>
              <div className="kpi__value">{fmtSemana(datos.semana, datos.anio)}</div>
              <div className="kpi__sub">{etiquetaModo(datos.modo)}</div>
            </div>
          </div>

          <div className="tabs mb-8" role="tablist" aria-label="Guía de estimación">
            <button
              type="button"
              role="tab"
              aria-selected={pestana === 'resumen'}
              className={`tabs__tab${pestana === 'resumen' ? ' is-active' : ''}`}
              onClick={() => setPestana('resumen')}
            >
              Resumen por frente
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={pestana === 'detalle'}
              className={`tabs__tab${pestana === 'detalle' ? ' is-active' : ''}`}
              onClick={() => setPestana('detalle')}
            >
              Detalle <span className="text-mute">{datos.conceptos.length}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={pestana === 'extra'}
              className={`tabs__tab${pestana === 'extra' ? ' is-active' : ''}`}
              onClick={() => setPestana('extra')}
            >
              Extra-catálogo <span className="text-mute">{datos.n_conceptos_extra}</span>
            </button>
          </div>

          {alertas > 0 && (
            <div
              className="text-sm mb-8"
              role="alert"
              style={{
                color: 'oklch(45% 0.13 75)',
                background: 'var(--c-warn-soft)',
                border: '1px solid var(--c-warn)',
                borderRadius: 'var(--r-md)',
                padding: '8px 12px',
              }}
            >
              <strong>Estimado por encima de lo confirmado.</strong> El residente no ha confirmado
              (o confirmó menos) el avance de {fmtEntero(alertas)} renglón(es).
              No bloquea la estimación: se resuelve confirmando el avance real o bajando la cantidad
              estimada. Míralos en la pestaña «Detalle».
            </div>
          )}

          {pestana === 'resumen' && <TablaPorFrente frentes={datos.por_frente} total={datos.monto_total} />}
          {pestana === 'detalle' && <TablaDeConceptos conceptos={datos.conceptos} />}
          {pestana === 'extra' && (
            <TablaDeConceptos conceptos={datos.conceptos.filter((c) => c.fuera_catalogo)} />
          )}

          <div className="field__hint mt-8">
            Fórmula aplicada: cantidad validada × precio unitario del modo{' '}
            {etiquetaModo(datos.modo).toLowerCase()} (§11.3 E.2). Se calcula al leer; cambia
            un renglón y esta guía cambia con él.
          </div>
        </>
      )}
    </div>
  );
}

function TablaPorFrente({
  frentes,
  total,
}: {
  readonly frentes: readonly FrenteDelReporteRespuesta[];
  readonly total: string | number;
}) {
  if (frentes.length === 0) {
    return (
      <div className="empty">
        <div className="empty-title">Sin renglones</div>
        <div className="empty-sub">Esta estimación no tiene conceptos capturados.</div>
      </div>
    );
  }
  return (
    <div className="table-wrap">
      <div className="table-scroll">
        <table className="table" style={{ minWidth: 'max-content' }}>
          <thead>
            <tr>
              <th style={{ minWidth: 90 }}>Clave</th>
              <th style={{ minWidth: 220 }}>Frente</th>
              <th className="is-num" style={{ minWidth: 100 }}>
                Conceptos
              </th>
              <th className="is-num" style={{ minWidth: 130 }}>
                Subtotal
              </th>
              <th className="is-num" style={{ minWidth: 90 }}>
                %
              </th>
            </tr>
          </thead>
          <tbody>
            {frentes.map((f) => (
              <tr key={f.clave || f.nombre}>
                <td className="mono text-xs">{f.clave}</td>
                <td>{f.nombre}</td>
                <td className="is-num tnum">{fmtEntero(f.conceptos)}</td>
                <td className="is-num tnum">{fmtMXN(f.subtotal)}</td>
                <td className="is-num tnum">{fmtPct(f.porcentaje)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr style={{ fontWeight: 600 }}>
              <td colSpan={2}>Total estimación</td>
              <td className="is-num tnum">
                {fmtEntero(frentes.reduce((s, f) => s + f.conceptos, 0))}
              </td>
              <td className="is-num tnum">{fmtMXN(total)}</td>
              <td className="is-num tnum">100%</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

function TablaDeConceptos({
  conceptos,
}: {
  readonly conceptos: readonly ConceptoDelReporteRespuesta[];
}) {
  if (conceptos.length === 0) {
    return (
      <div className="empty">
        <div className="empty-title">Nada aquí</div>
        <div className="empty-sub">No hay renglones en esta vista.</div>
      </div>
    );
  }
  return (
    <div className="table-wrap">
      <div className="table-scroll">
        <table className="table" style={{ minWidth: 'max-content' }}>
          <thead>
            <tr>
              <th style={{ minWidth: 90 }}>Clave</th>
              <th style={{ minWidth: 280 }}>Descripción</th>
              <th style={{ minWidth: 130 }}>Frente</th>
              <th style={{ minWidth: 64 }}>Unid.</th>
              <th className="is-num" style={{ minWidth: 90 }}>
                Cantidad
              </th>
              <th className="is-num" style={{ minWidth: 110 }}>
                P.U.
              </th>
              <th className="is-num" style={{ minWidth: 120 }}>
                Importe
              </th>
              <th style={{ minWidth: 190 }}>Respaldo</th>
            </tr>
          </thead>
          <tbody>
            {conceptos.map((c, i) => (
              <tr key={c.actividad_id ?? i}>
                <td className="mono text-xs">
                  {c.fuera_catalogo && <span className="badge badge--outline">EXT</span>}{' '}
                  {c.clave || '—'}
                </td>
                <td>{c.descripcion}</td>
                <td className="text-xs text-mute">{c.nivel_descripcion ?? '—'}</td>
                <td className="mono text-xs">{c.unidad}</td>
                <td className="is-num tnum">{fmtNum(c.cantidad)}</td>
                <td className="is-num tnum">{fmtMXN(c.precio_unitario)}</td>
                <td className="is-num tnum">{fmtMXN(c.importe)}</td>
                <td className="text-xs">
                  {c.alerta === 'sin_confirmar' ? (
                    <span className="badge badge--warn" title="Nadie confirmó este avance">
                      sin confirmar
                    </span>
                  ) : c.alerta === 'por_encima' ? (
                    <span
                      className="badge badge--warn"
                      title={`Se confirmó ${fmtNum(c.cantidad_confirmada)}; se estima más`}
                    >
                      +{fmtNum(c.exceso)} sobre lo confirmado
                    </span>
                  ) : c.actividad_id ? (
                    <span className="badge badge--ok">con respaldo</span>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
