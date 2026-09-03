/**
 * Fuera de catálogo y extra de catálogo — dos cosas, no sinónimos (§11.2, §11.3).
 *
 * El jefe de obra las separó: *"fuera de catálogo son actividades que no están
 * en el catálogo, y extra de catálogo son las que solicita el residente cuando
 * se termina el umbral"*. Esta pantalla las presenta como lo que son, porque
 * confundirlas manda al residente por el camino equivocado:
 *
 * | | Fuera de catálogo | Extra de catálogo |
 * |---|---|---|
 * | Qué es | trabajo que no está en el catálogo | más cantidad de algo que ya está |
 * | Cuándo | apareció en la obra | se agotó el umbral |
 * | Precio | lo arma el residente | el del catálogo |
 * | Quién lo mete | el residente lo da de alta | el residente **pide**, Control autoriza |
 *
 * ## El umbral se ve antes de agotarse
 *
 * La pestaña de extra lista lo que ya no tiene margen y lo que está cerca. El
 * umbral no avisa: descubrirlo el día que se necesita la cantidad es tarde,
 * porque para entonces hay gente parada esperando una autorización.
 *
 * ## Dónde cae el trabajo
 *
 * Toda alta identifica **frente** (nivel) y **sub-frente** (etapa). Sin ellos la
 * actividad no aparece en ningún grupo de Avances del día y queda huérfana.
 */

import { useMemo, useState } from 'react';

