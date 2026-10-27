/**
 * Prototipo modificado: cambios y adicionales (migración 0080; cerebro D-573 a D-575).
 *
 * Antes de asignar, lo que cambia se hace directo en el diseño. **Cambio:** puede restar
 * —se elimina del presupuesto— o sumar. **Adicional:** highlights y conceptos fuera de catálogo;
 * solo suma. Lo que cambia puede aplicar sobre un concepto del prototipo o **nacer nuevo**.
 * Si la parte ya estaba validada, vuelve a cuantificarse. Asignada, ya no se toca: cambiarla es
 * control de cambio.
 */

import { useRef, useState } from 'react';

import { claveDeIdempotencia, type ErrorApi } from '@/api/cliente';
import type { ActividadRespuesta } from '@/api/generado/modelo';
import {
  getBitacoraDePartesApiV1ObrasObraIdPartesBitacoraGetQueryKey,
  getModificacionesDeLaObraApiV1ObrasObraIdModificacionesGetQueryKey,
  getPartesDeLaObraApiV1ObrasObraIdPartesGetQueryKey,
  useAgregarActividadNuevaApiV1ObrasObraIdModificacionesNuevaPost,
  useModificacionesDeLaObraApiV1ObrasObraIdModificacionesGet,
  useModificarActividadApiV1ActividadesActividadIdModificacionPost,
} from '@/api/generado/partes/partes';
import { useActividadesDeObraApiV1ObrasObraIdActividadesGet } from '@/api/generado/torre/torre';
import { queryClient } from '@/app/queryClient';
import { ErrorBanner } from '@/lib/ErrorBanner';
import Cotizaciones from './Cotizaciones';
import { fmtFecha, fmtNum } from '@/lib/formato';
import type { Rol } from '@/shell/navegacion';
import {
  ETIQUETA_MODIFICACION,
  motivoDeModificacion,
  puedeModificar,
  type TipoDeModificacion,
} from './reglas';

interface Props {
  readonly obraId: string;
  readonly rol: Rol;
  /** Las partes que son etapas, para elegir dónde nace lo nuevo. */
  readonly etapas: readonly { readonly id: string; readonly nombre: string }[];
}

