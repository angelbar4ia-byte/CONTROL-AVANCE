/**
 * Torre de control — dónde está cada obra y qué le toca hoy (§5.1, §5.3).
 *
 * Es la pantalla donde **aterrizan tres de los cuatro roles**: Supervisor,
 * Control de obra y Super intendente la tienen como primera entrada. Hasta
 * ahora caían en Cierres como sustituto, con un comentario en `App.tsx` que lo
 * decía.
 *
 * ## Una implementación, no tres
 *
 * Pantalla compartida del §5.3: lo que cambia por rol es el **alcance** —que ya
 * resolvió RLS antes de que la respuesta salga del servidor— y una línea de
 * texto que dice qué le toca a quien mira. No hay ramas por rol en el render, y
 * eso es deliberado: tres copias de la misma tabla se desincronizan.
 *
 * ## Virtualizada desde el día uno (regla 4 del ROADMAP, §12.9)
 *
 * El §12.1 habla de 60–80 obras activas, y el Gantt ya enseñó que el umbral
 * llega antes de lo que uno cree. Se virtualiza pasado el umbral y por debajo
 * se pinta la tabla completa, que es más simple de leer y de depurar.
 */

import { useMemo, useRef, useState } from 'react';

import { useTorreDeControlApiV1TorreGet } from '@/api/generado/torre/torre';
import type { EstadoDeObraRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtPct } from '@/lib/formato';
import { useVirtualizer } from '@tanstack/react-virtual';
import { PanelObraTorre } from './PanelObraTorre';
import {
  etiquetaUrgencia,
  filtrarObras,
  resumirTorre,
  subtituloDeTorre,
  tituloDeTorre,
  tonoUrgencia,
  urgenciaDe,
} from './reglas';

/** Alto de `.table tbody tr` en el sistema de diseño. */
const ALTO_FILA = 41;

/** A partir de aquí se virtualiza. Por debajo, el DOM completo es más simple. */
const UMBRAL_VIRTUAL = 60;

const ALTO_VISIBLE = 560;

