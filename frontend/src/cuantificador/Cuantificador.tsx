/**
 * Cuantificador — el plano, los trazos y lo que cada uno aporta a la obra
 * (cerebro MODELO.md §1b: `plano → trazo → enlace → cantidad`).
 *
 * Pantalla compartida (§5.3): los cuatro roles trazan, y RLS decide qué obras y
 * planos ve cada uno. Lo que se mide aquí **informa y no corrige**: sobre una
 * actividad, la cantidad medida se compara con `cant_base` y la diferencia es
 * candidata de desviación — nunca reemplaza el presupuesto.
 *
 * ## Todo pasa por el servidor
 *
 * El visor dibuja y captura; no calcula cantidades. La medida del trazo en
 * pantalla es una vista previa en unidades de plano. La que cuenta la calcula
 * PostGIS al guardar, y esa es la que vuelve en la tabla de estado.
 *
 * ## Teclado mientras se dibuja
 *
 * Enter cierra el trazo, Retroceso quita el último vértice, Esc lo descarta.
 * Se ignoran si el foco está en un campo de formulario o hay un cajón abierto:
 * escribir «0.5» en un factor no debe borrar vértices.
 */

import { useEffect, useMemo, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGetQueryKey,
  getListarPlanosApiV1ObrasObraIdPlanosGetQueryKey,
  getTrazosDePlanoApiV1PlanosPlanoIdTrazosGetQueryKey,
  useArchivoDePlanoApiV1PlanosPlanoIdArchivoGet,
  useEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGet,
  useListarPlanosApiV1ObrasObraIdPlanosGet,
  useTrazosDePlanoApiV1PlanosPlanoIdTrazosGet,
} from '@/api/generado/cuantificacion/cuantificacion';
import type {
  ActividadRespuesta,
  ArchivoDePlanoRespuesta,
  NodoCuantificadoRespuesta,
  PlanoDetalleRespuesta,
  TrazoRespuesta,
  TrazosDePlanoRespuesta,
} from '@/api/generado/modelo';
import { useActividadesDeObraApiV1ObrasObraIdActividadesGet } from '@/api/generado/torre/torre';
import { queryClient } from '@/app/queryClient';
import { fmtNum } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { SelectorObra } from '@/lib/SelectorObra';
import { AltaPlano } from './AltaPlano';
import { AltaTrazo } from './AltaTrazo';
import { Visor, type TrazoVisible } from './Visor';
import {
  trazoCompleto,
  type Herramienta,
  type HerramientaDeTrazo,
  type Punto,
} from './geometria';
import { etiquetaMedida } from './reglas';

const HERRAMIENTAS: readonly { readonly clave: Herramienta; readonly etiqueta: string }[] = [
  { clave: 'seleccionar', etiqueta: 'Seleccionar' },
  { clave: 'poligono', etiqueta: 'Polígono' },
  { clave: 'linea', etiqueta: 'Línea' },
  { clave: 'punto', etiqueta: 'Punto' },
];

const ES_IMAGEN = /\.(png|jpe?g|webp)$/i;

function etiquetaActividad(a: ActividadRespuesta | undefined, id: string): string {
  if (!a) return id.slice(0, 8);
  const donde = [a.nivel_clave, a.etapa_clave].filter(Boolean).join(' · ');
  const que = a.concepto_clave ?? a.descripcion ?? 'Actividad';
  return donde ? `${que} — ${donde}` : String(que);
}

