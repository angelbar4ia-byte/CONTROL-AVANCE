/**
 * Avance total — el reporte por alcance (§11.2, §5.1).
 *
 * La entrada «Reportes → Avance total» del Super intendente caía en "en
 * construcción" porque el reporte que la sostiene, `POST /reportes/{tipo}`, no
 * existía hasta la Fase 16.
 *
 * ## No es la Torre en otra pestaña
 *
 * La Torre es para operar hoy: se entra a una obra, se ve qué la detiene. Esta
 * pantalla es para **llevarse el número a una junta**: los mismos datos
 * agregados y un `.xlsx` que se puede mandar por correo. Por eso arriba están
 * los totales y abajo el botón, y no una tabla que duplica la Torre.
 *
 * ## Los dos avances dicen cosas distintas
 *
 * `avance_por_actividades` es un conteo —concluidas ÷ totales—;
 * `avance_promedio_simple` es la media de los porcentajes de cada obra. Con
 * obras de distinto tamaño pueden diferir muchísimo, y por eso se muestran los
 * dos con su nombre completo en vez de un único "avance" que cada quien
 * interpretaría a su manera (`domain/reportes/avance.py`).
 *
 * El **avance ponderado por dinero** no está, aquí ni en el reporte: exige
 * decidir contra qué se pondera y el spec no lo fija. Esa decisión vive en
 * Presupuesto (§5.1).
 */

import { useState } from 'react';

import { useEncolarReporteApiV1ReportesTipoPost } from '@/api/generado/reportes/reportes';
import { useTorreDeControlApiV1TorreGet } from '@/api/generado/torre/torre';
import type { EstadoDeObraRespuesta, TrabajoRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtNum } from '@/lib/formato';
import { SeguimientoDeReporte } from './SeguimientoDeReporte';