export default function Modificaciones({ obraId, rol, etapas }: Props) {
  const modifica = puedeModificar(rol);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const clave = useRef(claveDeIdempotencia());

  const [actividadId, setActividadId] = useState('');
  const [tipo, setTipo] = useState<TipoDeModificacion>('cambio');
  const [delta, setDelta] = useState('');
  const [nota, setNota] = useState('');

  const [nuevoTipo, setNuevoTipo] = useState<TipoDeModificacion>('adicional');
  const [descripcion, setDescripcion] = useState('');
  const [cantidad, setCantidad] = useState('');
  const [precio, setPrecio] = useState('');
  const [etapaId, setEtapaId] = useState('');

  const actividades = useActividadesDeObraApiV1ObrasObraIdActividadesGet<ActividadRespuesta[], ErrorApi>(
    obraId,
    undefined,
    { query: { enabled: modifica } },
  );
  const bitacora = useModificacionesDeLaObraApiV1ObrasObraIdModificacionesGet(obraId);

  const refrescar = () => {
    for (const queryKey of [
      getModificacionesDeLaObraApiV1ObrasObraIdModificacionesGetQueryKey(obraId),
      getPartesDeLaObraApiV1ObrasObraIdPartesGetQueryKey(obraId),
      getBitacoraDePartesApiV1ObrasObraIdPartesBitacoraGetQueryKey(obraId),
    ]) {
      void queryClient.invalidateQueries({ queryKey });
    }
    void actividades.refetch();
  };

  const modificar = useModificarActividadApiV1ActividadesActividadIdModificacionPost<ErrorApi>({
    mutation: {
      onSuccess: (r) => {
        setError(null);
        setDelta('');
        setNota('');
        setAviso(
          `${ETIQUETA_MODIFICACION[r.tipo as TipoDeModificacion] ?? r.tipo}: ${fmtNum(r.cantidad_antes)} → ${fmtNum(r.cantidad_despues)}.` +
            (r.parte_reabierta ? ' La parte volvió a cuantificarse.' : ''),
        );
        refrescar();
      },
      onError: (e) => setError(e.message),
    },
    request: { headers: () => ({ 'Idempotency-Key': clave.current }) },
  });
  const nacer = useAgregarActividadNuevaApiV1ObrasObraIdModificacionesNuevaPost<ErrorApi>({
    mutation: {
      onSuccess: (r) => {
        setError(null);
        setDescripcion('');
        setCantidad('');
        setPrecio('');
        setAviso(
          `Nació un ${ETIQUETA_MODIFICACION[r.tipo as TipoDeModificacion]?.toLowerCase() ?? r.tipo}.` +
            (r.parte_reabierta ? ' La parte volvió a cuantificarse.' : ''),
        );
        refrescar();
      },
      onError: (e) => setError(e.message),
    },
    request: { headers: () => ({ 'Idempotency-Key': clave.current }) },
  });

  const elegida = (actividades.data ?? []).find((a) => a.id === actividadId);
  const deltaNum = Number(delta);
  const motivo = elegida ? motivoDeModificacion(tipo, Number(elegida.cant_base), deltaNum) : null;

  return (
    <section aria-label="Cambios y adicionales" className="mt-16">
      <h2 className="text-sm" style={{ margin: '16px 0 8px' }}>
        Cambios y adicionales
      </h2>
      <div className="text-xs text-mute mb-8">
        Un cambio puede restar (se elimina del presupuesto); un adicional —un highlight o un concepto fuera de
        catálogo— solo suma. Antes de asignar se hace directo; asignada, es control de cambio.
      </div>
      {error && <ErrorBanner mensaje={error} />}
      {aviso && (
        <div className="text-sm mb-8" role="status">
          {aviso}
        </div>
      )}

      {modifica && (
        <div className="row gap-12" style={{ flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <form
            aria-label="Modificar un concepto"
            className="card"
            style={{ minWidth: 300, flex: 1 }}
            onSubmit={(e) => {
              e.preventDefault();
              if (!elegida || motivo) return;
              clave.current = claveDeIdempotencia();
              modificar.mutate({
                actividadId: elegida.id,
                data: { tipo, delta, nota: nota.trim() || null },
              });
            }}
          >
            <div className="card__body col gap-8">
              <strong className="text-sm">Modificar un concepto del prototipo</strong>
              <div className="field">
                <label className="field__label" htmlFor="mod-concepto">
                  Concepto
                </label>
                <select
                  id="mod-concepto"
                  className="select"
                  value={actividadId}
                  onChange={(e) => setActividadId(e.target.value)}
                >
                  <option value="">Elige un concepto…</option>
                  {(actividades.data ?? []).map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.concepto_clave ? `${a.concepto_clave} · ` : ''}
                      {a.descripcion ?? ''} ({fmtNum(a.cant_base)})
                    </option>
                  ))}
                </select>
              </div>
              <div className="row gap-8" style={{ flexWrap: 'wrap' }}>
                <div className="field">
                  <label className="field__label" htmlFor="mod-tipo">
                    Tipo
                  </label>
                  <select
                    id="mod-tipo"
                    className="select"
                    value={tipo}
                    onChange={(e) => setTipo(e.target.value as TipoDeModificacion)}
                  >
                    <option value="cambio">Cambio</option>
                    <option value="adicional">Adicional</option>
                  </select>
                </div>
                <div className="field">
                  <label className="field__label" htmlFor="mod-delta">
                    Cuánto cambia (negativo quita)
                  </label>
                  <input
                    id="mod-delta"
                    className="input"
                    type="number"
                    step="any"
                    value={delta}
                    onChange={(e) => setDelta(e.target.value)}
                  />
                </div>
              </div>
              <div className="field">
                <label className="field__label" htmlFor="mod-nota">
                  Nota
                </label>
                <input id="mod-nota" className="input" value={nota} onChange={(e) => setNota(e.target.value)} />
              </div>
              {delta !== '' && motivo && (
                <div className="text-xs" role="note">
                  {motivo}
                </div>
              )}
              <div>
                <button
                  type="submit"
                  className="btn btn--sm btn--primary"
                  disabled={!elegida || delta === '' || motivo !== null || modificar.isPending}
                >
                  Aplicar {ETIQUETA_MODIFICACION[tipo].toLowerCase()}
                </button>
              </div>
            </div>
          </form>

          <form
            aria-label="Agregar algo nuevo"
            className="card"
            style={{ minWidth: 300, flex: 1 }}
            onSubmit={(e) => {
              e.preventDefault();
              clave.current = claveDeIdempotencia();
              nacer.mutate({
                obraId,
                data: {
                  tipo: nuevoTipo,
                  descripcion,
                  cantidad,
                  precio_unitario: precio === '' ? '0' : precio,
                  etapa_id: etapaId || null,
                },
              });
            }}
          >
            <div className="card__body col gap-8">
              <strong className="text-sm">Lo que nace nuevo</strong>
              <div className="field">
                <label className="field__label" htmlFor="nuevo-tipo">
                  Tipo de lo nuevo
                </label>
                <select
                  id="nuevo-tipo"
                  className="select"
                  value={nuevoTipo}
                  onChange={(e) => setNuevoTipo(e.target.value as TipoDeModificacion)}
                >
                  <option value="adicional">Adicional (highlight o fuera de catálogo)</option>
                  <option value="cambio">Cambio (se agrega al diseño)</option>
                </select>
              </div>
              <div className="field">
                <label className="field__label" htmlFor="nuevo-descripcion">
                  Descripción
                </label>
                <input
                  id="nuevo-descripcion"
                  className="input"
                  value={descripcion}
                  onChange={(e) => setDescripcion(e.target.value)}
                />
              </div>
              <div className="row gap-8" style={{ flexWrap: 'wrap' }}>
                <div className="field">
                  <label className="field__label" htmlFor="nuevo-cantidad">
                    Cantidad
                  </label>
                  <input
                    id="nuevo-cantidad"
                    className="input"
                    type="number"
                    min="0"
                    step="any"
                    value={cantidad}
                    onChange={(e) => setCantidad(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label className="field__label" htmlFor="nuevo-precio">
                    Precio unitario
                  </label>
                  <input
                    id="nuevo-precio"
                    className="input"
                    type="number"
                    min="0"
                    step="any"
                    value={precio}
                    onChange={(e) => setPrecio(e.target.value)}
                  />
                </div>
              </div>
              <div className="field">
                <label className="field__label" htmlFor="nuevo-etapa">
                  Nace en la etapa
                </label>
                <select
                  id="nuevo-etapa"
                  className="select"
                  value={etapaId}
                  onChange={(e) => setEtapaId(e.target.value)}
                >
                  <option value="">Suelto, sin etapa</option>
                  {etapas.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.nombre}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <button
                  type="submit"
                  className="btn btn--sm btn--primary"
                  disabled={descripcion.trim() === '' || Number(cantidad) <= 0 || nacer.isPending}
                >
                  Agregar
                </button>
              </div>
            </div>
          </form>
        </div>
      )}

      {(bitacora.data ?? []).length === 0 ? (
        <div className="text-mute text-sm" style={{ marginTop: 8 }}>
          El prototipo no se ha modificado.
        </div>
      ) : (
        <ul aria-label="Modificaciones" className="text-xs" style={{ margin: '8px 0 0', padding: 0, listStyle: 'none' }}>
          {(bitacora.data ?? []).map((m) => (
            <li key={m.id}>
              <span className={`badge badge--${m.tipo === 'cambio' ? 'info' : 'accent'}`}>
                {ETIQUETA_MODIFICACION[m.tipo as TipoDeModificacion] ?? m.tipo}
              </span>{' '}
              <strong>{m.descripcion || m.concepto_clave}</strong>
              {m.nace_nueva ? ' (nació nuevo)' : ''}: {fmtNum(m.cantidad_antes)} → {fmtNum(m.cantidad_despues)} (
              {Number(m.delta) > 0 ? '+' : ''}
              {fmtNum(m.delta)})
              <span className="text-mute">
                {' '}
                · {m.usuario_nombre ?? m.rol} · {fmtFecha(m.creada_en)}
              </span>
              {m.nota ? <span> — {m.nota}</span> : null}
            </li>
          ))}
        </ul>
      )}
      <Cotizaciones obraId={obraId} puedeCotizar={rol === 'control_obra'} />
    </section>
  );
}