import {
  useActividadesDeObraApiV1ObrasObraIdActividadesGet,
  useArmarPrecioDeExtraApiV1ActividadesPrecioArmadoPost,
  useDarDeAltaExtraApiV1ActividadesPost,
} from '@/api/generado/torre/torre';
import {
  useListarControlesDeCambioApiV1ControlesCambioGet,
  useSolicitarControlDeCambioApiV1ObrasObraIdControlesCambioPost,
} from '@/api/generado/control-cambio/control-cambio';
import { useListarCuadrillasApiV1CuadrillasGet } from '@/api/generado/catalogos/catalogos';
import {
  ModoPago,
  TipoControlCambio,
  type ActividadRespuesta,
  type ControlCambioRespuesta,
  type CuadrillaRespuesta,
  type PrecioArmadoRespuesta,
} from '@/api/generado/modelo';
import { claveDeIdempotencia, type ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { SelectorObra } from '@/lib/SelectorObra';
import { fmtFecha, fmtMXN, fmtNum } from '@/lib/formato';
import { tonoEstatusActividad } from '@/avance/reglas';
import {
  etiquetaTipoCambio,
  margenDe,
  PESTANAS_EXTRA,
  sinMargen,
  techoDe,
  tonoEstatusCambio,
  type PestanaExtra,
} from './reglas';

export default function ExtraCatalogo() {
  const [obraId, setObraId] = useState('');
  const [pestana, setPestana] = useState<PestanaExtra>('fuera');
  const [dandoDeAlta, setDandoDeAlta] = useState(false);
  const [pidiendo, setPidiendo] = useState<ActividadRespuesta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const actividadesQ = useActividadesDeObraApiV1ObrasObraIdActividadesGet<
    ActividadRespuesta[],
    ErrorApi
  >(obraId, undefined, { query: { enabled: obraId !== '' } });

  const controlesQ = useListarControlesDeCambioApiV1ControlesCambioGet<
    ControlCambioRespuesta[],
    ErrorApi
  >({ obra_id: obraId || undefined }, { query: { enabled: obraId !== '' } });

  const actividades = useMemo(() => actividadesQ.data ?? [], [actividadesQ.data]);
  const fueraDeCatalogo = useMemo(
    () => actividades.filter((a) => a.extra),
    [actividades],
  );
  // Ordenadas por lo que menos margen les queda: es la lista de "por esto voy a
  // tener que pedir", y la de arriba es la que urge.
  const conUmbral = useMemo(
    () =>
      [...actividades]
        .filter((a) => !a.extra)
        .sort((a, b) => margenDe(a) - margenDe(b)),
    [actividades],
  );

  function alPedir(): void {
    setPidiendo(null);
    setAviso('Solicitud enviada a Control de obra.');
    void controlesQ.refetch();
    setPestana('solicitudes');
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Mi trabajo</div>
          <h1 className="page__title">Fuera de catálogo</h1>
          <div className="page__subtitle">
            Trabajo que no está en el catálogo lo das de alta con su precio. Más
            cantidad de algo que ya está —cuando se agota el umbral— se{' '}
            <strong>pide</strong> a Control de obra: no son lo mismo y no se
            resuelven igual.
          </div>
        </div>
        <div className="page__actions">
          <button
            type="button"
            className="btn btn--primary"
            disabled={obraId === ''}
            title={obraId === '' ? 'Elige primero tu obra' : undefined}
            onClick={() => {
              setError(null);
              setDandoDeAlta(true);
            }}
          >
            + Nueva actividad
          </button>
        </div>
      </div>

      {actividadesQ.error && <ErrorBanner mensaje={actividadesQ.error.message} />}
      {error && <ErrorBanner mensaje={error} />}
      {aviso && (
        <div className="mb-8" role="status">
          <span className="badge badge--ok">{aviso}</span>{' '}
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setAviso(null)}
          >
            Entendido
          </button>
        </div>
      )}

      <div className="filterbar">
        <div style={{ minWidth: 260 }}>
          <SelectorObra
            id="obra"
            etiqueta="Obra"
            valor={obraId}
            onCambio={setObraId}
          />
        </div>
      </div>

      {obraId !== '' && (
        <>
          <div className="tabs mb-8" role="tablist" aria-label="Fuera de catálogo">
            {PESTANAS_EXTRA.map((opcion) => (
              <button
                key={opcion.clave}
                type="button"
                role="tab"
                aria-selected={pestana === opcion.clave}
                title={opcion.ayuda}
                className={`tabs__tab${pestana === opcion.clave ? ' is-active' : ''}`}
                onClick={() => setPestana(opcion.clave)}
              >
                {opcion.etiqueta}{' '}
                <span className="text-mute tnum">
                  {opcion.clave === 'fuera'
                    ? fueraDeCatalogo.length
                    : opcion.clave === 'extra'
                      ? conUmbral.filter(sinMargen).length
                      : (controlesQ.data ?? []).length}
                </span>
              </button>
            ))}
          </div>
          <div className="field__hint mb-8">
            {PESTANAS_EXTRA.find((o) => o.clave === pestana)?.ayuda}
          </div>
        </>
      )}

      {obraId === '' ? (
        <div className="empty">
          <div className="empty-title">Elige tu obra</div>
          <div className="empty-sub">
            El trabajo fuera de catálogo aparece en una obra concreta.
          </div>
        </div>
      ) : pestana === 'fuera' ? (
        <TablaFueraDeCatalogo actividades={fueraDeCatalogo} />
      ) : pestana === 'extra' ? (
        <TablaDelUmbral actividades={conUmbral} onPedir={setPidiendo} />
      ) : (
        <TablaDeSolicitudes controles={controlesQ.data ?? []} />
      )}

      {dandoDeAlta && (
        <AltaFueraDeCatalogo
          obraId={obraId}
          actividades={actividades}
          onCerrar={() => setDandoDeAlta(false)}
          onCreada={() => {
            setDandoDeAlta(false);
            setAviso('Actividad dada de alta.');
            void actividadesQ.refetch();
          }}
          onError={setError}
        />
      )}

      {pidiendo !== null && (
        <PedirMasCantidad
          obraId={obraId}
          actividad={pidiendo}
          onCerrar={() => setPidiendo(null)}
          onPedida={alPedir}
          onError={setError}
        />
      )}
    </div>
  );
}