export default function AvanceTotal() {
  const { sesion } = useSesion();
  const [reporteId, setReporteId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Los mismos datos que alimentan el reporte del worker: la vista previa sale
  // de `/torre` y el `.xlsx` de `ArmarReporteDeAvance`, que consulta lo mismo.
  // Si divergieran, la pantalla y el archivo dirían números distintos sobre la
  // misma cartera.
  const torre = useTorreDeControlApiV1TorreGet<EstadoDeObraRespuesta[], ErrorApi>();

  const encolar = useEncolarReporteApiV1ReportesTipoPost<ErrorApi>({
    mutation: {
      onSuccess: (trabajo) => {
        setError(null);
        setReporteId((trabajo as TrabajoRespuesta).id);
      },
      onError: (err) => setError(err.message),
    },
  });

  if (!sesion) return null;

  const obras = torre.data ?? [];
  const totales = agregar(obras);

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Reportes</div>
          <h1 className="page__title">Avance total</h1>
          <div className="page__subtitle">
            Las obras de tu alcance, agregadas. El archivo se genera en segundo plano (§11.2).
          </div>
        </div>
        <div className="page__actions">
          <button
            type="button"
            className="btn btn--primary"
            disabled={encolar.isPending}
            onClick={() => encolar.mutate({ tipo: 'avance', data: {} })}
          >
            {encolar.isPending ? 'Encolando…' : 'Generar Excel'}
          </button>
        </div>
      </div>

      {error && <ErrorBanner mensaje={error} />}
      {torre.error && <ErrorBanner mensaje={torre.error.message} />}

      {reporteId && (
        <SeguimientoDeReporte
          reporteId={reporteId}
          titulo="Avance total"
          onCerrar={() => setReporteId(null)}
        />
      )}

      <div className="row gap-8 mb-8">
        <Tarjeta etiqueta="Obras" valor={fmtNum(totales.obras)} />
        <Tarjeta
          etiqueta="Avance por actividades"
          valor={`${fmtNum(totales.avancePorActividades)} %`}
          nota={`${fmtNum(totales.concluidas)} de ${fmtNum(totales.actividades)} concluidas`}
        />
        <Tarjeta
          etiqueta="Avance promedio simple"
          valor={`${fmtNum(totales.promedioSimple)} %`}
          nota="Media de los porcentajes, sin ponderar"
        />
        <Tarjeta
          etiqueta="Requieren atención"
          valor={fmtNum(totales.conPendientes)}
          nota="Bloqueadas, con incidencia abierta o con cierre esperando"
        />
      </div>

      {torre.isLoading ? (
        <div className="empty">
          <div className="empty-title">Cargando…</div>
        </div>
      ) : obras.length === 0 ? (
        <div className="empty">
          <div className="empty-title">No hay obras en tu alcance</div>
          <div className="empty-sub">El alcance lo resuelve RLS, no esta pantalla (§4).</div>
        </div>
      ) : (
        <div className="card">
          <div className="card__header">
            <h2 className="card__title">Por proyecto</h2>
          </div>
          <div className="card__body">
            <table className="table">
              <thead>
                <tr>
                  <th>Proyecto</th>
                  <th className="num">Obras</th>
                  <th className="num">Actividades</th>
                  <th className="num">Concluidas</th>
                  <th className="num">Avance</th>
                  <th className="num">Atención</th>
                </tr>
              </thead>
              <tbody>
                {porProyecto(obras).map((fila) => (
                  <tr key={fila.proyecto}>
                    <td className="mono">{fila.proyecto}</td>
                    <td className="num mono">{fmtNum(fila.obras)}</td>
                    <td className="num mono">{fmtNum(fila.actividades)}</td>
                    <td className="num mono">{fmtNum(fila.concluidas)}</td>
                    <td className="num mono">{fmtNum(fila.avance)} %</td>
                    <td className="num mono">{fmtNum(fila.conPendientes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Tarjeta({
  etiqueta,
  valor,
  nota,
}: {
  readonly etiqueta: string;
  readonly valor: string;
  readonly nota?: string;
}) {
  return (
    <div className="card" style={{ flex: 1 }}>
      <div className="card__body col gap-4">
        <div className="text-mute text-sm">{etiqueta}</div>
        <div className="mono" style={{ fontSize: 'var(--fs-2xl)' }}>
          {valor}
        </div>
        {nota && <div className="text-mute text-sm">{nota}</div>}
      </div>
    </div>
  );
}

interface Totales {
  readonly obras: number;
  readonly actividades: number;
  readonly concluidas: number;
  readonly avancePorActividades: number;
  readonly promedioSimple: number;
  readonly conPendientes: number;
}

/**
 * Los mismos totales que calcula `domain/reportes/avance.py`.
 *
 * Sí, están dos veces —aquí y en Python— y eso normalmente sería una copia
 * peligrosa. Se acepta porque son sumas sobre las filas que la propia
 * respuesta ya trae, no una regla de negocio: el `avance_pct` de cada obra lo
 * derivó la base con la fórmula del §6, y ninguno de los dos lados lo
 * recalcula. Lo que no se duplica es lo que sí sería una regla —el avance
 * ponderado— porque no existe en ninguno.
 */
export function agregar(obras: readonly EstadoDeObraRespuesta[]): Totales {
  const actividades = obras.reduce((suma, o) => suma + o.actividades, 0);
  const concluidas = obras.reduce((suma, o) => suma + o.concluidas, 0);
  const suma = obras.reduce((total, o) => total + Number(o.avance_pct ?? 0), 0);

  return {
    obras: obras.length,
    actividades,
    concluidas,
    // División protegida: una cartera recién dada de alta no tiene actividades
    // hasta que se genera desde el prototipo (§11.3 A).
    avancePorActividades: actividades === 0 ? 0 : redondear((concluidas * 100) / actividades),
    promedioSimple: obras.length === 0 ? 0 : redondear(suma / obras.length),
    conPendientes: obras.filter(requiereAtencion).length,
  };
}

/** Mismo criterio que la Torre y que el reporte: lo que espera a alguien. */
export function requiereAtencion(obra: EstadoDeObraRespuesta): boolean {
  return (
    obra.bloqueadas > 0 ||
    obra.incidencias_detienen > 0 ||
    obra.incidencias_abiertas > 0 ||
    obra.cierres_pendientes > 0
  );
}

interface FilaProyecto {
  readonly proyecto: string;
  readonly obras: number;
  readonly actividades: number;
  readonly concluidas: number;
  readonly avance: number;
  readonly conPendientes: number;
}

/**
 * Agrupa por proyecto. El avance de la fila es **por actividades**, no el
 * promedio de las obras: dentro de un proyecto las obras son comparables en
 * número de actividades y el conteo es el que suma sin ponderaciones.
 */
export function porProyecto(obras: readonly EstadoDeObraRespuesta[]): FilaProyecto[] {
  const grupos = new Map<string, EstadoDeObraRespuesta[]>();
  for (const obra of obras) {
    const clave = obra.proyecto_clave || '(sin proyecto)';
    grupos.set(clave, [...(grupos.get(clave) ?? []), obra]);
  }

  return [...grupos.entries()]
    .map(([proyecto, delGrupo]) => {
      const totales = agregar(delGrupo);
      return {
        proyecto,
        obras: totales.obras,
        actividades: totales.actividades,
        concluidas: totales.concluidas,
        avance: totales.avancePorActividades,
        conPendientes: totales.conPendientes,
      };
    })
    .sort((a, b) => a.proyecto.localeCompare(b.proyecto));
}

function redondear(valor: number): number {
  return Math.round(valor * 100) / 100;
}
