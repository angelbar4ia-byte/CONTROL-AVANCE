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

import { useMemo, useState } from 'react';

import { TipoCarga } from '@/api/generado/modelo';
import {
  useListarClustersApiV1ClustersGet,
  useListarProyectosApiV1ProyectosGet,
  useListarPrototiposApiV1PrototiposGet,
} from '@/api/generado/proyectos/proyectos';
import { getPresupuestoDeObrasApiV1PresupuestosObrasGetQueryKey } from '@/api/generado/presupuesto/presupuesto';
import { queryClient } from '@/app/queryClient';
import { SubirCarga } from '@/cargas/SubirCarga';
import { AltaObra } from '@/proyectos/AltaObra';
import { puedeAdministrarObras } from '@/proyectos/reglas';

import { usePresupuestoDeObrasApiV1PresupuestosObrasGet } from '@/api/generado/presupuesto/presupuesto';
import type { ResumenDeObraRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtMXN, fmtPct } from '@/lib/formato';
import { FilasVirtuales, useTablaVirtual } from '@/lib/tablaVirtual';
import { PanelRendimientos } from './PanelRendimientos';
import {
  esRelevante,
  etiquetaClasificacion,
  resumirPresupuesto,
  textoPorcentaje,
  tonoClasificacion,
} from './reglas';

export default function Presupuesto() {
  const { sesion } = useSesion();
  const [soloDesviadas, setSoloDesviadas] = useState(false);
  const [abierta, setAbierta] = useState<ResumenDeObraRespuesta | null>(null);
  // La entrada del escenario «Ingeniería» (cerebro §8.9): se crea o se elige la obra aquí, se
  // asocia a su prototipo —o se parte del más parecido— y se carga la ingeniería.
  const [dialogo, setDialogo] = useState<'obra' | 'ingenieria' | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const administra = sesion?.rol != null && puedeAdministrarObras(sesion.rol);
  const proyectosQ = useListarProyectosApiV1ProyectosGet({ query: { enabled: administra } });
  const clustersQ = useListarClustersApiV1ClustersGet(undefined, { query: { enabled: administra } });
  const prototiposQ = useListarPrototiposApiV1PrototiposGet(undefined, { query: { enabled: administra } });

  const consulta = usePresupuestoDeObrasApiV1PresupuestosObrasGet<
    ResumenDeObraRespuesta[],
    ErrorApi
  >();

  const filas = useMemo(() => {
    const todas = consulta.data ?? [];
    return soloDesviadas ? todas.filter((f) => esRelevante(f.clasificacion)) : todas;
  }, [consulta.data, soloDesviadas]);

  const resumen = useMemo(() => resumirPresupuesto(filas), [filas]);

  const virtual = useTablaVirtual(filas);

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
      {aviso && (
        <div className="text-sm mb-8" role="status">
          {aviso}
        </div>
      )}

      {(administra || sesion.rol === 'costos') && (
        <div className="row gap-8 mb-8" style={{ flexWrap: 'wrap' }}>
          {administra && (
            <button type="button" className="btn btn--sm" onClick={() => setDialogo('obra')}>
              Nueva obra
            </button>
          )}
          <button type="button" className="btn btn--sm" onClick={() => setDialogo('ingenieria')}>
            Cargar ingeniería
          </button>
        </div>
      )}

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
        <div className="table-scroll" ref={virtual.ref} style={virtual.estilo}>
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
              ) : (
                <FilasVirtuales control={virtual}>
                  {(fila) => (
                    <FilaObra key={fila.obra_id} fila={fila} onAbrir={setAbierta} />
                  )}
                </FilasVirtuales>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {dialogo === 'obra' && (
        <AltaObra
          proyectos={proyectosQ.data ?? []}
          clusters={clustersQ.data ?? []}
          prototipos={prototiposQ.data ?? []}
          onCerrar={() => setDialogo(null)}
          onCreada={() => {
            setDialogo(null);
            setAviso('Obra creada. Cárgale la ingeniería: con su prototipo o partiendo del más parecido.');
            void consulta.refetch();
            void clustersQ.refetch();
          }}
        />
      )}

      {dialogo === 'ingenieria' && (
        <SubirCarga
          tipoInicial={TipoCarga.ingenieria_lote}
          onCerrar={() => setDialogo(null)}
          onAplicada={() => {
            setDialogo(null);
            setAviso('Ingeniería cargada. Si algo no cuadra, abre la obra y mide el renglón.');
            void queryClient.invalidateQueries({
              queryKey: getPresupuestoDeObrasApiV1PresupuestosObrasGetQueryKey(),
            });
          }}
        />
      )}

      {abierta && (
        <PanelRendimientos obra={abierta} onCerrar={() => setAbierta(null)} />
      )}
    </div>
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