function TablaFueraDeCatalogo({
  actividades,
}: {
  readonly actividades: readonly ActividadRespuesta[];
}) {
  if (actividades.length === 0) {
    return (
      <div className="empty">
        <div className="empty-title">Nada fuera de catálogo todavía</div>
        <div className="empty-sub">
          Aquí aparece el trabajo que no estaba en el prototipo: un muro que
          había que demoler, una instalación que el proyecto no traía.
        </div>
      </div>
    );
  }
  return (
    <div className="table-wrap">
      <div className="table-scroll">
        <table className="table" style={{ minWidth: 'max-content' }}>
          <thead>
            <tr>
              <th style={{ minWidth: 90 }}>Clave</th>
              <th style={{ minWidth: 280 }}>Descripción</th>
              <th style={{ minWidth: 130 }}>Frente</th>
              <th style={{ minWidth: 150 }}>Sub-frente</th>
              <th style={{ minWidth: 64 }}>Unid.</th>
              <th className="is-num" style={{ minWidth: 90 }}>
                Base
              </th>
              <th className="is-num" style={{ minWidth: 100 }}>
                Ejecutada
              </th>
              <th className="is-num" style={{ minWidth: 110 }}>
                Precio
              </th>
              <th style={{ minWidth: 130 }}>Orden de cambio</th>
              <th style={{ minWidth: 110 }}>Estatus</th>
            </tr>
          </thead>
          <tbody>
            {actividades.map((a) => (
              <tr key={a.id}>
                <td className="mono text-xs">
                  <span className="badge badge--outline">EXT</span>
                </td>
                <td>{a.descripcion}</td>
                <td className="text-xs">{a.nivel_descripcion ?? '—'}</td>
                <td className="text-xs text-mute">{a.etapa_descripcion ?? '—'}</td>
                <td className="mono text-xs">{a.unidad ?? '—'}</td>
                <td className="is-num tnum">{fmtNum(a.cant_base)}</td>
                <td className="is-num tnum">{fmtNum(a.cant_ejecutada)}</td>
                <td className="is-num tnum">
                  {fmtMXN(
                    a.modo_pago === ModoPago.destajo
                      ? a.precio_destajo
                      : a.precio_unitario,
                  )}
                </td>
                <td className="mono text-xs">{a.orden_cambio ?? '—'}</td>
                <td>
                  <span className={`badge badge--${tonoEstatusActividad(a.estatus)}`}>
                    {a.estatus.replace('_', ' ')}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * Lo que está por agotar su umbral, lo más apretado arriba.
 *
 * El umbral no avisa antes de agotarse: descubrirlo el día que se necesita la
 * cantidad es tarde, porque para entonces hay gente parada esperando una
 * autorización que tarda.
 */
function TablaDelUmbral({
  actividades,
  onPedir,
}: {
  readonly actividades: readonly ActividadRespuesta[];
  readonly onPedir: (actividad: ActividadRespuesta) => void;
}) {
  if (actividades.length === 0) {
    return (
      <div className="empty">
        <div className="empty-title">Esta obra no tiene actividades de catálogo</div>
        <div className="empty-sub">Falta generarla o aplicarle el programa base.</div>
      </div>
    );
  }
  return (
    <div className="table-wrap">
      <div className="table-scroll">
        <table className="table" style={{ minWidth: 'max-content' }}>
          <thead>
            <tr>
              <th style={{ minWidth: 120 }}>Clave</th>
              <th style={{ minWidth: 260 }}>Descripción</th>
              <th style={{ minWidth: 130 }}>Frente</th>
              <th className="is-num" style={{ minWidth: 90 }}>
                Base
              </th>
              <th className="is-num" style={{ minWidth: 100 }}>
                Programada
              </th>
              <th
                className="is-num"
                style={{ minWidth: 90 }}
                title="Hasta aquí puedes programar sin pedir autorización"
              >
                Techo
              </th>
              <th className="is-num" style={{ minWidth: 110 }}>
                Margen
              </th>
              <th className="cell-actions" />
            </tr>
          </thead>
          <tbody>
            {actividades.map((a) => {
              const margen = margenDe(a);
              const agotada = margen <= 0;
              return (
                <tr key={a.id}>
                  <td className="mono text-xs">{a.concepto_clave ?? '—'}</td>
                  <td>{a.descripcion}</td>
                  <td className="text-xs">{a.nivel_descripcion ?? '—'}</td>
                  <td className="is-num tnum">{fmtNum(a.cant_base)}</td>
                  <td className="is-num tnum">{fmtNum(a.cant_programada)}</td>
                  <td className="is-num tnum text-mute">{fmtNum(techoDe(a))}</td>
                  <td className="is-num">
                    <span className={`badge badge--${agotada ? 'danger' : 'ok'}`}>
                      {agotada ? 'Agotado' : fmtNum(margen)}
                    </span>
                    {a.cant_autorizada !== null && a.cant_autorizada !== undefined && (
                      <span
                        className="badge badge--info"
                        title={`Autorizada por ${a.orden_cambio ?? 'orden de cambio'}`}
                      >
                        OC
                      </span>
                    )}
                  </td>
                  <td className="cell-actions">
                    <button
                      type="button"
                      className="btn btn--sm"
                      onClick={() => onPedir(a)}
                    >
                      Pedir más
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TablaDeSolicitudes({
  controles,
}: {
  readonly controles: readonly ControlCambioRespuesta[];
}) {
  if (controles.length === 0) {
    return (
      <div className="empty">
        <div className="empty-title">No has pedido nada</div>
        <div className="empty-sub">
          Lo que pidas a Control de obra aparece aquí con su resolución y su
          orden de cambio.
        </div>
      </div>
    );
  }
  return (
    <div className="table-wrap">
      <div className="table-scroll">
        <table className="table" style={{ minWidth: 'max-content' }}>
          <thead>
            <tr>
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
            </tr>
          </thead>
          <tbody>
            {controles.map((c) => (
              <tr key={c.id}>
                <td className="text-sm">{etiquetaTipoCambio(c.tipo)}</td>
                <td>{c.motivo}</td>
                <td className="is-num tnum">{c.renglones}</td>
                <td className="is-num tnum">{fmtMXN(c.importe)}</td>
                <td className="text-xs">{fmtFecha(c.solicitado_en)}</td>
                <td>
                  <span className={`badge badge--${tonoEstatusCambio(c.estatus)}`}>
                    {c.estatus}
                  </span>
                </td>
                <td className="mono text-xs">
                  {c.orden_cambio ?? (
                    <span className="text-mute">
                      {c.estatus === 'solicitado' ? 'esperando' : '—'}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * Dar de alta trabajo que no está en el catálogo, con su precio armado.
 *
 * El jefe de obra: *"el residente dice qué cuadrilla va a utilizar, cuántas y
 * el tiempo, también el material a utilizar, y se crea el precio"*.
 *
 * El precio lo calcula el **servidor** (`POST /actividades/precio-armado`), no
 * esta pantalla: los costos son del catálogo y mandarlos al cliente para
 * multiplicar aquí expondría el costo a quien solo necesita el precio, y dejaría
 * la fórmula en dos lugares que un día divergen.
 *
 * ## Frente y sub-frente
 *
 * Se toman de una actividad vecina en vez de pedir dos selectores más: el
 * residente ya sabe junto a qué está trabajando, y "como esta otra" es más
 * rápido y menos equivocable que elegir de dos catálogos.
 */
function AltaFueraDeCatalogo({
  obraId,
  actividades,
  onCerrar,
  onCreada,
  onError,
}: {
  readonly obraId: string;
  readonly actividades: readonly ActividadRespuesta[];
  readonly onCerrar: () => void;
  readonly onCreada: () => void;
  readonly onError: (mensaje: string) => void;
}) {
  const [descripcion, setDescripcion] = useState('');
  const [ordenCambio, setOrdenCambio] = useState('');
  const [cantidad, setCantidad] = useState('');
  const [vecina, setVecina] = useState('');
  const [cuadrillas, setCuadrillas] = useState<readonly LineaCuadrillaUI[]>([]);
  const [precio, setPrecio] = useState<PrecioArmadoRespuesta | null>(null);

  // Clave fija por formulario: un doble clic crearía **dos** actividades con la
  // misma orden de cambio, y las dos se estimarían — el extra se paga dos veces.
  const clave = useMemo(claveDeIdempotencia, []);

  const cuadrillasQ = useListarCuadrillasApiV1CuadrillasGet<
    CuadrillaRespuesta[],
    ErrorApi
  >(undefined);

  const armar = useArmarPrecioDeExtraApiV1ActividadesPrecioArmadoPost<ErrorApi>({
    mutation: {
      onSuccess: (r) => setPrecio(r as PrecioArmadoRespuesta),
      onError: (err) => onError(err.message),
    },
  });

  const crear = useDarDeAltaExtraApiV1ActividadesPost<ErrorApi>({
    mutation: { onSuccess: onCreada, onError: (err) => onError(err.message) },
  });

  const ubicacion = actividades.find((a) => a.id === vecina);
  const cantidadNum = cantidad.trim() === '' ? 0 : Number(cantidad);

  function recalcular(lineas: readonly LineaCuadrillaUI[]): void {
    if (cantidadNum <= 0) return;
    const utiles = lineas.filter(
      (l) => l.cuadrillaId !== '' && Number(l.cuantas) > 0 && Number(l.dias) > 0,
    );
    armar.mutate({
      data: {
        cantidad: cantidadNum,
        cuadrillas: utiles.map((l) => ({
          cuadrilla_id: l.cuadrillaId,
          cuadrillas: Number(l.cuantas),
          dias: Number(l.dias),
        })),
        materiales: [],
      },
    });
  }

  function cambiarLinea(indice: number, cambios: Partial<LineaCuadrillaUI>): void {
    const siguiente = cuadrillas.map((l, i) => (i === indice ? { ...l, ...cambios } : l));
    setCuadrillas(siguiente);
    recalcular(siguiente);
  }

  const listo =
    descripcion.trim() !== '' &&
    ordenCambio.trim() !== '' &&
    cantidadNum > 0 &&
    precio !== null &&
    Number(precio.precio_unitario) > 0;

  return (
    <Modal titulo="Nueva actividad fuera de catálogo" onCerrar={onCerrar}>
      <div className="sheet__body">
        <div className="field">
          <label className="field__label" htmlFor="descripcion">
            Qué trabajo es
          </label>
          <input
            id="descripcion"
            className="input"
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
            placeholder="Demolición de bardas perimetrales preexistentes"
          />
        </div>

        <div className="row gap-8 mt-8">
          <div className="field" style={{ maxWidth: 150 }}>
            <label className="field__label" htmlFor="cantidad">
              Cantidad
            </label>
            <input
              id="cantidad"
              className="input"
              type="number"
              min={0}
              step="any"
              value={cantidad}
              onChange={(e) => setCantidad(e.target.value)}
              onBlur={() => recalcular(cuadrillas)}
            />
          </div>
          <div className="field" style={{ minWidth: 240 }}>
            <label className="field__label" htmlFor="vecina">
              Va junto a
            </label>
            <select
              id="vecina"
              className="select"
              value={vecina}
              onChange={(e) => setVecina(e.target.value)}
            >
              <option value="">Elige una actividad cercana…</option>
              {actividades.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.nivel_descripcion} · {a.etapa_descripcion} ·{' '}
                  {(a.descripcion ?? '').slice(0, 34)}
                </option>
              ))}
            </select>
            <span className="field__hint">
              De ahí salen el frente y el sub-frente: sin ellos la actividad no
              aparece en tu día.
            </span>
          </div>
        </div>

        <div className="field mt-8">
          <label className="field__label" htmlFor="oc">
            Orden de cambio
          </label>
          <input
            id="oc"
            className="input"
            value={ordenCambio}
            onChange={(e) => setOrdenCambio(e.target.value)}
            placeholder="OC-2026-014"
          />
          <span className="field__hint">
            Obligatoria: es lo que autoriza el trabajo, y la base la exige.
          </span>
        </div>

        <div className="mt-8">
          <div className="row gap-8" style={{ alignItems: 'center' }}>
            <strong className="text-sm">Con qué se va a hacer</strong>
            <button
              type="button"
              className="btn btn--sm"
              onClick={() =>
                setCuadrillas([...cuadrillas, { cuadrillaId: '', cuantas: '1', dias: '1' }])
              }
            >
              + Cuadrilla
            </button>
          </div>

          {cuadrillas.map((linea, indice) => (
            <div key={indice} className="row gap-4 mt-8" style={{ alignItems: 'end' }}>
              <div className="field" style={{ minWidth: 240 }}>
                <select
                  className="select"
                  value={linea.cuadrillaId}
                  aria-label="Cuadrilla"
                  onChange={(e) => cambiarLinea(indice, { cuadrillaId: e.target.value })}
                >
                  <option value="">Elige cuadrilla…</option>
                  {(cuadrillasQ.data ?? []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.clave} · {c.nombre}
                      {c.costo_jornada === null || c.costo_jornada === undefined
                        ? ' (sin costo)'
                        : ''}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field" style={{ maxWidth: 100 }}>
                <input
                  className="input"
                  type="number"
                  min={1}
                  aria-label="Cuántas"
                  value={linea.cuantas}
                  onChange={(e) => cambiarLinea(indice, { cuantas: e.target.value })}
                />
                <span className="field__hint">cuántas</span>
              </div>
              <div className="field" style={{ maxWidth: 100 }}>
                <input
                  className="input"
                  type="number"
                  min={1}
                  aria-label="Días"
                  value={linea.dias}
                  onChange={(e) => cambiarLinea(indice, { dias: e.target.value })}
                />
                <span className="field__hint">días</span>
              </div>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                aria-label="Quitar cuadrilla"
                onClick={() => {
                  const siguiente = cuadrillas.filter((_, i) => i !== indice);
                  setCuadrillas(siguiente);
                  recalcular(siguiente);
                }}
              >
                Quitar
              </button>
            </div>
          ))}
        </div>

        {precio !== null && (
          <div className="mt-8">
            <div className="row gap-8 text-sm" style={{ flexWrap: 'wrap' }}>
              <span>
                Mano de obra <strong>{fmtMXN(precio.mano_obra)}</strong>
              </span>
              <span>
                Materiales <strong>{fmtMXN(precio.materiales)}</strong>
              </span>
              <span>
                Total <strong>{fmtMXN(precio.total)}</strong>
              </span>
              <span>
                Unitario <strong>{fmtMXN(precio.precio_unitario)}</strong>
              </span>
            </div>
            {!precio.completo && (
              <div className="mt-8" role="status">
                <span className="badge badge--warn">Incompleto</span> Falta el
                costo de: {(precio.sin_costo ?? []).join(', ')}. El total está por debajo
                de lo que cuesta — captúralo en Catálogos → Cuadrillas.
              </div>
            )}
          </div>
        )}
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!listo || crear.isPending}
          title={listo ? undefined : 'Falta descripción, cantidad, orden de cambio o precio'}
          onClick={() =>
            crear.mutate({
              data: {
                obra_id: obraId,
                descripcion: descripcion.trim(),
                orden_cambio: ordenCambio.trim(),
                cant_base: cantidadNum,
                modo_pago: ModoPago.destajo,
                precio_destajo: Number(precio?.precio_unitario ?? 0),
                nivel_id: ubicacion?.nivel_id ?? null,
                etapa_id: ubicacion?.etapa_id ?? null,
              },
              headers: { 'Idempotency-Key': clave },
            } as never)
          }
        >
          {crear.isPending ? 'Guardando…' : 'Dar de alta'}
        </button>
      </div>
    </Modal>
  );
}

interface LineaCuadrillaUI {
  readonly cuadrillaId: string;
  readonly cuantas: string;
  readonly dias: string;
}

/**
 * Pedirle a Control más cantidad de algo que ya está en la obra.
 *
 * No se da de alta: se **solicita**. La orden de cambio la captura quien
 * autoriza, no quien pide — una orden tecleada por el solicitante no autoriza
 * nada, y por eso este formulario no la tiene.
 */
function PedirMasCantidad({
  obraId,
  actividad,
  onCerrar,
  onPedida,
  onError,
}: {
  readonly obraId: string;
  readonly actividad: ActividadRespuesta;
  readonly onCerrar: () => void;
  readonly onPedida: () => void;
  readonly onError: (mensaje: string) => void;
}) {
  const [cantidad, setCantidad] = useState(String(techoDe(actividad)));
  const [motivo, setMotivo] = useState('');

  const pedir = useSolicitarControlDeCambioApiV1ObrasObraIdControlesCambioPost<ErrorApi>(
    {
      mutation: { onSuccess: onPedida, onError: (err) => onError(err.message) },
    },
  );

  const nueva = cantidad.trim() === '' ? 0 : Number(cantidad);
  const sube = nueva > techoDe(actividad);
  const precio = Number(
    actividad.modo_pago === ModoPago.destajo
      ? actividad.precio_destajo
      : actividad.precio_unitario,
  );

  return (
    <Modal
      titulo={`Pedir más cantidad · ${actividad.concepto_clave ?? ''}`}
      onCerrar={onCerrar}
    >
      <div className="sheet__body">
        <p className="text-mute text-sm">
          {actividad.descripcion}
          <br />
          {actividad.nivel_descripcion} · {actividad.etapa_descripcion}
        </p>

        <div className="row gap-8 text-sm mt-8" style={{ flexWrap: 'wrap' }}>
          <span>
            Base <strong>{fmtNum(actividad.cant_base)}</strong>
          </span>
          <span>
            Programada <strong>{fmtNum(actividad.cant_programada)}</strong>
          </span>
          <span>
            Techo actual <strong>{fmtNum(techoDe(actividad))}</strong>
          </span>
        </div>

        <div className="field mt-8" style={{ maxWidth: 180 }}>
          <label className="field__label" htmlFor="nueva-cantidad">
            Cantidad que necesitas
          </label>
          <input
            id="nueva-cantidad"
            className="input"
            type="number"
            min={0}
            step="any"
            value={cantidad}
            onChange={(e) => setCantidad(e.target.value)}
          />
        </div>

        <div className="field mt-8">
          <label className="field__label" htmlFor="motivo">
            Por qué hace falta
          </label>
          <textarea
            id="motivo"
            className="input"
            rows={3}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Se agotó la cantidad y falta el eje 3"
          />
          <span className="field__hint">
            Quien autoriza no estuvo en la obra: esto es todo lo que va a tener
            para decidir.
          </span>
        </div>

        {sube && precio > 0 && (
          <div className="mt-8" role="status">
            <span className="badge badge--info">Costo</span> Le mueve{' '}
            <strong>{fmtMXN((nueva - Number(actividad.cant_programada)) * precio)}</strong>{' '}
            al costo final de la obra.
          </div>
        )}
        {!sube && (
          <div className="mt-8" role="status">
            <span className="badge badge--outline">Ojo</span> Esa cantidad cabe
            en tu techo actual: no hace falta pedir nada, captúrala en Avances.
          </div>
        )}
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!sube || motivo.trim() === '' || pedir.isPending}
          onClick={() =>
            pedir.mutate({
              obraId,
              data: {
                tipo: TipoControlCambio.extra_catalogo,
                motivo: motivo.trim(),
                nivel_id: actividad.nivel_id ?? null,
                etapa_id: actividad.etapa_id ?? null,
                lineas: [
                  {
                    actividad_id: actividad.id,
                    cantidad: nueva,
                    precio_unitario: precio,
                  },
                ],
              },
            } as never)
          }
        >
          {pedir.isPending ? 'Enviando…' : 'Pedir a Control'}
        </button>
      </div>
    </Modal>
  );
}
