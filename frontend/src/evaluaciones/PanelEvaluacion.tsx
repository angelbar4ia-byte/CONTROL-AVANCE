/**
 * Detalle de una evaluación: criterios y respuestas (§7.8, §11.2).
 *
 * Los criterios salen de `GET /criterios-evaluacion?aplica_a=…` —catálogo
 * configurable por sujeto (§6 "Criterios configurables por sujeto")— y las
 * respuestas se mandan con `POST /evaluaciones/{id}/respuestas`.
 *
 * El **puntaje no se calcula aquí**: lo pondera el dominio con el `peso` de
 * cada criterio (§7.8) y llega ya resuelto en `EvaluacionRespuesta.puntaje`.
 * El peso se muestra solo como contexto de lectura.
 */

import { useState } from 'react';

import {
  useAgregarRespuestasApiV1EvaluacionesEvaluacionIdRespuestasPost,
  useListarCriteriosApiV1CriteriosEvaluacionGet,
} from '@/api/generado/evaluaciones/evaluaciones';
import type { EvaluacionRespuesta, SujetoEvaluacion } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { fmtNum } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import {
  hayRespuestas,
  peticionDeRespuestas,
  type CapturaRespuesta,
} from './formulario';
import {
  criteriosPendientes,
  etiquetaNivel,
  etiquetaSujeto,
  puedeResponder,
  tonoNivel,
  tonoPuntaje,
} from './reglas';

interface Props {
  readonly evaluacion: EvaluacionRespuesta;
  readonly onCerrar: () => void;
  readonly onRespondida: () => void;
}

export function PanelEvaluacion({ evaluacion, onCerrar, onRespondida }: Props) {
  const { sesion } = useSesion();
  const [capturas, setCapturas] = useState<ReadonlyMap<string, CapturaRespuesta>>(new Map());
  const [error, setError] = useState<string | null>(null);

  const criterios = useListarCriteriosApiV1CriteriosEvaluacionGet({
    aplica_a: evaluacion.sujeto_tipo as SujetoEvaluacion,
  });

  const responder =
    useAgregarRespuestasApiV1EvaluacionesEvaluacionIdRespuestasPost<ErrorApi>({
      mutation: {
        onSuccess: () => {
          setError(null);
          setCapturas(new Map());
          onRespondida();
        },
        onError: (err) => setError(err.message),
      },
    });

  function capturar(criterioId: string, campo: keyof CapturaRespuesta, valor: string) {
    setCapturas((previo) => {
      const siguiente = new Map(previo);
      const actual = siguiente.get(criterioId) ?? { valor: '', comentario: '' };
      siguiente.set(criterioId, { ...actual, [campo]: valor });
      return siguiente;
    });
  }

  if (!sesion) return null;

  const respondidas = evaluacion.respuestas ?? [];
  const porCriterio = new Map(respondidas.map((r) => [r.criterio_id, r]));
  const lista = criterios.data ?? [];
  const pendientes = criteriosPendientes(lista, respondidas);
  const esSuya = puedeResponder(sesion.usuarioId, evaluacion.evaluador_id);

  return (
    <Sheet
      titulo={`${etiquetaSujeto(evaluacion.sujeto_tipo)} · ${evaluacion.periodo}`}
      subtitulo={`${evaluacion.id.slice(0, 8)} · nivel ${evaluacion.nivel}`}
      onCerrar={onCerrar}
    >
      <div className="sheet__body col gap-16">
        {error && <ErrorBanner mensaje={error} />}

        <div className="row gap-12">
          <span className={`badge badge--${tonoNivel(evaluacion.nivel)}`}>
            {etiquetaNivel(evaluacion.nivel)}
          </span>
          <span className={`badge badge--${tonoPuntaje(evaluacion.puntaje)}`}>
            Puntaje: {fmtNum(evaluacion.puntaje)}
          </span>
          <span className="badge badge--outline">
            {respondidas.length}/{lista.length} criterios
          </span>
        </div>

        {evaluacion.comentarios && (
          <p className="text-sm text-soft">{evaluacion.comentarios}</p>
        )}

        {!esSuya && (
          <div className="badge badge--warn" role="status">
            Solo quien creó la evaluación puede responderla (§7.8). Esta es de
            otro evaluador: se muestra en lectura.
          </div>
        )}

        <div className="table-wrap">
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Criterio</th>
                  <th className="is-num">Peso</th>
                  <th className="is-num">Valor</th>
                  <th>Comentario</th>
                </tr>
              </thead>
              <tbody>
                {criterios.isLoading ? (
                  <tr>
                    <td colSpan={4}>
                      <div className="text-mute text-sm" style={{ padding: '16px 0' }}>
                        Cargando criterios…
                      </div>
                    </td>
                  </tr>
                ) : lista.length === 0 ? (
                  <tr>
                    <td colSpan={4}>
                      <div className="text-mute text-sm" style={{ padding: '16px 0' }}>
                        No hay criterios configurados para «
                        {etiquetaSujeto(evaluacion.sujeto_tipo)}» (§6).
                      </div>
                    </td>
                  </tr>
                ) : (
                  lista.map((criterio) => {
                    const yaRespondida = porCriterio.get(criterio.id);
                    const captura = capturas.get(criterio.id);
                    return (
                      <tr key={criterio.id}>
                        <td>
                          <div>{criterio.nombre}</div>
                          <div className="text-xs text-mute mono">{criterio.clave}</div>
                        </td>
                        <td className="is-num">{fmtNum(criterio.peso)}</td>
                        <td className="is-num">
                          {yaRespondida ? (
                            <span className="mono">{fmtNum(yaRespondida.valor)}</span>
                          ) : esSuya ? (
                            <input
                              className="input input--mono"
                              inputMode="decimal"
                              aria-label={`Valor de ${criterio.nombre}`}
                              value={captura?.valor ?? ''}
                              onChange={(e) => capturar(criterio.id, 'valor', e.target.value)}
                            />
                          ) : (
                            <span className="text-faint">—</span>
                          )}
                        </td>
                        <td>
                          {yaRespondida ? (
                            <span className="text-mute text-sm">
                              {yaRespondida.comentario ?? '—'}
                            </span>
                          ) : esSuya ? (
                            <input
                              className="input"
                              aria-label={`Comentario de ${criterio.nombre}`}
                              value={captura?.comentario ?? ''}
                              onChange={(e) =>
                                capturar(criterio.id, 'comentario', e.target.value)
                              }
                            />
                          ) : (
                            <span className="text-faint">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {esSuya && pendientes.length > 0 && (
          <div className="field__hint">
            Faltan {pendientes.length} criterio(s) por responder. Un criterio ya
            respondido no se puede volver a mandar: el endpoint contesta 409
            (§7.8).
          </div>
        )}
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cerrar
        </button>
        {esSuya && (
          <button
            type="button"
            className="btn btn--accent"
            disabled={responder.isPending || !hayRespuestas(capturas)}
            onClick={() =>
              responder.mutate({
                evaluacionId: evaluacion.id,
                data: peticionDeRespuestas(capturas),
              })
            }
          >
            {responder.isPending ? 'Guardando…' : 'Guardar respuestas'}
          </button>
        )}
      </div>
    </Sheet>
  );
}
