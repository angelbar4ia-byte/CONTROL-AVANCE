/**
 * Avances — captura de avance de actividades (§11.2 "Ejecución · Avance").
 *
 * Rol: Residente. Ruta `/avances` (`shell/navegacion.ts`).
 *
 * ## Limitación conocida
 *
 * El contrato actual **no expone** `GET /obras/{id}/actividades` ni
 * `GET /actividades/{id}` (están en el spec §11.2 pero el módulo `avance`
 * del backend solo implementa `PATCH /actividades/{id}/avance`, ver
 * `backend/src/obractrl/adapters/api/v1/avance.py`). Sin un endpoint de
 * listado no hay forma de mostrar "las actividades de la obra del
 * Residente": esta pantalla captura avance por `actividad_id` (UUID, se
 * pega desde otra pantalla/reporte) y mantiene una bitácora **de la
 * sesión actual** con lo capturado — no un listado real de actividades.
 * Cuando exista el endpoint de listado, esta pantalla debe cambiar el
 * formulario manual por una tabla seleccionable (§12.9).
 */

import { useState, type FormEvent } from 'react';

import { useCapturarAvanceApiV1ActividadesActividadIdAvancePatch } from '@/api/generado/avance/avance';
import type { AvanceRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { colorAvance, fmtFecha, fmtNum, fmtPct } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { advertenciasAvance, tonoEstatusActividad } from './reglas';

interface CapturaSesion {
  readonly actividadId: string;
  readonly fecha: string;
  readonly respuesta: AvanceRespuesta;
}

const HOY = () => new Date().toISOString().slice(0, 10);

export default function Avances() {
  const [capturas, setCapturas] = useState<readonly CapturaSesion[]>([]);
  const [actividadId, setActividadId] = useState('');
  const [cantEjecutada, setCantEjecutada] = useState('');
  const [cantProgramada, setCantProgramada] = useState('');
  const [fecha, setFecha] = useState('');
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const mutacion = useCapturarAvanceApiV1ActividadesActividadIdAvancePatch<ErrorApi>({
    mutation: {
      onSuccess: (respuesta) => {
        setError(null);
        setCapturas((previas) => [
          { actividadId, fecha: fecha || HOY(), respuesta },
          ...previas.filter((c) => c.actividadId !== actividadId),
        ]);
        setCantEjecutada('');
        setCantProgramada('');
      },
      onError: (err) => {
        setError({ mensaje: err.message, campo: err.campo });
      },
    },
  });

  // Cant. base conocida de esta actividad si ya se capturó en la sesión
  // (§6 solo se puede reflejar en UX una vez que el backend la reveló).
  const cantBaseConocida =
    capturas.find((c) => c.actividadId === actividadId)?.respuesta.cant_base ?? null;

  const advertencias = advertenciasAvance({
    cantBase: cantBaseConocida !== null ? Number(cantBaseConocida) : null,
    cantProgramada: cantProgramada.trim() === '' ? null : Number(cantProgramada),
    cantEjecutada: cantEjecutada.trim() === '' ? null : Number(cantEjecutada),
  });

  const puedeEnviar =
    actividadId.trim() !== '' &&
    cantEjecutada.trim() !== '' &&
    !Number.isNaN(Number(cantEjecutada)) &&
    !advertencias.cantEjecutadaExcedeProgramada &&
    !mutacion.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;

    mutacion.mutate({
      actividadId,
      data: {
        cant_ejecutada: cantEjecutada,
        cant_programada: cantProgramada.trim() === '' ? undefined : cantProgramada,
        fecha: fecha.trim() === '' ? undefined : fecha,
        evidencias: [],
      },
    });
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Ejecución</div>
          <h1 className="page__title">Avances</h1>
          <div className="page__subtitle">
            Captura de avance por actividad (§6). Las cantidades se validan de
            forma autoritativa en el servidor.
          </div>
        </div>
      </div>

      <div className="card mb-8">
        <div className="card__header">
          <div>
            <h2 className="card__title">Registrar avance</h2>
            <div className="card__sub mono">
              cant_programada ≤ cant_base × 1.2 · cant_ejecutada ≤ cant_programada
            </div>
          </div>
        </div>
        <div className="card__body">
          <form onSubmit={alEnviar} className="col gap-12">
            <div className="row gap-12" style={{ flexWrap: 'wrap' }}>
              <div className="field" style={{ minWidth: 280, flex: 2 }}>
                <label className="field__label" htmlFor="actividad-id">
                  ID de actividad
                </label>
                <input
                  id="actividad-id"
                  className="input input--mono"
                  placeholder="uuid de la actividad"
                  value={actividadId}
                  onChange={(e) => setActividadId(e.target.value)}
                  required
                />
                {cantBaseConocida !== null && (
                  <div className="field__hint mono tnum">
                    cant_base conocida: {fmtNum(cantBaseConocida)}
                  </div>
                )}
              </div>

              <div className="field" style={{ minWidth: 160, flex: 1 }}>
                <label className="field__label" htmlFor="cant-programada">
                  Cant. programada (opcional)
                </label>
                <input
                  id="cant-programada"
                  className="input input--mono"
                  type="number"
                  step="any"
                  min="0"
                  value={cantProgramada}
                  onChange={(e) => setCantProgramada(e.target.value)}
                />
                {advertencias.cantProgramadaExcedeBase && (
                  <div className="field__hint" style={{ color: 'var(--c-warn)' }}>
                    Excede cant_base × 1.2 — el servidor puede rechazarla.
                  </div>
                )}
              </div>

              <div className="field" style={{ minWidth: 160, flex: 1 }}>
                <label className="field__label" htmlFor="cant-ejecutada">
                  Cant. ejecutada
                </label>
                <input
                  id="cant-ejecutada"
                  className="input input--mono"
                  type="number"
                  step="any"
                  min="0"
                  value={cantEjecutada}
                  onChange={(e) => setCantEjecutada(e.target.value)}
                  required
                />
                {advertencias.cantEjecutadaExcedeProgramada && (
                  <div className="field__hint" style={{ color: 'var(--c-danger)' }}>
                    No puede exceder la cantidad programada.
                  </div>
                )}
              </div>

              <div className="field" style={{ minWidth: 160, flex: 1 }}>
                <label className="field__label" htmlFor="fecha">
                  Fecha (opcional)
                </label>
                <input
                  id="fecha"
                  className="input"
                  type="date"
                  value={fecha}
                  onChange={(e) => setFecha(e.target.value)}
                />
              </div>
            </div>

            {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}

            <div className="row">
              <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
                {mutacion.isPending ? 'Guardando…' : 'Registrar avance'}
              </button>
            </div>
          </form>
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Actividad</th>
                <th>Fecha</th>
                <th className="is-num">Cant. base</th>
                <th className="is-num">Cant. programada</th>
                <th className="is-num">Cant. ejecutada</th>
                <th>Avance</th>
                <th>Estatus</th>
              </tr>
            </thead>
            <tbody>
              {capturas.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Aún no hay avances capturados en esta sesión.
                    </div>
                  </td>
                </tr>
              ) : (
                capturas.map((c) => {
                  const pct = Number(c.respuesta.avance_pct);
                  const tono = colorAvance(pct);
                  return (
                    <tr key={c.actividadId}>
                      <td className="is-key">{c.actividadId}</td>
                      <td>{fmtFecha(c.fecha)}</td>
                      <td className="is-num">{fmtNum(c.respuesta.cant_base)}</td>
                      <td className="is-num">{fmtNum(c.respuesta.cant_programada)}</td>
                      <td className="is-num">{fmtNum(c.respuesta.cant_ejecutada)}</td>
                      <td>
                        <div className={`bar ${tono !== 'accent' ? `bar--${tono}` : ''}`}>
                          <div
                            className="bar__fill"
                            style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                          />
                        </div>
                        <div className="text-mute text-xs mono tnum mt-8">{fmtPct(pct)}</div>
                      </td>
                      <td>
                        <span className={`badge badge--${tonoEstatusActividad(c.respuesta.estatus)}`}>
                          {c.respuesta.estatus}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
