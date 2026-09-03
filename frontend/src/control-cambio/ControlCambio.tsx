/**
 * Bandeja de control de cambio — donde Control resuelve lo que el residente
 * pidió (§4, §11.3).
 *
 * Sin esta pantalla el residente podía pedir (§9d3eb7e) pero nadie tenía dónde
 * responderle: `POST /controles-cambio/{id}/resolver` existía sin puerta de
 * entrada.
 *
 * ## Autorizar aplica el efecto
 *
 * Al autorizar, el servidor sube el techo de una actividad, da de alta el
 * trabajo nuevo, o cancela la que se sustituye — en la misma transacción
 * (`ResolverControlDeCambio`). No hay un paso aparte que se le pueda olvidar
 * a nadie.
 *
 * ## La orden de cambio se escribe aquí, no en la solicitud
 *
 * Es lo que la vuelve válida: sin ella el botón de autorizar no está
 * disponible, y la base lo repite como CHECK.
 */

import { useState } from 'react';

import {
  useListarControlesDeCambioApiV1ControlesCambioGet,
  useLineasDelControlApiV1ControlesCambioControlIdLineasGet,
  useResolverControlDeCambioApiV1ControlesCambioControlIdResolverPost,
} from '@/api/generado/control-cambio/control-cambio';
import type {
  ControlCambioRespuesta,
  LineaDeControlRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { useClavesPorRecurso } from '@/lib/idempotencia';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { fmtFecha, fmtMXN, fmtNum } from '@/lib/formato';
import { etiquetaTipoCambio, puedeResolver, tonoEstatusCambio } from './reglas';

const TABS: readonly { readonly valor: string; readonly etiqueta: string }[] = [
  { valor: 'solicitado', etiqueta: 'Por resolver' },
  { valor: 'autorizado', etiqueta: 'Autorizados' },
  { valor: 'rechazado', etiqueta: 'Rechazados' },
  { valor: 'todas', etiqueta: 'Todos' },
];

type Dialogo =
  | { readonly tipo: 'autorizar'; readonly control: ControlCambioRespuesta }
  | { readonly tipo: 'rechazar'; readonly control: ControlCambioRespuesta }
  | null;

export default function ControlCambio() {
  const { sesion } = useSesion();
  // Una clave por (método, ruta): resolver el control 1 y luego el 2 son
  // operaciones distintas, y una clave fija haría que la segunda llegara con
  // la del primero.
  const idempotente = useClavesPorRecurso();

  const [tab, setTab] = useState('solicitado');
  const [abierto, setAbierto] = useState<string | null>(null);
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const [error, setError] = useState<string | null>(null);

  const consulta = useListarControlesDeCambioApiV1ControlesCambioGet<
    ControlCambioRespuesta[],
    ErrorApi
  >({ estatus: tab === 'todas' ? undefined : tab });

  const resolver = useResolverControlDeCambioApiV1ControlesCambioControlIdResolverPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        setDialogo(null);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
    ...idempotente,
  });

  if (!sesion) return null;
  const resuelve = puedeResolver(sesion.rol);
  const controles = consulta.data ?? [];

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Control de obra</div>
          <h1 className="page__title">Control de cambio</h1>
          <div className="page__subtitle">
            Más cantidad, trabajo fuera de catálogo, una sustitución, o el alta
            de algo del catálogo que no estaba. El residente pide; al
            autorizar se aplica en la obra y la orden de cambio queda con la
            solicitud.
          </div>
        </div>
      </div>

      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}
      {error && <ErrorBanner mensaje={error} />}

      <div className="tabs mb-8" role="tablist" aria-label="Control de cambio">
        {TABS.map((t) => (
          <button
            key={t.valor}
            type="button"
            role="tab"
            aria-selected={tab === t.valor}
            className={`tabs__tab${tab === t.valor ? ' is-active' : ''}`}
            onClick={() => setTab(t.valor)}
          >
            {t.etiqueta}
          </button>
        ))}
      </div>

      {consulta.isLoading ? (
        <div className="text-mute text-sm" style={{ padding: 24 }}>
          Cargando…
        </div>
      ) : controles.length === 0 ? (
        <div className="empty">
          <div className="empty-title">Nada en esta pestaña</div>
          <div className="empty-sub">
            {tab === 'solicitado'
              ? 'No hay solicitudes esperando resolución.'
              : 'Cambia de pestaña para ver otras.'}
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <div className="table-scroll">
            <table className="table" style={{ minWidth: 'max-content' }}>
              <thead>
                <tr>
                  <th style={{ minWidth: 30 }} />
                  <th style={{ minWidth: 140 }}>Tipo</th>
                  <th style={{ minWidth: 300 }}>Motivo</th>
                  <th className="is-num" style={{ minWidth: 80 }}>
                    Renglones
                  </th>
                  <th className="is-num" style={{ minWidth: 120 }}>
                    Importe
                  </th>
                  <th style={{ minWidth: 110 }}>Pedida</th>
                  <th style={{ minWidth: 110 }}>Estatus</th>
                  <th style={{ minWidth: 140 }}>Orden de cambio</th>
                  {resuelve && <th className="cell-actions" style={{ minWidth: 200 }} />}
                </tr>
              </thead>
              <tbody>
                {controles.map((c) => (
                  <FilaControl
                    key={c.id}
                    control={c}
                    abierto={abierto === c.id}
                    resuelve={resuelve}
                    onAlternar={() => setAbierto(abierto === c.id ? null : c.id)}
                    onAutorizar={() => setDialogo({ tipo: 'autorizar', control: c })}
                    onRechazar={() => setDialogo({ tipo: 'rechazar', control: c })}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {dialogo?.tipo === 'autorizar' && (
        <DialogoAutorizar
          control={dialogo.control}
          guardando={resolver.isPending}
          onCerrar={() => setDialogo(null)}
          onConfirmar={(datos) =>
            resolver.mutate({ controlId: dialogo.control.id, data: { autorizado: true, ...datos } })
          }
        />
      )}

      {dialogo?.tipo === 'rechazar' && (
        <DialogoRechazar
          control={dialogo.control}
          guardando={resolver.isPending}
          onCerrar={() => setDialogo(null)}
          onConfirmar={(nota) =>
            resolver.mutate({
              controlId: dialogo.control.id,
              data: { autorizado: false, nota },
            })
          }
        />
      )}
    </div>
  );
}

function FilaControl({
  control,
  abierto,
  resuelve,
  onAlternar,
  onAutorizar,
  onRechazar,
}: {
  readonly control: ControlCambioRespuesta;
  readonly abierto: boolean;
  readonly resuelve: boolean;
  readonly onAlternar: () => void;
  readonly onAutorizar: () => void;
  readonly onRechazar: () => void;
}) {
  const lineasQ = useLineasDelControlApiV1ControlesCambioControlIdLineasGet<
    LineaDeControlRespuesta[],
    ErrorApi
  >(control.id, { query: { enabled: abierto } });

  return (
    <>
      <tr>
        <td>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            aria-expanded={abierto}
            aria-label={`Renglones de ${control.motivo}`}
            onClick={onAlternar}
          >
            {abierto ? '▾' : '▸'}
          </button>
        </td>
        <td className="text-sm">{etiquetaTipoCambio(control.tipo)}</td>
        <td>{control.motivo}</td>
        <td className="is-num tnum">{control.renglones ?? 0}</td>
        <td className="is-num tnum">{fmtMXN(control.importe ?? 0)}</td>
        <td className="text-xs">{fmtFecha(control.solicitado_en)}</td>
        <td>
          <span className={`badge badge--${tonoEstatusCambio(control.estatus)}`}>
            {control.estatus}
          </span>
        </td>
        <td className="mono text-xs">
          {control.orden_cambio ?? <span className="text-mute">—</span>}
        </td>
        {resuelve && (
          <td className="cell-actions">
            {control.estatus === 'solicitado' ? (
              <div className="row gap-4">
                <button type="button" className="btn btn--accent btn--sm" onClick={onAutorizar}>
                  Autorizar
                </button>
                <button type="button" className="btn btn--danger btn--sm" onClick={onRechazar}>
                  Rechazar
                </button>
              </div>
            ) : (
              <span className="text-faint text-sm">—</span>
            )}
          </td>
        )}
      </tr>
      {abierto && (
        <tr style={{ background: 'var(--c-panel-2)' }}>
          <td colSpan={resuelve ? 9 : 8}>
            <div className="col gap-2" style={{ padding: '8px 0 8px 28px' }}>
              {lineasQ.isLoading ? (
                <span className="text-mute text-xs">Cargando renglones…</span>
              ) : (
                (lineasQ.data ?? []).map((linea) => (
                  <div key={linea.id} className="row gap-8 text-xs" style={{ alignItems: 'center' }}>
                    <span className="mono">{linea.concepto_clave ?? 'EXT'}</span>
                    <span>{linea.descripcion ?? linea.actividad_descripcion ?? '—'}</span>
                    <span className="text-mute">cant. {fmtNum(linea.cantidad)}</span>
                    {linea.cant_base !== null && linea.cant_base !== undefined && (
                      <span className="text-mute">
                        base {fmtNum(linea.cant_base)} → prog. {fmtNum(linea.cant_programada)}
                      </span>
                    )}
                    <span className="text-mute">{fmtMXN(Number(linea.cantidad) * Number(linea.precio_unitario))}</span>
                  </div>
                ))
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function DialogoAutorizar({
  control,
  guardando,
  onCerrar,
  onConfirmar,
}: {
  readonly control: ControlCambioRespuesta;
  readonly guardando: boolean;
  readonly onCerrar: () => void;
  readonly onConfirmar: (datos: {
    orden_cambio: string;
    nota?: string;
    descuenta_ejecutado?: boolean;
  }) => void;
}) {
  const [orden, setOrden] = useState('');
  const [nota, setNota] = useState('');
  const [descuenta, setDescuenta] = useState(false);

  const esSustitucion = control.tipo === 'sustitucion';

  return (
    <Modal titulo={`Autorizar · ${etiquetaTipoCambio(control.tipo)}`} onCerrar={onCerrar}>
      <div className="sheet__body">
        <p className="text-mute text-sm">{control.motivo}</p>
        <p className="text-sm">
          Le mueve <strong>{fmtMXN(control.importe ?? 0)}</strong> al costo final
          de la obra.
        </p>

        <div className="field">
          <label className="field__label" htmlFor="orden">
            Orden de cambio
          </label>
          <input
            id="orden"
            className="input"
            value={orden}
            onChange={(e) => setOrden(e.target.value)}
            placeholder="OC-2026-014"
          />
          <span className="field__hint">
            Obligatoria: es lo que autoriza el trabajo. Sin ella no se puede
            guardar.
          </span>
        </div>

        <div className="field mt-8">
          <label className="field__label" htmlFor="nota">
            Nota (opcional)
          </label>
          <textarea
            id="nota"
            className="input"
            rows={2}
            value={nota}
            onChange={(e) => setNota(e.target.value)}
          />
        </div>

        {esSustitucion && (
          <label className="row gap-8 mt-8" style={{ alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={descuenta}
              onChange={(e) => setDescuenta(e.target.checked)}
            />
            <span className="text-sm">
              Descontar lo ya ejecutado de la actividad que se sustituye
            </span>
          </label>
        )}
        {esSustitucion && (
          <p className="field__hint">
            Por defecto lo ejecutado se estima: el trabajo se hizo y alguien lo
            pagó. Marca esto solo si ese caso no aplica.
          </p>
        )}
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--accent"
          disabled={orden.trim() === '' || guardando}
          onClick={() =>
            onConfirmar({
              orden_cambio: orden.trim(),
              nota: nota.trim() === '' ? undefined : nota.trim(),
              descuenta_ejecutado: descuenta,
            })
          }
        >
          {guardando ? 'Autorizando…' : 'Autorizar'}
        </button>
      </div>
    </Modal>
  );
}

function DialogoRechazar({
  control,
  guardando,
  onCerrar,
  onConfirmar,
}: {
  readonly control: ControlCambioRespuesta;
  readonly guardando: boolean;
  readonly onCerrar: () => void;
  readonly onConfirmar: (nota: string) => void;
}) {
  const [nota, setNota] = useState('');

  return (
    <Modal titulo={`Rechazar · ${etiquetaTipoCambio(control.tipo)}`} onCerrar={onCerrar}>
      <div className="sheet__body">
        <p className="text-mute text-sm">{control.motivo}</p>
        <div className="field">
          <label className="field__label" htmlFor="motivo-rechazo">
            Por qué se rechaza
          </label>
          <textarea
            id="motivo-rechazo"
            className="input"
            rows={3}
            value={nota}
            onChange={(e) => setNota(e.target.value)}
          />
          <span className="field__hint">
            El residente ve esto: sin motivo, va a volver a pedir lo mismo.
          </span>
        </div>
      </div>
      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--danger"
          disabled={nota.trim() === '' || guardando}
          onClick={() => onConfirmar(nota.trim())}
        >
          {guardando ? 'Rechazando…' : 'Rechazar'}
        </button>
      </div>
    </Modal>
  );
}
