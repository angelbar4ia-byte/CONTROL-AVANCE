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

import { useMemo, useState } from 'react';

import { useTorreDeControlApiV1TorreGet } from '@/api/generado/torre/torre';
import type { EstadoDeObraRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtPct } from '@/lib/formato';
import { FilasVirtuales, useTablaVirtual } from '@/lib/tablaVirtual';
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

  // Virtualizada desde el día uno (regla 4, §12.9): el §12.1 habla de 60–80
  // obras activas y el Gantt ya enseñó que el umbral llega antes de lo que uno
  // cree.
  const virtual = useTablaVirtual(obras);

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
        <div className="table-scroll" ref={virtual.ref} style={virtual.estilo}>
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
              ) : (
                <FilasVirtuales control={virtual}>
                  {(obra) => (
                    <FilaObra key={obra.obra_id} obra={obra} onAbrir={setAbierta} />
                  )}
                </FilasVirtuales>
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
