/**
 * Presupuesto de obras — presupuestado contra ejecutado (§5.1, §7.3).
 *
 * Un área entera del §5.1 que tenía sus tablas con RLS desde la migración 0006
 * y ni un endpoint que las leyera.
 *
 * ## Virtualizada (regla 4, §12.9)
 *
 * Es una fila por obra en el alcance, y el §12.1 habla de 60–80 activas. Mismo
 * umbral y mismo mecanismo que la Torre: espaciadores en vez de posicionamiento
 * absoluto, porque un `<tr>` absoluto sale del algoritmo de tabla y las celdas
 * dejan de alinearse con el encabezado.
 *
 * ## Solo lectura
 *
 * El presupuesto entra por carga de Excel y se versiona ahí (§10.8). Una
 * pantalla de captura abriría un segundo camino de alta para el mismo dato, con
 * otro versionado y otra reversa.
 */

import { useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

import { usePresupuestoDeObrasApiV1PresupuestosObrasGet } from '@/api/generado/presupuesto/presupuesto';
import type { ResumenDeObraRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtMXN, fmtPct } from '@/lib/formato';
import { PanelRendimientos } from './PanelRendimientos';
import {
  esRelevante,
  etiquetaClasificacion,
  resumirPresupuesto,
  textoPorcentaje,
  tonoClasificacion,
} from './reglas';

const ALTO_FILA = 41;
const UMBRAL_VIRTUAL = 60;
const ALTO_VISIBLE = 560;

export default function Presupuesto() {
  const { sesion } = useSesion();
  const [soloDesviadas, setSoloDesviadas] = useState(false);
  const [abierta, setAbierta] = useState<ResumenDeObraRespuesta | null>(null);

  const consulta = usePresupuestoDeObrasApiV1PresupuestosObrasGet<
    ResumenDeObraRespuesta[],
    ErrorApi
  >();

  const filas = useMemo(() => {
    const todas = consulta.data ?? [];
    return soloDesviadas ? todas.filter((f) => esRelevante(f.clasificacion)) : todas;
  }, [consulta.data, soloDesviadas]);

  const resumen = useMemo(() => resumirPresupuesto(filas), [filas]);

  const contenedor = useRef<HTMLDivElement>(null);
  const virtualiza = filas.length > UMBRAL_VIRTUAL;
  const virtualizador = useVirtualizer({
    count: virtualiza ? filas.length : 0,
    getScrollElement: () => contenedor.current,
    estimateSize: () => ALTO_FILA,
    overscan: 10,
  });

  if (!sesion) return null;

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Presupuesto</div>
          <h1 className="page__title">Presupuesto de obras</h1>
          <div className="page__subtitle">
            Lo presupuestado contra lo ejecutado, obra por obra (§7.3). El
            presupuesto es del prototipo: todas las obras que lo instancian
            comparten el mismo.
          </div>
        </div>
      </div>

      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}

      <div className="row gap-12 mb-8" style={{ flexWrap: 'wrap' }}>
        <Tarjeta etiqueta="Obras" valor={String(resumen.obras)} />
        <Tarjeta etiqueta="Presupuestado" valor={fmtMXN(resumen.presupuestado)} />
        <Tarjeta etiqueta="Ejecutado" valor={fmtMXN(resumen.ejecutado)} />
        <Tarjeta
          etiqueta="Desviación"
          valor={fmtMXN(resumen.desviacion)}
          tono={resumen.desviacion > 0 ? 'danger' : undefined}
        />
        <Tarjeta
          etiqueta="Con sobre costo"
          valor={String(resumen.sobreCosto)}
          tono={resumen.sobreCosto > 0 ? 'danger' : undefined}
        />
      </div>

      <div className="filterbar">
        <label className="row gap-4" style={{ alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={soloDesviadas}
            onChange={(e) => setSoloDesviadas(e.target.checked)}
          />
          <span className="text-sm">Solo las que se desvían</span>
        </label>
      </div>

      <div className="table-wrap">
        <div
          className="table-scroll"
          ref={contenedor}
          style={virtualiza ? { maxHeight: ALTO_VISIBLE, overflowY: 'auto' } : undefined}
        >
          <table className="table">
            <thead>
              <tr>
                <th>Obra</th>
                <th>Proyecto · cluster</th>
                <th>Prototipo</th>
                <th className="is-num">Avance</th>
                <th className="is-num">Presupuestado</th>
                <th className="is-num">Ejecutado</th>
                <th className="is-num">Desviación</th>
                <th>Estado</th>
                <th className="cell-actions">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={9}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : filas.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      {soloDesviadas
                        ? 'Ninguna obra se desvía del presupuesto.'
                        : 'No hay obras en tu alcance.'}
                    </div>
                  </td>
                </tr>
              ) : virtualiza ? (
                <FilasVirtuales
                  filas={filas}
                  virtualizador={virtualizador}
                  onAbrir={setAbierta}
                />
              ) : (
                filas.map((fila) => (
                  <FilaObra key={fila.obra_id} fila={fila} onAbrir={setAbierta} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {abierta && (
        <PanelRendimientos obra={abierta} onCerrar={() => setAbierta(null)} />
      )}
    </div>
  );
}

/** Ver el comentario del mismo patrón en `torre/Torre.tsx`. */
function FilasVirtuales({
  filas,
  virtualizador,
  onAbrir,
}: {
  readonly filas: readonly ResumenDeObraRespuesta[];
  readonly virtualizador: ReturnType<typeof useVirtualizer<HTMLDivElement, Element>>;
  readonly onAbrir: (fila: ResumenDeObraRespuesta) => void;
}) {
  const visibles = virtualizador.getVirtualItems();
  const antes = visibles.length > 0 ? (visibles[0]?.start ?? 0) : 0;
  const despues =
    visibles.length > 0
      ? virtualizador.getTotalSize() - (visibles[visibles.length - 1]?.end ?? 0)
      : 0;

  return (
    <>
      {antes > 0 && <tr style={{ height: antes }} aria-hidden="true" />}
      {visibles.map((item) => {
        const fila = filas[item.index];
        if (fila === undefined) return null;
        return <FilaObra key={fila.obra_id} fila={fila} onAbrir={onAbrir} />;
      })}
      {despues > 0 && <tr style={{ height: despues }} aria-hidden="true" />}
    </>
  );
}

function FilaObra({
  fila,
  onAbrir,
}: {
  readonly fila: ResumenDeObraRespuesta;
  readonly onAbrir: (fila: ResumenDeObraRespuesta) => void;
}) {
  return (
    <tr>
      <td className="is-key">{fila.obra_clave}</td>
      <td className="text-sm">
        {fila.proyecto_clave} · {fila.cluster_clave}
      </td>
      <td className="text-sm">
        {/* Una obra URBA no tiene prototipo, y por lo tanto no tiene
            presupuesto (§7.2). Se dice, en vez de mostrar un cero mudo. */}
        {fila.es_urba ? <span className="text-mute">URBA</span> : (fila.prototipo_clave ?? '—')}
      </td>
      <td className="is-num mono">{fmtPct(Number(fila.avance_pct))}</td>
      <td className="is-num mono">{fmtMXN(Number(fila.monto_presupuestado))}</td>
      <td className="is-num mono">{fmtMXN(Number(fila.monto_ejecutado))}</td>
      <td className="is-num mono">
        {fmtMXN(Number(fila.desviacion_importe))}
        <span className="text-xs text-mute"> {textoPorcentaje(fila.desviacion_pct)}</span>
      </td>
      <td>
        <span className={`badge badge--${tonoClasificacion(fila.clasificacion)}`}>
          {etiquetaClasificacion(fila.clasificacion)}
        </span>
      </td>
      <td className="cell-actions">
        <button type="button" className="btn btn--sm" onClick={() => onAbrir(fila)}>
          Abrir
        </button>
      </td>
    </tr>
  );
}

function Tarjeta({
  etiqueta,
  valor,
  tono,
}: {
  readonly etiqueta: string;
  readonly valor: string;
  readonly tono?: string;
}) {
  return (
    <div className="card" style={{ minWidth: 150 }}>
      <div className="card__body col gap-2">
        <span className="text-xs text-mute">{etiqueta}</span>
        <span
          className="is-key mono"
          style={{ fontSize: 18, color: tono ? `var(--c-${tono})` : undefined }}
        >
          {valor}
        </span>
      </div>
    </div>
  );
}