export default function Cuantificador() {
  const [obraId, setObraId] = useState('');
  const [planoElegido, setPlanoElegido] = useState('');
  const [herramienta, setHerramienta] = useState<Herramienta>('seleccionar');
  const [borrador, setBorrador] = useState<readonly Punto[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [subiendoPlano, setSubiendoPlano] = useState(false);
  const [seleccionadoId, setSeleccionadoId] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const planos = useListarPlanosApiV1ObrasObraIdPlanosGet<
    PlanoDetalleRespuesta[],
    ErrorApi
  >(obraId, { query: { enabled: obraId !== '' } });
  const listaDePlanos = useMemo(() => planos.data ?? [], [planos.data]);

  // Al cambiar de obra se limpia todo lo que dependía de ella; al llegar la
  // lista, se abre el primer plano para no dejar al usuario frente a un vacío.
  useEffect(() => {
    setPlanoElegido('');
    setBorrador([]);
    setSeleccionadoId(null);
    setHerramienta('seleccionar');
  }, [obraId]);
  useEffect(() => {
    if (planoElegido === '' && listaDePlanos[0]) setPlanoElegido(listaDePlanos[0].id);
  }, [listaDePlanos, planoElegido]);

  const plano = listaDePlanos.find((p) => p.id === planoElegido);
  const esImagen = plano !== undefined && ES_IMAGEN.test(plano.archivo_url);

  const trazosConsulta = useTrazosDePlanoApiV1PlanosPlanoIdTrazosGet<
    TrazosDePlanoRespuesta,
    ErrorApi
  >(planoElegido, { query: { enabled: planoElegido !== '' } });
  const estado = useEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGet<
    NodoCuantificadoRespuesta[],
    ErrorApi
  >(obraId, { query: { enabled: obraId !== '' } });
  const actividadesConsulta = useActividadesDeObraApiV1ObrasObraIdActividadesGet<
    ActividadRespuesta[],
    ErrorApi
  >(obraId, undefined, { query: { enabled: obraId !== '' } });
  const actividades = useMemo(() => actividadesConsulta.data ?? [], [actividadesConsulta.data]);

  // La URL firmada solo se pide si el archivo es una imagen que el visor sabe
  // pintar. Una caducidad corta no es problema: se carga una vez al abrir el
  // plano y la imagen queda en memoria del navegador.
  const archivo = useArchivoDePlanoApiV1PlanosPlanoIdArchivoGet<
    ArchivoDePlanoRespuesta,
    ErrorApi
  >(planoElegido, { query: { enabled: planoElegido !== '' && esImagen, retry: false, staleTime: 5 * 60_000 } });

  const features = useMemo(() => trazosConsulta.data?.features ?? [], [trazosConsulta.data]);
  const trazosVisibles = useMemo<TrazoVisible[]>(
    () =>
      features.map((f) => ({
        id: f.id,
        geometry: f.geometry,
        porRevisar: f.properties.por_revisar,
      })),
    [features],
  );
  const seleccionado = features.find((f) => f.id === seleccionadoId) ?? null;

  const forma: HerramientaDeTrazo | null = herramienta === 'seleccionar' ? null : herramienta;

  function cambiarHerramienta(nueva: Herramienta) {
    setHerramienta(nueva);
    setBorrador([]);
    setAviso(null);
    if (nueva !== 'seleccionar') setSeleccionadoId(null);
  }

  function alPunto(p: Punto) {
    if (!forma) return;
    setAviso(null);
    if (forma === 'punto') {
      setBorrador([p]);
      setGuardando(true);
      return;
    }
    setBorrador((actual) => [...actual, p]);
  }

  function terminar() {
    if (forma && trazoCompleto(forma, borrador)) setGuardando(true);
  }

  // Atajos mientras se dibuja. El efecto se rearma con cada cambio del borrador:
  // los manejadores leen el estado de este render, no uno viejo.
  useEffect(() => {
    if (!forma || guardando || subiendoPlano) return;
    function alTeclear(e: KeyboardEvent) {
      const destino = e.target as HTMLElement | null;
      if (destino && /^(INPUT|SELECT|TEXTAREA)$/.test(destino.tagName)) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        if (forma && trazoCompleto(forma, borrador)) setGuardando(true);
      } else if (e.key === 'Backspace') {
        e.preventDefault();
        setBorrador((actual) => actual.slice(0, -1));
      } else if (e.key === 'Escape') {
        setBorrador([]);
      }
    }
    window.addEventListener('keydown', alTeclear);
    return () => window.removeEventListener('keydown', alTeclear);
  }, [forma, borrador, guardando, subiendoPlano]);

  function alGuardar(resultado: TrazoRespuesta) {
    setGuardando(false);
    setBorrador([]);
    const total = resultado.recalculos[0]?.cantidad_total;
    setAviso(
      resultado.enlace_ids.length === 0
        ? 'Trazo guardado, todavía sin enlace a ninguna actividad.'
        : `Trazo guardado. Cantidad medida del nodo: ${fmtNum(total)}.`,
    );
    void queryClient.invalidateQueries({
      queryKey: getTrazosDePlanoApiV1PlanosPlanoIdTrazosGetQueryKey(planoElegido),
    });
    void queryClient.invalidateQueries({
      queryKey: getEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGetQueryKey(obraId),
    });
    void queryClient.invalidateQueries({
      queryKey: getListarPlanosApiV1ObrasObraIdPlanosGetQueryKey(obraId),
    });
  }

  const porActividad = useMemo(() => new Map(actividades.map((a) => [a.id, a])), [actividades]);
  const nodos = estado.data ?? [];

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Presupuesto</div>
          <h1 className="page__title">Cuantificador</h1>
          <div className="page__subtitle">
            Traza sobre el plano y enlaza cada trazo a las actividades que alimenta. Lo que se
            mide <strong>informa</strong> y se compara con la cantidad base; no la reemplaza.
          </div>
        </div>
      </div>

      <div className="filterbar">
        <div style={{ minWidth: 220 }}>
          <SelectorObra id="cuant-obra" etiqueta="Obra" valor={obraId} onCambio={setObraId} />
        </div>
        <div className="field" style={{ minWidth: 240 }}>
          <label className="field__label" htmlFor="cuant-plano">
            Plano
          </label>
          <select
            id="cuant-plano"
            className="select"
            value={planoElegido}
            disabled={obraId === ''}
            onChange={(e) => {
              setPlanoElegido(e.target.value);
              setBorrador([]);
              setSeleccionadoId(null);
            }}
          >
            <option value="">{obraId === '' ? 'Elige una obra primero' : 'Sin planos'}</option>
            {listaDePlanos.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre} · v{p.version}
                {p.n_trazos_por_revisar > 0 ? ` · ${p.n_trazos_por_revisar} por revisar` : ''}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className="btn"
          disabled={obraId === ''}
          onClick={() => setSubiendoPlano(true)}
        >
          Subir plano
        </button>
      </div>

      {obraId === '' ? (
        <div className="empty">
          <div className="empty-title">Elige una obra</div>
          <div className="empty-sub">Los planos y sus trazos son de una obra.</div>
        </div>
      ) : plano === undefined ? (
        <div className="empty">
          <div className="empty-title">{planos.isLoading ? 'Cargando planos…' : 'Esta obra no tiene planos'}</div>
          {!planos.isLoading && (
            <div className="empty-sub">Sube una imagen del plano para empezar a trazar.</div>
          )}
        </div>
      ) : (
        <div className="cuant">
          <div className="cuant__lienzo">
            <div className="row cuant__barra" role="toolbar" aria-label="Herramientas de trazo">
              {HERRAMIENTAS.map((h) => (
                <button
                  key={h.clave}
                  type="button"
                  className={`btn btn--sm${herramienta === h.clave ? ' btn--primary' : ''}`}
                  aria-pressed={herramienta === h.clave}
                  onClick={() => cambiarHerramienta(h.clave)}
                >
                  {h.etiqueta}
                </button>
              ))}
              {forma && forma !== 'punto' && (
                <>
                  <span className="text-mute text-xs">
                    {borrador.length} vértices · Enter cierra · Retroceso quita · Esc descarta
                  </span>
                  <button
                    type="button"
                    className="btn btn--accent btn--sm"
                    disabled={!trazoCompleto(forma, borrador)}
                    onClick={terminar}
                  >
                    Terminar trazo
                  </button>
                </>
              )}
            </div>

            {aviso && (
              <div className="text-sm" role="status">
                {aviso}
              </div>
            )}
            {trazosConsulta.error && <ErrorBanner mensaje={trazosConsulta.error.message} />}
            {!esImagen && (
              <div className="text-mute text-xs">
                Este plano no es una imagen (PNG, JPG o WebP): el visor aún no pinta PDF, así que
                se traza sobre una rejilla en blanco.
              </div>
            )}
            {esImagen && archivo.error && (
              <div className="text-mute text-xs">
                No se pudo cargar el archivo del plano ({archivo.error.message}). Los trazos se
                muestran sobre una rejilla en blanco.
              </div>
            )}

            <Visor
              claveDePlano={planoElegido}
              fondoUrl={esImagen ? (archivo.data?.url ?? null) : null}
              trazos={trazosVisibles}
              seleccionadoId={seleccionadoId}
              herramienta={herramienta}
              borrador={borrador}
              onPunto={alPunto}
              onSeleccionar={setSeleccionadoId}
            />
          </div>

          <aside className="cuant__lateral col gap-12">
            <div className="card">
              <div className="card__header">
                <div className="card__title">{seleccionado ? 'Trazo elegido' : 'Trazos del plano'}</div>
              </div>
              <div className="card__body col">
                {seleccionado ? (
                  <>
                    <div className="text-sm">
                      {seleccionado.properties.capa ?? 'Sin capa'} ·{' '}
                      <span className="mono">{seleccionado.properties.fuente.toUpperCase()}</span>
                    </div>
                    {seleccionado.properties.por_revisar && (
                      <span className="badge badge--warn">
                        Hecho sobre una versión anterior: revísalo
                      </span>
                    )}
                    {seleccionado.properties.enlaces.length === 0 ? (
                      <div className="text-mute text-sm">Sin enlaces: no alimenta ninguna cantidad.</div>
                    ) : (
                      <table className="table">
                        <thead>
                          <tr>
                            <th>Actividad</th>
                            <th>Medida</th>
                            <th className="is-num">Cantidad</th>
                          </tr>
                        </thead>
                        <tbody>
                          {seleccionado.properties.enlaces.map((e) => (
                            <tr key={e.enlace_id} style={e.vigente ? undefined : { opacity: 0.5 }}>
                              <td>
                                {etiquetaActividad(porActividad.get(e.nodo_id), e.nodo_id)}
                                {!e.vigente && <span className="text-mute"> · reemplazado</span>}
                              </td>
                              <td>
                                {etiquetaMedida(e.medida)} × {fmtNum(e.factor)}
                              </td>
                              <td className="is-num">{fmtNum(e.cantidad)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </>
                ) : (
                  <div className="text-mute text-sm">
                    {features.length === 0
                      ? 'Este plano aún no tiene trazos.'
                      : `${features.length} ${features.length === 1 ? 'trazo' : 'trazos'}. Elige uno con la herramienta Seleccionar.`}
                  </div>
                )}
              </div>
            </div>

            <div className="card">
              <div className="card__header">
                <div className="card__title">Cuantificación de la obra</div>
                <div className="card__sub">Medido contra el presupuesto</div>
              </div>
              <div className="card__body card__body--flush">
                {estado.error ? (
                  <div className="card__body">
                    <ErrorBanner mensaje={estado.error.message} />
                  </div>
                ) : nodos.length === 0 ? (
                  <div className="card__body text-mute text-sm">
                    Ningún trazo está enlazado todavía.
                  </div>
                ) : (
                  <div className="table-scroll">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Nodo</th>
                          <th className="is-num">Base</th>
                          <th className="is-num">Medido</th>
                          <th className="is-num">Dif.</th>
                        </tr>
                      </thead>
                      <tbody>
                        {nodos.map((n) => (
                          <tr key={`${n.tipo_nodo}-${n.nodo_id}`}>
                            <td>
                              {n.descripcion ?? etiquetaActividad(porActividad.get(n.nodo_id), n.nodo_id)}
                              {n.trazos_por_revisar > 0 && (
                                <span className="badge badge--warn" style={{ marginLeft: 6 }}>
                                  {n.trazos_por_revisar} por revisar
                                </span>
                              )}
                            </td>
                            <td className="is-num">{fmtNum(n.cant_base)}</td>
                            <td className="is-num">{fmtNum(n.cantidad_medida)}</td>
                            <td className="is-num">{fmtNum(n.diferencia)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </aside>
        </div>
      )}

      {guardando && plano && forma && (
        <AltaTrazo
          planoId={plano.id}
          versionPlano={plano.version}
          herramienta={forma}
          puntos={borrador}
          actividades={actividades}
          onCerrar={() => {
            setGuardando(false);
            // Un punto se captura con un solo clic: si se cancela el cajón no
            // hay nada que seguir editando, se descarta.
            if (forma === 'punto') setBorrador([]);
          }}
          onGuardado={alGuardar}
        />
      )}

      {subiendoPlano && (
        <AltaPlano
          obraId={obraId}
          onCerrar={() => setSubiendoPlano(false)}
          onRegistrado={(id) => {
            setSubiendoPlano(false);
            setPlanoElegido(id);
            void queryClient.invalidateQueries({
              queryKey: getListarPlanosApiV1ObrasObraIdPlanosGetQueryKey(obraId),
            });
          }}
        />
      )}
    </div>
  );
}
