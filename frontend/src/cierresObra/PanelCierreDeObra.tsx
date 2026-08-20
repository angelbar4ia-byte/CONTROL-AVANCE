/**
 * El acta de una obra: qué falta y quién ha firmado (§11.3 D).
 *
 * ## Dos bloques de pendientes, no uno
 *
 * Los que **impiden entregar** —avance incompleto, trabajo sin concluir, dinero
 * sin validar— y los que solo hay que mirar —expediente vacío, evaluación
 * ausente—. Mezclarlos haría que un expediente vacío se viera igual de grave
 * que una estimación sin validar, y entonces nadie miraría ninguno.
 *
 * ## El botón de firmar aparece por rol, no por persona
 *
 * `uq_cierre_obra_participacion` es por `(cierre, rol)`: si otro residente ya
 * firmó, este no vuelve a hacerlo. La pantalla lo dice así para que nadie
 * espere un botón que no va a aparecer.
 */

import { useMemo, useState } from 'react';

import {
  useListarParticipacionesApiV1CierresObraCierreIdParticipacionesGet,
  useObtenerCierreDeObraApiV1CierresObraCierreIdGet,
  useParticiparApiV1CierresObraCierreIdParticiparPost,
} from '@/api/generado/cierres-obra/cierres-obra';
import type { CierreDeObraRespuesta } from '@/api/generado/modelo';
import { claveDeIdempotencia, type ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { fmtFecha } from '@/lib/formato';
import {
  aportacionDe,
  estadoDeActa,
  etiquetaEstado,
  etiquetaRol,
  leTocaFirmar,
  separarPendientes,
  tonoEstado,
} from './reglas';

interface Props {
  readonly cierreId: string;
  readonly onCerrar: () => void;
  readonly onCambio: () => void;
}

export function PanelCierreDeObra({ cierreId, onCerrar, onCambio }: Props) {
  const { sesion } = useSesion();
  const [comentario, setComentario] = useState('');
  const [acta, setActa] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [entregada, setEntregada] = useState(false);

  // Una clave por acta: firmar dos veces la misma es lo que el backend rechaza,
  // y el doble clic no debe ser lo que lo provoque.
  const clave = useMemo(claveDeIdempotencia, []);

  const consulta = useObtenerCierreDeObraApiV1CierresObraCierreIdGet<
    CierreDeObraRespuesta,
    ErrorApi
  >(cierreId);

  const participaciones =
    useListarParticipacionesApiV1CierresObraCierreIdParticipacionesGet(cierreId);

  const participar = useParticiparApiV1CierresObraCierreIdParticiparPost<ErrorApi>({
    mutation: {
      onSuccess: (resultado) => {
        setError(null);
        setComentario('');
        setActa('');
        // `?? false`: el campo es opcional en el contrato porque solo viene
        // en la participación que completa el acta.
        setEntregada(resultado.cerro_la_obra ?? false);
        void consulta.refetch();
        void participaciones.refetch();
        onCambio();
      },
      onError: (err) => setError(err.message),
    },
    request: { headers: { 'Idempotency-Key': clave } },
  });

  if (!sesion) return null;

  const cierre = consulta.data;

  return (
    <Sheet
      titulo="Cierre de obra"
      subtitulo={cierre ? `Acta ${cierre.estatus}` : undefined}
      onCerrar={onCerrar}
    >
      <div className="sheet__body col gap-12">
        {error && <ErrorBanner mensaje={error} />}

        {entregada && (
          <div className="badge badge--ok">
            Firmada por los cuatro roles: la obra quedó entregada y congelada
            (§11.3 D.3).
          </div>
        )}

        {consulta.isLoading || cierre === undefined ? (
          <div className="text-mute text-sm">Cargando el acta…</div>
        ) : (
          <>
            <div className="row gap-8">
              <span className={`badge badge--${tonoEstado(estadoDeActa(cierre))}`}>
                {etiquetaEstado(estadoDeActa(cierre))}
              </span>
            </div>

            <Pendientes cierre={cierre} />

            <hr className="sep" />

            <div className="field">
              <div className="field__label">Partes del acta (§11.3 D.2)</div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Rol</th>
                    <th>Aporta</th>
                    <th>Quién</th>
                    <th>Comentario</th>
                  </tr>
                </thead>
                <tbody>
                  {(['residente', 'supervisor', 'control_obra', 'super_intendente'] as const).map(
                    (rol) => {
                      const parte = (participaciones.data ?? []).find(
                        (p) => p.rol === rol,
                      );
                      return (
                        <tr key={rol} className={parte ? '' : 'is-muted'}>
                          <td className="is-key">{etiquetaRol(rol)}</td>
                          <td className="text-sm">{aportacionDe(rol)}</td>
                          <td className="text-sm">
                            {parte ? (
                              <>
                                {parte.usuario_nombre ?? '—'}
                                <span className="text-xs text-mute">
                                  {' '}
                                  {fmtFecha(parte.fecha)}
                                </span>
                              </>
                            ) : (
                              <span className="text-mute">Sin firmar</span>
                            )}
                          </td>
                          <td className="text-sm">{parte?.comentario ?? '—'}</td>
                        </tr>
                      );
                    },
                  )}
                </tbody>
              </table>
            </div>

            {leTocaFirmar(cierre, sesion.rol) && (
              <>
                <hr className="sep" />
                <div className="field">
                  <label className="field__label" htmlFor="cierre-comentario">
                    Tu parte: {aportacionDe(sesion.rol).toLowerCase()}
                  </label>
                  <textarea
                    id="cierre-comentario"
                    className="input"
                    rows={3}
                    value={comentario}
                    onChange={(e) => setComentario(e.target.value)}
                    placeholder="Qué observas al entregar tu parte"
                  />
                </div>

                {/* El acta la escribe quien firma al final: es el documento del
                    cierre, no de cada parte. */}
                {sesion.rol === 'super_intendente' && cierre.faltan.length === 1 && (
                  <div className="field">
                    <label className="field__label" htmlFor="cierre-acta">
                      Acta de entrega
                    </label>
                    <textarea
                      id="cierre-acta"
                      className="input"
                      rows={3}
                      value={acta}
                      onChange={(e) => setActa(e.target.value)}
                      placeholder="Texto del acta con el que se entrega la obra"
                    />
                  </div>
                )}

                {!cierre.puede_cerrarse && cierre.faltan.length === 1 && (
                  <div className="badge badge--danger">
                    Con tu firma se completa el acta, pero todavía hay pendientes
                    que impiden entregar. Resuélvelos antes.
                  </div>
                )}

                <button
                  type="button"
                  className="btn btn--primary"
                  style={{ alignSelf: 'flex-start' }}
                  disabled={participar.isPending}
                  onClick={() =>
                    participar.mutate({
                      cierreId,
                      data: {
                        comentario: comentario.trim() || null,
                        acta: acta.trim() || null,
                      },
                    })
                  }
                >
                  {participar.isPending ? 'Registrando…' : 'Registrar mi parte'}
                </button>
              </>
            )}

            {!leTocaFirmar(cierre, sesion.rol) && cierre.estatus === 'en_proceso' && (
              <div className="field__hint">
                {cierre.participaron.includes(sesion.rol)
                  ? 'Tu rol ya registró su parte: la participación es del rol, no de la persona.'
                  : 'Tu rol no participa en este acta.'}
              </div>
            )}
          </>
        )}
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cerrar
        </button>
      </div>
    </Sheet>
  );
}

function Pendientes({ cierre }: { readonly cierre: CierreDeObraRespuesta }) {
  const { bloqueantes, avisos } = separarPendientes(cierre);

  if (bloqueantes.length === 0 && avisos.length === 0) {
    return (
      <div className="badge badge--ok">
        Sin pendientes: la obra está lista para entregarse.
      </div>
    );
  }

  return (
    <div className="col gap-8">
      {bloqueantes.length > 0 && (
        <div className="field">
          <div className="field__label">Impiden entregar</div>
          <ul className="col gap-4" style={{ margin: 0, paddingLeft: 18 }}>
            {bloqueantes.map((p) => (
              <li key={p.clave} className="text-sm">
                {p.detalle}
              </li>
            ))}
          </ul>
        </div>
      )}

      {avisos.length > 0 && (
        <div className="field">
          <div className="field__label">Conviene revisarlos</div>
          <div className="field__hint">
            No impiden firmar, pero se entregaría sin ellos.
          </div>
          <ul className="col gap-4" style={{ margin: 0, paddingLeft: 18 }}>
            {avisos.map((p) => (
              <li key={p.clave} className="text-sm text-mute">
                {p.detalle}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
