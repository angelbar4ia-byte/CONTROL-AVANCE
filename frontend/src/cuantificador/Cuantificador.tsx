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
  getNotasDePlanoApiV1PlanosPlanoIdNotasGetQueryKey,
  getTrazosDePlanoApiV1PlanosPlanoIdTrazosGetQueryKey,
  useArchivoDePlanoApiV1PlanosPlanoIdArchivoGet,
  useEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGet,
  useListarPlanosApiV1ObrasObraIdPlanosGet,
  useNotasDePlanoApiV1PlanosPlanoIdNotasGet,
  useTrazosDePlanoApiV1PlanosPlanoIdTrazosGet,
} from '@/api/generado/cuantificacion/cuantificacion';
import type {
  ActividadRespuesta,
  ArchivoDePlanoRespuesta,
  NodoCuantificadoRespuesta,
  NodoPrototipoRespuesta,
  NotaPlanoDetalleRespuesta,
  PlanoDetalleRespuesta,
  TrazoRespuesta,
  TrazosDePlanoRespuesta,
} from '@/api/generado/modelo';
import { useListarObrasApiV1ObrasGet } from '@/api/generado/obras/obras';
import { useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet } from '@/api/generado/proyectos/proyectos';
import { useActividadesDeObraApiV1ObrasObraIdActividadesGet } from '@/api/generado/torre/torre';
import { queryClient } from '@/app/queryClient';
import { useSesion } from '@/app/sesion';
import { fmtFecha, fmtNum } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { SelectorObra } from '@/lib/SelectorObra';
import { AltaNota } from './AltaNota';
import { AltaPlano } from './AltaPlano';
import { AltaTrazo, type NodoDePrototipo } from './AltaTrazo';
import { ReemplazarEnlace } from './ReemplazarEnlace';
import { Visor, type NotaVisible, type Seleccion, type TrazoVisible } from './Visor';
import {
  trazoCompleto,
  type Herramienta,
  type HerramientaDeTrazo,
  type Punto,
} from './geometria';
import { useImagenDePdf } from './pdf';
import { etiquetaMedida } from './reglas';

const HERRAMIENTAS: readonly { readonly clave: Herramienta; readonly etiqueta: string }[] = [
  { clave: 'seleccionar', etiqueta: 'Seleccionar' },
  { clave: 'poligono', etiqueta: 'Polígono' },
  { clave: 'linea', etiqueta: 'Línea' },
  { clave: 'punto', etiqueta: 'Punto' },
];

/** Anotar el plano es solo de Residente y Supervisor (MODELO.md §1b); el
 *  servidor lo impone con 403, esto solo evita ofrecer un botón que fallaría. */
const HERRAMIENTA_NOTA = { clave: 'nota', etiqueta: 'Nota' } as const;

const ES_IMAGEN = /\.(png|jpe?g|webp)$/i;
const ES_PDF = /\.pdf$/i;

function etiquetaActividad(a: ActividadRespuesta | undefined, id: string): string {
  if (!a) return id.slice(0, 8);
  const donde = [a.nivel_clave, a.etapa_clave].filter(Boolean).join(' · ');
  const que = a.concepto_clave ?? a.descripcion ?? 'Actividad';
  return donde ? `${que} — ${donde}` : String(que);
}

