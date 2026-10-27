/**
 * Comprobación y validación — lo que se ejecutó de más (migración 0066).
 *
 * La decisión del usuario: si se puede ejecutar más de lo programado, **el
 * excedente se va a comprobación y validación**. Capturar avance nunca se
 * bloquea (WORKFLOWS.md §8.1, «registrar nunca se bloquea»); aquí llega lo que
 * pasó de lo programado y Control de obra decide su destino:
 *
 *   · **Validar**: fue trabajo real y se respalda con una orden de cambio. Se
 *     vuelve control de cambio y sube el techo de la actividad.
 *   · **Pérdida**: se ejecutó y no se cobra.
 *
 * Mientras un excedente espera, la actividad no se puede cerrar y por tanto no
 * se estima ni se paga: la deuda es medible, con su antigüedad, que es lo que
 * ordena esta lista (las más viejas, primero).
 *
 * Lectura abierta a quien ve la obra (RLS); decidir es de Control de obra y del
 * Super intendente — quienes autorizan un control de cambio (§4). El residente
 * lo originó al ejecutarlo y no se lo autoriza a sí mismo.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useBandejaApiV1ComprobacionesGet,
  usePerdidaApiV1ActividadesActividadIdExcedentePerdidaPost,
  useValidarApiV1ActividadesActividadIdExcedenteValidarPost,
} from '@/api/generado/comprobaciones/comprobaciones';
import type { ExcedentePendiente } from '@/api/generado/modelo';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtFecha, fmtNum } from '@/lib/formato';
import { useClavesPorRecurso } from '@/lib/idempotencia';
import { Modal } from '@/lib/Modal';
import { puedeComprobar } from './reglas';

type Dialogo =
  | { readonly tipo: 'validar'; readonly fila: ExcedentePendiente }
  | { readonly tipo: 'perdida'; readonly fila: ExcedentePendiente }
  | null;

export default function Comprobaciones() {
  const { sesion } = useSesion();
  const idempotente = useClavesPorRecurso();
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const consulta = useBandejaApiV1ComprobacionesGet<ExcedentePendiente[], ErrorApi>();

  const alExito = (mensaje: string) => () => {
    setError(null);
    setDialogo(null);
    setAviso(mensaje);
    void consulta.refetch();
  };
  const validar = useValidarApiV1ActividadesActividadIdExcedenteValidarPost<ErrorApi>({
    mutation: { onSuccess: alExito('Excedente validado: quedó como control de cambio.'), onError: (e) => setError(e.message) },
    ...idempotente,
  });
  const perdida = usePerdidaApiV1ActividadesActividadIdExcedentePerdidaPost<ErrorApi>({
    mutation: { onSuccess: alExito('Excedente declarado pérdida.'), onError: (e) => setError(e.message) },
    ...idempotente,
  });

  if (!sesion) return null;
  const decide = puedeComprobar(sesion.rol);
  const filas = consulta.data ?? [];

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Control de obra</div>
          <h1 className="page__title">Comprobación y validación</h1>
          <div className="page__subtitle">
            Lo que se ejecutó <strong>por encima de lo programado</strong>. Se
            registra siempre; aquí se comprueba. Mientras espera, la actividad
            no se puede cerrar ni estimar.
          </div>
        </div>
      </div>

      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}
      {error && <ErrorBanner mensaje={error} />}
      {aviso && (
        <div className="text-sm mb-8" role="status">
          {aviso}
        </div>
      )}

      {consulta.isLoading ? (
        <div className="text-mute text-sm" style={{ padding: 24 }}>
          Cargando…
        </div>
      ) : filas.length === 0 ? (
        <div className="empty">
          <div className="empty-title">Nada por comprobar</div>
          <div className="empty-sub">
            Ninguna actividad tiene ejecutado de más pendiente de decisión.
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <div className="table-scroll">
            <table className="table" style={{ minWidth: 'max-content' }}>
              <thead>
                <tr>
                  <th style={{ minWidth: 110 }}>Obra</th>
                  <th style={{ minWidth: 260 }}>Actividad</th>
                  <th className="is-num">Programado</th>
                  <th className="is-num">Ejecutado</th>
                  <th className="is-num">Excedente</th>
                  <th style={{ minWidth: 130 }}>Antigüedad</th>
                  {decide && <th className="cell-actions" style={{ minWidth: 200 }} />}
                </tr>
              </thead>
              <tbody>
                {filas.map((f) => (
                  <tr key={f.actividad_id}>
                    <td className="mono">{f.obra_clave}</td>
                    <td>
                      <span className="mono">{f.concepto_clave ?? '—'}</span>{' '}
                      {f.descripcion}
                    </td>
                    <td className="is-num tnum">
                      {fmtNum(f.cant_programada)} {f.unidad}
                    </td>
                    <td className="is-num tnum">{fmtNum(f.cant_ejecutada)}</td>
                    <td className="is-num tnum">
                      <span className="badge badge--warn">+{fmtNum(f.cant_excedente)}</span>
                    </td>
                    <td className="text-xs">
                      {f.excedente_desde ? `${fmtFecha(f.excedente_desde)} · ${f.dias ?? 0} d` : '—'}
                    </td>
                    {decide && (
                      <td className="cell-actions">
                        <button
                          type="button"
                          className="btn btn--sm btn--primary"
                          onClick={() => setDialogo({ tipo: 'validar', fila: f })}
                        >
                          Validar
                        </button>{' '}
                        <button
                          type="button"
                          className="btn btn--sm"
                          onClick={() => setDialogo({ tipo: 'perdida', fila: f })}
                        >
                          Pérdida
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {dialogo?.tipo === 'validar' && (
        <DialogoDecision
          fila={dialogo.fila}
          titulo="Validar el excedente"
          explicacion="Fue trabajo real. Se vuelve control de cambio y sube el techo de la actividad a lo ejecutado."
          pideOrden
          boton="Validar"
          guardando={validar.isPending}
          onCerrar={() => setDialogo(null)}
          onConfirmar={(datos) =>
            validar.mutate({ actividadId: dialogo.fila.actividad_id, data: datos })
          }
        />
      )}
      {dialogo?.tipo === 'perdida' && (
        <DialogoDecision
          fila={dialogo.fila}
          titulo="Declarar pérdida"
          explicacion="Se ejecutó y no se cobra: el excedente deja de ser pendiente y el techo no sube."
          boton="Declarar pérdida"
          guardando={perdida.isPending}
          onCerrar={() => setDialogo(null)}
          onConfirmar={(datos) =>
            perdida.mutate({
              actividadId: dialogo.fila.actividad_id,
              data: { nota: datos.nota },
            })
          }
        />
      )}
    </div>
  );
}

function DialogoDecision({
  fila,
  titulo,
  explicacion,
  pideOrden = false,
  boton,
  guardando,
  onCerrar,
  onConfirmar,
}: {
  readonly fila: ExcedentePendiente;
  readonly titulo: string;
  readonly explicacion: string;
  readonly pideOrden?: boolean;
  readonly boton: string;
  readonly guardando: boolean;
  readonly onCerrar: () => void;
  readonly onConfirmar: (datos: { nota: string; orden_cambio?: string }) => void;
}) {
  const [orden, setOrden] = useState('');
  const [nota, setNota] = useState('');
  const completo = nota.trim() !== '' && (!pideOrden || orden.trim() !== '');

  return (
    <Modal titulo={titulo} onCerrar={onCerrar}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (completo) {
            onConfirmar({ nota: nota.trim(), ...(pideOrden ? { orden_cambio: orden.trim() } : {}) });
          }
        }}
      >
        <div className="sheet__body col gap-12">
          <p className="text-sm">
            <span className="mono">{fila.concepto_clave}</span> {fila.descripcion} ·{' '}
            <strong>+{fmtNum(fila.cant_excedente)}</strong> sobre lo programado (
            {fmtNum(fila.cant_programada)}).
          </p>
          <p className="text-mute text-sm">{explicacion}</p>

          {pideOrden && (
            <div className="field">
              <label className="field__label" htmlFor="excedente-orden">
                Orden de cambio
              </label>
              <input
                id="excedente-orden"
                className="input"
                value={orden}
                onChange={(e) => setOrden(e.target.value)}
                placeholder="OC-2026-014"
              />
              <span className="field__hint">
                Obligatoria: es lo que respalda el trabajo ejecutado de más.
              </span>
            </div>
          )}

          <div className="field">
            <label className="field__label" htmlFor="excedente-nota">
              Qué se comprobó
            </label>
            <textarea
              id="excedente-nota"
              className="input"
              rows={3}
              value={nota}
              onChange={(e) => setNota(e.target.value)}
            />
            <span className="field__hint">Queda como constancia de la decisión.</span>
          </div>
        </div>
        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!completo || guardando}>
            {guardando ? 'Guardando…' : boton}
          </button>
        </div>
      </form>
    </Modal>
  );
}