export default function Torre() {
  const { sesion } = useSesion();
  const [soloPendientes, setSoloPendientes] = useState(false);
  const [busqueda, setBusqueda] = useState('');
  const [abierta, setAbierta] = useState<EstadoDeObraRespuesta | null>(null);

  const consulta = useTorreDeControlApiV1TorreGet<EstadoDeObraRespuesta[], ErrorApi>({
    solo_pendientes: soloPendientes,
  });

  const obras = useMemo(
    () => filtrarObras(consulta.data ?? [], busqueda),
    [consulta.data, busqueda],
  );
  const resumen = useMemo(() => resumirTorre(obras), [obras]);

  const contenedor = useRef<HTMLDivElement>(null);
  const virtualiza = obras.length > UMBRAL_VIRTUAL;
  const virtualizador = useVirtualizer({
    count: virtualiza ? obras.length : 0,
    getScrollElement: () => contenedor.current,
    estimateSize: () => ALTO_FILA,
    overscan: 10,
  });

  if (!sesion) return null;

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Control</div>
          <h1 className="page__title">{tituloDeTorre(sesion.rol)}</h1>
          <div className="page__subtitle">{subtituloDeTorre(sesion.rol)}</div>
        </div>
      </div>

      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}

      <div className="row gap-12 mb-8" style={{ flexWrap: 'wrap' }}>
        <Tarjeta etiqueta="Obras" valor={resumen.obras} />
        <Tarjeta etiqueta="Detenidas" valor={resumen.detenidas} tono="danger" />
        <Tarjeta etiqueta="Con pendientes" valor={resumen.pendientes} tono="warn" />
        <Tarjeta etiqueta="Al corriente" valor={resumen.alCorriente} tono="ok" />
        <Tarjeta etiqueta="Cierres por resolver" valor={resumen.cierresPendientes} />
        <Tarjeta etiqueta="Incidencias abiertas" valor={resumen.incidenciasAbiertas} />
      </div>

      <div className="filterbar">
        <div className="field" style={{ minWidth: 260 }}>
          <label className="field__label" htmlFor="torre-busqueda">
            Buscar
          </label>
          <input
            id="torre-busqueda"
            className="input"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Obra, cluster, proyecto o residente"
          />
        </div>
        <label className="row gap-4" style={{ alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={soloPendientes}
            onChange={(e) => setSoloPendientes(e.target.checked)}
          />
          <span className="text-sm">Solo las que esperan algo</span>
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
                <th>Residente</th>
                <th>Estado</th>
                <th className="is-num">Avance</th>
                <th className="is-num">Actividades</th>
                <th className="is-num">Críticas</th>
                <th className="is-num">Cierres</th>
                <th className="is-num">Incidencias</th>
                <th className="cell-actions">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={10}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : obras.length === 0 ? (
                <tr>
                  <td colSpan={10}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      {soloPendientes
                        ? 'Nada esperando. Todas tus obras están al corriente.'
                        : 'No hay obras en tu alcance.'}
                    </div>
                  </td>
                </tr>
              ) : virtualiza ? (
                <FilasVirtuales
                  obras={obras}
                  virtualizador={virtualizador}
                  onAbrir={setAbierta}
                />
              ) : (
                obras.map((obra) => (
                  <FilaObra key={obra.obra_id} obra={obra} onAbrir={setAbierta} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {abierta && (
        <PanelObraTorre
          obra={abierta}
          onCerrar={() => setAbierta(null)}
          onCambio={() => void consulta.refetch()}
        />
      )}
    </div>
  );
}

/**
 * Las filas virtualizadas dentro de un `<tbody>`.
 *
 * El truco de las dos filas espaciadoras —una arriba y otra abajo, con la
 * altura de lo que no se pinta— existe porque una tabla no admite hijos
 * posicionados en absoluto sin romper el reparto de columnas: `position:
 * absolute` sobre un `<tr>` lo saca del algoritmo de tabla y las celdas dejan
 * de alinearse con el `<thead>`. Con espaciadores, la tabla sigue siendo una
 * tabla y el navegador sigue alineando.
 */
function FilasVirtuales({
  obras,
  virtualizador,
  onAbrir,
}: {
  readonly obras: readonly EstadoDeObraRespuesta[];
  readonly virtualizador: ReturnType<typeof useVirtualizer<HTMLDivElement, Element>>;
  readonly onAbrir: (obra: EstadoDeObraRespuesta) => void;
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
        const obra = obras[item.index];
        if (obra === undefined) return null;
        return <FilaObra key={obra.obra_id} obra={obra} onAbrir={onAbrir} />;
      })}
      {despues > 0 && <tr style={{ height: despues }} aria-hidden="true" />}
    </>
  );
}

function FilaObra({
  obra,
  onAbrir,
}: {
  readonly obra: EstadoDeObraRespuesta;
  readonly onAbrir: (obra: EstadoDeObraRespuesta) => void;
}) {
  const urgencia = urgenciaDe(obra);
  return (
    <tr>
      <td className="is-key">{obra.obra_clave}</td>
      <td className="text-sm">
        {obra.proyecto_clave} · {obra.cluster_clave}
      </td>
      <td className="text-sm">{obra.residente_nombre ?? '—'}</td>
      <td>
        <span className={`badge badge--${tonoUrgencia(urgencia)}`}>
          {etiquetaUrgencia(urgencia)}
        </span>
      </td>
      <td className="is-num mono">{fmtPct(Number(obra.avance_pct))}</td>
      <td className="is-num mono">{obra.actividades}</td>
      <td className="is-num mono">{obra.criticas}</td>
      <td className="is-num mono">
        {obra.cierres_pendientes > 0 ? (
          <span className="badge badge--warn">{obra.cierres_pendientes}</span>
        ) : (
          '—'
        )}
      </td>
      <td className="is-num mono">
        {obra.incidencias_abiertas > 0 ? (
          <span
            className={`badge badge--${obra.incidencias_detienen > 0 ? 'danger' : 'warn'}`}
          >
            {obra.incidencias_abiertas}
          </span>
        ) : (
          '—'
        )}
      </td>
      <td className="cell-actions">
        <button type="button" className="btn btn--sm" onClick={() => onAbrir(obra)}>
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
  readonly valor: number;
  readonly tono?: string;
}) {
  return (
    <div className="card" style={{ minWidth: 140 }}>
      <div className="card__body col gap-2">
        <span className="text-xs text-mute">{etiqueta}</span>
        <span
          className="is-key mono"
          style={{ fontSize: 22, color: tono ? `var(--c-${tono})` : undefined }}
        >
          {valor}
        </span>
      </div>
    </div>
  );
}