export default function Cuantificador() {
  const { sesion } = useSesion();
  const puedeAnotar = sesion?.rol === 'residente' || sesion?.rol === 'supervisor';
  const puedeEnlazarPrototipo = sesion?.rol === 'control_obra' || sesion?.rol === 'super_intendente';
  const [obraId, setObraId] = useState('');
  const [planoElegido, setPlanoElegido] = useState('');
  const [herramienta, setHerramienta] = useState<Herramienta>('seleccionar');
  const [borrador, setBorrador] = useState<readonly Punto[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [subiendoPlano, setSubiendoPlano] = useState(false);
  const [seleccion, setSeleccion] = useState<Seleccion | null>(null);
  const [notaPunto, setNotaPunto] = useState<Punto | null>(null);
  const [reemplazando, setReemplazando] = useState<string | null>(null);
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
    setSeleccion(null);
    setHerramienta('seleccionar');
  }, [obraId]);
  useEffect(() => {
    if (planoElegido === '' && listaDePlanos[0]) setPlanoElegido(listaDePlanos[0].id);
  }, [listaDePlanos, planoElegido]);

  const plano = listaDePlanos.find((p) => p.id === planoElegido);
  const esImagen = plano !== undefined && ES_IMAGEN.test(plano.archivo_url);
  const esPdf = plano !== undefined && ES_PDF.test(plano.archivo_url);

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

  // Los nodos del prototipo de la obra, solo para quien puede enlazarlos. Se
  // ofrecen los conceptos: son los que llevan cantidad (`prototipo_nodo.cantidad`).
  const obras = useListarObrasApiV1ObrasGet();
  const prototipoId = obras.data?.find((o) => o.id === obraId)?.prototipo_id ?? '';
  const nodosConsulta = useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet<
    NodoPrototipoRespuesta[],
    ErrorApi
  >(prototipoId, { query: { enabled: puedeEnlazarPrototipo && prototipoId !== '' } });
  const nodosDePrototipo = useMemo<NodoDePrototipo[]>(
    () =>
      (nodosConsulta.data ?? [])
        .filter((n) => n.tipo === 'concepto')
        .map((n) => ({ id: n.id, etiqueta: [n.clave, n.nombre].filter(Boolean).join(' · ') })),
    [nodosConsulta.data],
  );

  // La URL firmada solo se pide si el archivo es algo que el visor sabe pintar:
  // una imagen, o un PDF que se rasteriza (`useImagenDePdf`). Una caducidad corta no es problema: se carga una vez al abrir el
  // plano y la imagen queda en memoria del navegador.
  const archivo = useArchivoDePlanoApiV1PlanosPlanoIdArchivoGet<
    ArchivoDePlanoRespuesta,
    ErrorApi
  >(planoElegido, { query: { enabled: planoElegido !== '' && (esImagen || esPdf), retry: false, staleTime: 5 * 60_000 } });

  const pdf = useImagenDePdf(esPdf ? (archivo.data?.url ?? null) : null);
  const fondoUrl = esImagen ? (archivo.data?.url ?? null) : esPdf ? pdf.url : null;

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
  const notasConsulta = useNotasDePlanoApiV1PlanosPlanoIdNotasGet<
    NotaPlanoDetalleRespuesta[],
    ErrorApi
  >(planoElegido, { query: { enabled: planoElegido !== '' } });
  const listaDeNotas = useMemo(() => notasConsulta.data ?? [], [notasConsulta.data]);
  const notasVisibles = useMemo<NotaVisible[]>(
    () =>
      listaDeNotas.flatMap((n) => {
        const c = n.ubicacion.coordinates;
        return Array.isArray(c) && typeof c[0] === 'number' && typeof c[1] === 'number'
          ? [{ id: n.id, punto: [c[0], c[1]] as Punto, texto: n.texto, porRevisar: n.por_revisar }]
          : [];
      }),
    [listaDeNotas],
  );

  const seleccionado =
    seleccion?.tipo === 'trazo' ? (features.find((f) => f.id === seleccion.id) ?? null) : null;
  const notaElegida =
    seleccion?.tipo === 'nota' ? (listaDeNotas.find((n) => n.id === seleccion.id) ?? null) : null;
  const enlaceAReemplazar = seleccionado?.properties.enlaces.find((e) => e.enlace_id === reemplazando);

  const forma: HerramientaDeTrazo | null =
    herramienta === 'seleccionar' || herramienta === 'nota' ? null : herramienta;

  function cambiarHerramienta(nueva: Herramienta) {
    setHerramienta(nueva);
    setBorrador([]);
    setAviso(null);
    if (nueva !== 'seleccionar') setSeleccion(null);
  }

  function alPunto(p: Punto) {
    setAviso(null);
    if (herramienta === 'nota') {
      setNotaPunto(p);
      return;
    }
    if (!forma) return;
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
    if (!forma || guardando || subiendoPlano || notaPunto !== null || reemplazando !== null) return;
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
  }, [forma, borrador, guardando, subiendoPlano, notaPunto, reemplazando]);

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
  const porNodoDePrototipo = useMemo(
    () => new Map(nodosDePrototipo.map((n) => [n.id, n.etiqueta])),
    [nodosDePrototipo],
  );
  /** Nombre legible del nodo de un enlace, sea actividad o nodo de prototipo. */
  const nombreDeNodo = (tipo: string, id: string): string =>
    tipo === 'prototipo_nodo'
      ? (porNodoDePrototipo.get(id) ?? `Nodo de prototipo ${id.slice(0, 8)}`)
      : etiquetaActividad(porActividad.get(id), id);
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
              setSeleccion(null);
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
              {(puedeAnotar ? [...HERRAMIENTAS, HERRAMIENTA_NOTA] : HERRAMIENTAS).map((h) => (
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
            {plano !== undefined && !esImagen && !esPdf && (
              <div className="text-mute text-xs">
                Este plano no es una imagen (PNG, JPG o WebP) ni un PDF: se traza sobre una
                rejilla en blanco.
              </div>
            )}
            {(esImagen || esPdf) && archivo.error && (
              <div className="text-mute text-xs">
                No se pudo cargar el archivo del plano ({archivo.error.message}). Los trazos se
                muestran sobre una rejilla en blanco.
              </div>
            )}
            {esPdf && pdf.cargando && (
              <div className="text-mute text-xs" role="status">
                Preparando la hoja del PDF…
              </div>
            )}
            {esPdf && pdf.error && (
              <div className="text-mute text-xs">
                No se pudo dibujar el PDF ({pdf.error}). Los trazos se muestran sobre una
                rejilla en blanco.
              </div>
            )}

            <Visor
              claveDePlano={planoElegido}
              fondoUrl={fondoUrl}
              trazos={trazosVisibles}
              notas={notasVisibles}
              seleccion={seleccion}
              herramienta={herramienta}
              borrador={borrador}
              onPunto={alPunto}
              onSeleccionar={setSeleccion}
            />
          </div>

          <aside className="cuant__lateral col gap-12">
            <div className="card">
              <div className="card__header">
                <div className="card__title">
                  {seleccionado ? 'Trazo elegido' : notaElegida ? 'Nota elegida' : 'Trazos del plano'}
                </div>
              </div>
              <div className="card__body col">
                {notaElegida ? (
                  <>
                    <div className="text-sm" style={{ whiteSpace: 'pre-wrap' }}>
                      {notaElegida.texto}
                    </div>
                    <div className="text-mute text-xs">
                      {fmtFecha(notaElegida.created_at)}
                      {notaElegida.actividad_id &&
                        ` · ${etiquetaActividad(porActividad.get(notaElegida.actividad_id), notaElegida.actividad_id)}`}
                    </div>
                    {notaElegida.por_revisar && (
                      <span className="badge badge--warn">
                        Hecha sobre una versión anterior: el lugar pudo moverse
                      </span>
                    )}
                    <div className="text-mute text-xs">Una nota no suma cantidad.</div>
                  </>
                ) : seleccionado ? (
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
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {seleccionado.properties.enlaces.map((e) => (
                            <tr key={e.enlace_id} style={e.vigente ? undefined : { opacity: 0.5 }}>
                              <td>
                                {nombreDeNodo(e.tipo_nodo, e.nodo_id)}
                                {!e.vigente && <span className="text-mute"> · reemplazado</span>}
                              </td>
                              <td>
                                {etiquetaMedida(e.medida)} × {fmtNum(e.factor)}
                              </td>
                              <td className="is-num">{fmtNum(e.cantidad)}</td>
                              <td>
                                {e.vigente && (
                                  <button
                                    type="button"
                                    className="btn btn--ghost btn--sm"
                                    onClick={() => setReemplazando(e.enlace_id)}
                                  >
                                    Reemplazar
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </>
                ) : (
                  <div className="text-mute text-sm">
                    {features.length === 0 && listaDeNotas.length === 0
                      ? 'Este plano aún no tiene trazos ni notas.'
                      : `${features.length} ${features.length === 1 ? 'trazo' : 'trazos'} y ${listaDeNotas.length} ${listaDeNotas.length === 1 ? 'nota' : 'notas'}. Elige uno con la herramienta Seleccionar.`}
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
                              {n.descripcion ?? nombreDeNodo(n.tipo_nodo, n.nodo_id)}
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
          nodosDePrototipo={puedeEnlazarPrototipo ? nodosDePrototipo : null}
          onCerrar={() => {
            setGuardando(false);
            // Un punto se captura con un solo clic: si se cancela el cajón no
            // hay nada que seguir editando, se descarta.
            if (forma === 'punto') setBorrador([]);
          }}
          onGuardado={alGuardar}
        />
      )}

      {notaPunto !== null && plano && (
        <AltaNota
          planoId={plano.id}
          versionPlano={plano.version}
          punto={notaPunto}
          actividades={actividades}
          onCerrar={() => setNotaPunto(null)}
          onGuardada={() => {
            setNotaPunto(null);
            setAviso('Nota guardada.');
            void queryClient.invalidateQueries({
              queryKey: getNotasDePlanoApiV1PlanosPlanoIdNotasGetQueryKey(planoElegido),
            });
          }}
        />
      )}

      {enlaceAReemplazar && seleccionado && (
        <ReemplazarEnlace
          enlace={enlaceAReemplazar}
          candidatos={features.filter((f) => f.id !== seleccionado.id)}
          nombreDelNodo={nombreDeNodo(enlaceAReemplazar.tipo_nodo, enlaceAReemplazar.nodo_id)}
          onCerrar={() => setReemplazando(null)}
          onReemplazado={() => {
            setReemplazando(null);
            setAviso('Enlace reemplazado: el anterior queda como evidencia y ya no suma.');
            void queryClient.invalidateQueries({
              queryKey: getTrazosDePlanoApiV1PlanosPlanoIdTrazosGetQueryKey(planoElegido),
            });
            void queryClient.invalidateQueries({
              queryKey: getEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGetQueryKey(obraId),
            });
          }}
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
