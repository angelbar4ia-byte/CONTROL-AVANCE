/**
 * Extra-catálogo — el trabajo que aparece cuando la obra se mueve (§11.2, §5.1).
 *
 * El Residente la trae en su sidebar desde la Fase 1 («Mi trabajo → Extra
 * catálogo») y hasta ahora no llevaba a ninguna parte: `POST /actividades` no
 * existía. Sin ella, el trabajo que no estaba en el prototipo o se capturaba
 * contra una actividad que no correspondía —falseando su avance— o no se
 * capturaba.
 *
 * ## La orden de cambio no es un campo más
 *
 * Es lo que autoriza el trabajo, y sin ella el backend responde 422 y la base
 * rechaza el `INSERT` (`ck_actividad_extra_con_oc`, migración 0026). La
 * pantalla lo dice antes de dejar enviar, en vez de descubrirlo con un error.
 *
 * ## Y el precio tampoco
 *
 * Un extra sin precio del modo elegido no se puede estimar (§11.3 E): sería
 * trabajo real que nadie va a cobrar. Por eso el formulario pide **el precio
 * del modo de pago que se eligió**, no los dos.
 */

import { useMemo, useState, type FormEvent } from 'react';

import {
  useActividadesDeObraApiV1ObrasObraIdActividadesGet,
  useDarDeAltaExtraApiV1ActividadesPost,
} from '@/api/generado/torre/torre';
import { ModoPago, type ActividadRespuesta } from '@/api/generado/modelo';
import { claveDeIdempotencia, type ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { SelectorObra } from '@/lib/SelectorObra';
import { fmtNum } from '@/lib/formato';
import {
  etiquetaEstatusActividad,
  tonoEstatusActividad,
} from '@/torre/reglas';
import { campoDePrecio, etiquetaModoPago, extraCompleto, type FormularioExtra } from './reglas';

export default function ExtraCatalogo() {
  const { sesion } = useSesion();
  const [obraId, setObraId] = useState('');
  const [formulario, setFormulario] = useState<FormularioExtra>({
    descripcion: '',
    ordenCambio: '',
    cantBase: '',
    modoPago: ModoPago.destajo,
    precio: '',
    duracionDias: '1',
  });
  const [error, setError] = useState<string | null>(null);
  const [campoConError, setCampoConError] = useState<string | undefined>();

  // Clave fija por formulario: un doble clic crearía **dos** actividades con la
  // misma orden de cambio, y las dos se estimarían — el extra duplicado se paga
  // dos veces (regla 1 del ROADMAP).
  const clave = useMemo(claveDeIdempotencia, []);

  const actividades = useActividadesDeObraApiV1ObrasObraIdActividadesGet<
    ActividadRespuesta[],
    ErrorApi
  >(obraId, undefined, { query: { enabled: obraId !== '' } });

  const crear = useDarDeAltaExtraApiV1ActividadesPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        setCampoConError(undefined);
        setFormulario((previo) => ({
          ...previo,
          descripcion: '',
          ordenCambio: '',
          cantBase: '',
          precio: '',
        }));
        void actividades.refetch();
      },
      onError: (err) => {
        setError(err.message);
        setCampoConError(err.campo);
      },
    },
    request: { headers: { 'Idempotency-Key': clave } },
  });

  if (!sesion) return null;

  // El §11.2 marca la `(R)`: solo el residente da de alta trabajo extra. Los
  // demás llegan aquí desde su sidebar solo si escriben la ruta, así que la
  // pantalla lo explica en vez de mostrar un formulario que dará 403.
  const esResidente = sesion.rol === 'residente';

  const extras = (actividades.data ?? []).filter((a) => a.extra);

  function cambiar<K extends keyof FormularioExtra>(campo: K, valor: FormularioExtra[K]) {
    setFormulario((previo) => ({ ...previo, [campo]: valor }));
  }

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (obraId === '' || !extraCompleto(formulario)) return;
    const precio = formulario.precio.trim();
    crear.mutate({
      data: {
        obra_id: obraId,
        descripcion: formulario.descripcion.trim(),
        orden_cambio: formulario.ordenCambio.trim(),
        cant_base: formulario.cantBase.trim(),
        modo_pago: formulario.modoPago,
        duracion_dias: formulario.duracionDias.trim() || '1',
        // Solo el precio del modo elegido: un destajo no manda precio unitario
        // y viceversa. El dominio exige el que corresponde y solo ese.
        ...(campoDePrecio(formulario.modoPago) === 'precio_destajo'
          ? { precio_destajo: precio }
          : { precio_unitario: precio }),
      },
    });
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Mi trabajo</div>
          <h1 className="page__title">Extra-catálogo</h1>
          <div className="page__subtitle">
            Trabajo que apareció en obra y no estaba en el prototipo. Necesita la
            orden de cambio que lo autoriza (§11.2).
          </div>
        </div>
      </div>

      {error && <ErrorBanner mensaje={error} campo={campoConError} />}

      <div className="filterbar">
        <SelectorObra
          id="extra-obra"
          etiqueta="Obra"
          valor={obraId}
          onCambio={setObraId}
        />
      </div>

      {obraId === '' ? (
        <div className="empty">
          <div className="empty-title">Elige una obra</div>
          <div className="empty-sub">El listado ya viene acotado a tu alcance (§4).</div>
        </div>
      ) : (
        <>
          {esResidente ? (
            <form onSubmit={alEnviar} className="card mb-8">
              <div className="card__header">
                <h2 className="card__title">Dar de alta un extra</h2>
              </div>
              <div className="card__body col gap-12">
                <div className="field">
                  <label className="field__label" htmlFor="extra-descripcion">
                    Qué trabajo es
                  </label>
                  <input
                    id="extra-descripcion"
                    className="input"
                    value={formulario.descripcion}
                    onChange={(e) => cambiar('descripcion', e.target.value)}
                    placeholder="Demoler muro que el proyecto no traía"
                    required
                  />
                </div>

                <div className="row gap-12">
                  <div className="field" style={{ flex: 1 }}>
                    <label className="field__label" htmlFor="extra-oc">
                      Orden de cambio
                    </label>
                    <input
                      id="extra-oc"
                      className="input mono"
                      value={formulario.ordenCambio}
                      onChange={(e) => cambiar('ordenCambio', e.target.value)}
                      placeholder="OC-2026-014"
                      required
                    />
                    <div className="field__hint">
                      No hay trabajo extra sin autorización que lo respalde.
                    </div>
                  </div>
                  <div className="field" style={{ flex: 1 }}>
                    <label className="field__label" htmlFor="extra-cantidad">
                      Cantidad
                    </label>
                    <input
                      id="extra-cantidad"
                      className="input mono"
                      type="number"
                      min="0"
                      step="0.01"
                      value={formulario.cantBase}
                      onChange={(e) => cambiar('cantBase', e.target.value)}
                      required
                    />
                  </div>
                </div>

                <div className="row gap-12">
                  <div className="field" style={{ flex: 1 }}>
                    <label className="field__label" htmlFor="extra-modo">
                      Modo de pago
                    </label>
                    <select
                      id="extra-modo"
                      className="select"
                      value={formulario.modoPago}
                      onChange={(e) => cambiar('modoPago', e.target.value as ModoPago)}
                    >
                      {Object.values(ModoPago).map((modo) => (
                        <option key={modo} value={modo}>
                          {etiquetaModoPago(modo)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field" style={{ flex: 1 }}>
                    <label className="field__label" htmlFor="extra-precio">
                      {formulario.modoPago === ModoPago.destajo
                        ? 'Precio de destajo'
                        : 'Precio unitario'}
                    </label>
                    <input
                      id="extra-precio"
                      className="input mono"
                      type="number"
                      min="0"
                      step="0.01"
                      value={formulario.precio}
                      onChange={(e) => cambiar('precio', e.target.value)}
                      required
                    />
                    <div className="field__hint">
                      Sin precio no se puede estimar, y lo que no se estima no se
                      cobra (§11.3 E).
                    </div>
                  </div>
                  <div className="field" style={{ width: 120 }}>
                    <label className="field__label" htmlFor="extra-duracion">
                      Días
                    </label>
                    <input
                      id="extra-duracion"
                      className="input mono"
                      type="number"
                      min="0.5"
                      step="0.5"
                      value={formulario.duracionDias}
                      onChange={(e) => cambiar('duracionDias', e.target.value)}
                    />
                  </div>
                </div>
              </div>
              <div className="card__body" style={{ paddingTop: 0 }}>
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={crear.isPending || !extraCompleto(formulario)}
                >
                  {crear.isPending ? 'Dando de alta…' : 'Dar de alta'}
                </button>
              </div>
            </form>
          ) : (
            <div className="field__hint mb-8">
              El alta extra-catálogo la hace el residente de la obra (§11.2). Aquí
              puedes ver los que ya se registraron.
            </div>
          )}

          <div className="table-wrap">
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Trabajo</th>
                    <th>Estado</th>
                    <th className="is-num">Cantidad</th>
                    <th className="is-num">Ejecutado</th>
                    <th>Modo</th>
                  </tr>
                </thead>
                <tbody>
                  {actividades.isLoading ? (
                    <tr>
                      <td colSpan={5}>
                        <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                          Cargando…
                        </div>
                      </td>
                    </tr>
                  ) : extras.length === 0 ? (
                    <tr>
                      <td colSpan={5}>
                        <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                          Esta obra no tiene trabajo extra registrado.
                        </div>
                      </td>
                    </tr>
                  ) : (
                    extras.map((extra) => (
                      <tr key={extra.id}>
                        <td className="is-key">{extra.descripcion ?? extra.id.slice(0, 8)}</td>
                        <td>
                          <span
                            className={`badge badge--${tonoEstatusActividad(extra.estatus)}`}
                          >
                            {etiquetaEstatusActividad(extra.estatus)}
                          </span>
                        </td>
                        <td className="is-num mono">{fmtNum(Number(extra.cant_base))}</td>
                        <td className="is-num mono">
                          {fmtNum(Number(extra.cant_ejecutada))}
                        </td>
                        <td>{etiquetaModoPago(extra.modo_pago)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
