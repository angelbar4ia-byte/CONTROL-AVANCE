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

import { PanelLeft, PanelRight, Upload } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGetQueryKey,
  getListarPlanosApiV1ObrasObraIdPlanosGetQueryKey,
  getNotasDePlanoApiV1PlanosPlanoIdNotasGetQueryKey,
  getTrazosDePlanoApiV1PlanosPlanoIdTrazosGetQueryKey,
  useAgregarHuecoApiV1TrazosTrazoIdHuecosPost,
  useAprobarTrazoApiV1TrazosTrazoIdAprobarPost,
  useArchivoDePlanoApiV1PlanosPlanoIdArchivoGet,
  useEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGet,
  useListarPlanosApiV1ObrasObraIdPlanosGet,
  useNotasDePlanoApiV1PlanosPlanoIdNotasGet,
  useTrazosDePlanoApiV1PlanosPlanoIdTrazosGet,
} from '@/api/generado/cuantificacion/cuantificacion';
import type {
  ActividadRespuesta,
  ArchivoDePlanoRespuesta,
  EscalaRespuesta,
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
import { useSearchParams } from 'react-router-dom';
import { fmtFecha, fmtNum } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { SelectorObra } from '@/lib/SelectorObra';
import { AltaNota } from './AltaNota';
import { AltaPlano } from './AltaPlano';
import { AltaTrazo, type NodoDePrototipo } from './AltaTrazo';
import { CalibrarEscala } from './CalibrarEscala';
import { useAjuste, useAnchoAjustable } from '@/lib/useAjuste';
import { SeparadorDeAncho } from './SeparadorDeAncho';
import { arbolDeCuantificacion, trazosDeConceptos } from './arbol';
import { ArbolPresupuesto } from './ArbolPresupuesto';
import { BarraDeHerramientas, type ClaveDeInterruptor, type Interruptor } from './BarraDeHerramientas';
import { CuadroDeDatos } from './CuadroDeDatos';
import { cotasDe, etiquetasDeMedidas, sinCierre } from './etiquetas';
import {
  bandaDeLinea,
  poligonoDeForma,
  normalizarContorno,
  NOMBRE_DE_FORMA,
  type Alineacion,
  type Forma,
} from './formas';
import { OpcionesDeHerramienta } from './OpcionesDeHerramienta';
import { PanelVolumen } from './PanelVolumen';
import { resumenDePantalla, type TrazoParaResumen } from './resumen';
import { NuevaObra } from './NuevaObra';
import { ReemplazarEnlace } from './ReemplazarEnlace';
import { Visor, type NotaVisible, type Seleccion, type TrazoVisible } from './Visor';
import {
  PUNTOS_MINIMOS_DE_HUECO,
  aWkt,
  areaDeGeometria,
  partesDe,
  puntosDe,
  trazoCompleto,
  type Herramienta,
  type HerramientaDeTrazo,
  type Punto,
} from './geometria';
import { useImagenDePdf } from './pdf';
import { etiquetaMedida } from './reglas';

const HERRAMIENTAS: readonly Herramienta[] = [
  'seleccionar',
  'mano',
  'zoom',
  'poligono',
  'linea',
  'punto',
  'hueco',
  'escala',
];

/** Anotar el plano es solo de Residente y Supervisor (MODELO.md §1b); el
 *  servidor lo impone con 403, esto solo evita ofrecer un botón que fallaría. */
const HERRAMIENTA_NOTA: Herramienta = 'nota';

/** Atajo de teclado de cada herramienta de la barra. */
const ATAJOS: Readonly<Record<string, Herramienta>> = {
  v: 'seleccionar',
  h: 'mano',
  z: 'zoom',
  u: 'hueco',
  p: 'poligono',
  l: 'linea',
  o: 'punto',
  e: 'escala',
  n: 'nota',
};

const ES_IMAGEN = /\.(png|jpe?g|webp)$/i;
const ES_PDF = /\.pdf$/i;

function etiquetaActividad(a: ActividadRespuesta | undefined, id: string): string {
  if (!a) return id.slice(0, 8);
  const donde = [a.nivel_clave, a.etapa_clave].filter(Boolean).join(' · ');
  const que = a.concepto_clave ?? a.descripcion ?? 'Actividad';
  return donde ? `${que} — ${donde}` : String(que);
}

interface PropsEspacio {
  readonly obraId: string;
  /** Plano con el que abre; si no se manda, el primero de la obra. */
  readonly planoInicial?: string;
  /**
   * La actividad sobre la que se trabaja (la herramienta puntual, D-532): su
   * renglón queda a la vista y se actualiza al guardar cada trazo, y el
   * formulario de enlaces la trae ya elegida.
   */
  readonly actividadFocoId?: string;
  /** Una sola columna y un visor más bajo: es lo que cabe en la ventana flotante. */
  readonly compacto?: boolean;
  /** Avisa qué plano se está viendo, para que «Abrir en el módulo» lleve el mismo. */
  readonly onPlanoCambiado?: (planoId: string) => void;
  /** Lo que va al inicio de la barra de filtros (el módulo pone aquí el selector de obra). */
  readonly cabecera?: ReactNode;
}

/**
 * El motor del cuantificador: plano, herramientas, trazos y estado de la obra.
 * Lo usan las dos entradas (D-532): el módulo (`Cuantificador`) y la ventana
 * flotante (`VentanaCuantificador`). Es **el mismo motor y los mismos datos**:
 * lo que se traza en una se ve en la otra porque las dos leen y escriben lo
 * mismo, sin estado propio de la entrada.
 *
 * La obra es un parámetro y no un estado: cambiar de obra es montar otro
 * `EspacioDeTrazo` (`key={obraId}`), lo que limpia solo todo lo que dependía
 * de la anterior.
 */
export function EspacioDeTrazo({
  obraId,
  planoInicial,
  actividadFocoId,
  compacto = false,
  onPlanoCambiado,
  cabecera,
}: PropsEspacio) {
  const { sesion } = useSesion();
  const puedeAnotar = sesion?.rol === 'residente' || sesion?.rol === 'supervisor';
  /** `aprobar_trazo` es solo de Control de obra (MODELO.md §1b); el servidor lo impone con 403. */
  const puedeAprobar = sesion?.rol === 'control_obra';
  const puedeEnlazarPrototipo = sesion?.rol === 'control_obra' || sesion?.rol === 'super_intendente';
  const [planoElegido, setPlanoElegido] = useState(planoInicial ?? '');
  const [herramienta, setHerramienta] = useState<Herramienta>('seleccionar');
  const [borrador, setBorrador] = useState<readonly Punto[]>([]);
  // El hueco que se está dibujando sobre el área elegida (la ventana de un muro, el cubo de una
  // escalera). Se descuenta del área al cerrarlo con Enter.
  const [huecoEnCurso, setHuecoEnCurso] = useState<readonly Punto[]>([]);
  // Opciones de las herramientas: el grosor y la alineación de una línea, la forma de un punto.
  const [grosorM, setGrosorM] = useState<number | null>(null);
  const [alineacion, setAlineacion] = useState<Alineacion>('centro');
  const [formaPunto, setFormaPunto] = useState<Forma | null>(null);
  /** La forma con la que se está guardando el trazo (solo cuando nació de un punto con forma). */
  const [formaEstampada, setFormaEstampada] = useState<Forma | null>(null);
  const [cursor, setCursor] = useState<Punto | null>(null);
  const [mostrarMedidas, setMostrarMedidas] = useState(false);
  const [mostrarCotas, setMostrarCotas] = useState(false);
  const [datosAbiertos, setDatosAbiertos] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [subiendoPlano, setSubiendoPlano] = useState(false);
  const [seleccion, setSeleccion] = useState<Seleccion | null>(null);
  const [notaPunto, setNotaPunto] = useState<Punto | null>(null);
  const [reemplazando, setReemplazando] = useState<string | null>(null);
  const [calibrando, setCalibrando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [elegidos, setElegidos] = useState<ReadonlySet<string>>(new Set());
  const [soloElegidos, setSoloElegidos] = useState(false);
  const [volumenAbierto, setVolumenAbierto] = useState(false);
  const [arbolAbierto, setArbolAbierto] = useAjuste('arbol', !compacto);
  const [detalleAbierto, setDetalleAbierto] = useAjuste('detalle', !compacto);
  // El ancho de los dos paneles laterales se ajusta arrastrando su borde y se recuerda.
  const anchoArbol = useAnchoAjustable('ancho-arbol', 300, 200, 560);
  const anchoDetalle = useAnchoAjustable('ancho-detalle', 320, 240, 640);

  const planos = useListarPlanosApiV1ObrasObraIdPlanosGet<
    PlanoDetalleRespuesta[],
    ErrorApi
  >(obraId, { query: { enabled: obraId !== '' } });
  const listaDePlanos = useMemo(() => planos.data ?? [], [planos.data]);

  // Al llegar la lista, se abre el primer plano para no dejar al usuario frente
  // a un vacío.
  useEffect(() => {
    if (planoElegido === '' && listaDePlanos[0]) setPlanoElegido(listaDePlanos[0].id);
  }, [listaDePlanos, planoElegido]);
  useEffect(() => {
    if (planoElegido !== '') onPlanoCambiado?.(planoElegido);
  }, [planoElegido, onPlanoCambiado]);

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
  // «Solo los trazos de los conceptos elegidos»: sin conceptos elegidos no hay nada
  // que filtrar, y se ve todo.
  const escalaDelPlano = plano?.escala_m_por_unidad != null ? Number(plano.escala_m_por_unidad) : null;
  /** Unidades de plano por metro: lo que convierte un grosor o un tamaño en metros a coordenadas. */
  const unidadesPorMetro = escalaDelPlano !== null && escalaDelPlano > 0 ? 1 / escalaDelPlano : 1;
  const filtrando = soloElegidos && elegidos.size > 0;
  const featuresVisibles = useMemo(
    () => (filtrando ? trazosDeConceptos(features, elegidos) : features),
    [features, elegidos, filtrando],
  );
  const trazosVisibles = useMemo<TrazoVisible[]>(
    () =>
      featuresVisibles.map((f) => ({
        id: f.id,
        geometry: f.geometry,
        porRevisar: f.properties.por_revisar,
        aprobado: f.properties.aprobado_en != null,
        // El cuerpo de una línea con grosor (un muro), pintado con su alineación.
        banda:
          f.properties.grosor_m != null && f.properties.alineacion
            ? bandaDeLinea(
                puntosDe(f.geometry),
                Number(f.properties.grosor_m) * unidadesPorMetro,
                f.properties.alineacion,
              )
            : undefined,
      })),
    [featuresVisibles, unidadesPorMetro],
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

  const aprobar = useAprobarTrazoApiV1TrazosTrazoIdAprobarPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setAviso('Trazo aprobado.');
        void queryClient.invalidateQueries({
          queryKey: getTrazosDePlanoApiV1PlanosPlanoIdTrazosGetQueryKey(planoElegido),
        });
      },
      onError: (err) => setAviso(`No se pudo aprobar el trazo: ${err.message}`),
    },
  });

  const forma: HerramientaDeTrazo | null =
    herramienta === 'poligono' || herramienta === 'linea' || herramienta === 'punto'
      ? herramienta
      : null;

  /** Un hueco solo se abre sobre un área (un polígono trazado, no una línea con grosor). */
  const areaElegida =
    seleccionado !== null && areaDeGeometria(seleccionado.geometry) > 0 ? seleccionado : null;

  const agregarHueco = useAgregarHuecoApiV1TrazosTrazoIdHuecosPost<ErrorApi>();

  function limpiarDibujo() {
    setBorrador([]);
    setHuecoEnCurso([]);
    setFormaEstampada(null);
  }

  function cambiarHerramienta(nueva: Herramienta) {
    if (nueva === 'hueco' && areaElegida === null) {
      setAviso('Para abrir un hueco, primero elige el área con la herramienta Seleccionar.');
      return;
    }
    setHerramienta(nueva);
    limpiarDibujo();
    setAviso(null);
    // Moverse, acercar y abrir un hueco no sueltan lo elegido: el hueco se abre sobre ello.
    if (nueva !== 'seleccionar' && nueva !== 'mano' && nueva !== 'zoom' && nueva !== 'hueco') {
      setSeleccion(null);
    }
  }

  function alPunto(p: Punto) {
    setAviso(null);
    if (herramienta === 'nota') {
      setNotaPunto(p);
      return;
    }
    if (herramienta === 'escala') {
      // Dos puntos de referencia: al segundo se pide la distancia real. Un
      // tercer clic empieza de nuevo.
      const siguiente = borrador.length >= 2 ? [p] : [...borrador, p];
      setBorrador(siguiente);
      if (siguiente.length === 2) setCalibrando(true);
      return;
    }
    if (herramienta === 'hueco') {
      setHuecoEnCurso((actual) => [...actual, p]);
      return;
    }
    if (!forma) return;
    if (forma === 'punto') {
      if (formaPunto !== null) {
        // Un punto con forma: el polígono de la forma, centrado donde se hizo clic.
        setBorrador(poligonoDeForma(p, formaPunto, unidadesPorMetro));
        setFormaEstampada(formaPunto);
      } else {
        setBorrador([p]);
      }
      setGuardando(true);
      return;
    }
    setBorrador((actual) => [...actual, p]);
  }

  function terminar() {
    if (forma && trazoCompleto(forma, borrador)) setGuardando(true);
  }

  /** Cierra el hueco en curso: lo manda al servidor, que lo resta del área y recalcula. */
  async function cerrarHueco() {
    if (!areaElegida || huecoEnCurso.length < PUNTOS_MINIMOS_DE_HUECO) return;
    try {
      const r = await agregarHueco.mutateAsync({
        trazoId: areaElegida.id,
        data: { geometria_wkt: aWkt('poligono', huecoEnCurso) },
      });
      setHuecoEnCurso([]);
      const total = r.recalculos[0]?.cantidad_total;
      setAviso(
        total === undefined
          ? 'Hueco abierto: el área ya lo descuenta.'
          : `Hueco abierto. Cantidad medida del nodo: ${fmtNum(total)}.`,
      );
      void queryClient.invalidateQueries({
        queryKey: getTrazosDePlanoApiV1PlanosPlanoIdTrazosGetQueryKey(planoElegido),
      });
      void queryClient.invalidateQueries({
        queryKey: getEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGetQueryKey(obraId),
      });
    } catch (err) {
      setAviso(err instanceof Error ? err.message : 'No se pudo abrir el hueco.');
    }
  }

  // Atajos mientras se dibuja. El efecto se rearma con cada cambio del borrador:
  // los manejadores leen el estado de este render, no uno viejo.
  useEffect(() => {
    const dibujando = forma !== null || herramienta === 'hueco';
    if (!dibujando || guardando || subiendoPlano || notaPunto !== null || reemplazando !== null) return;
    function alTeclear(e: KeyboardEvent) {
      const destino = e.target as HTMLElement | null;
      if (destino && /^(INPUT|SELECT|TEXTAREA)$/.test(destino.tagName)) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        if (herramienta === 'hueco') void cerrarHueco();
        else if (forma && trazoCompleto(forma, borrador)) setGuardando(true);
      } else if (e.key === 'Backspace') {
        e.preventDefault();
        if (herramienta === 'hueco') setHuecoEnCurso((actual) => actual.slice(0, -1));
        else setBorrador((actual) => actual.slice(0, -1));
      } else if (e.key === 'Escape') {
        limpiarDibujo();
      }
    }
    window.addEventListener('keydown', alTeclear);
    return () => window.removeEventListener('keydown', alTeclear);
    // `cerrarHueco` y `limpiarDibujo` leen estado del render: se rearma con él.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forma, herramienta, borrador, huecoEnCurso, guardando, subiendoPlano, notaPunto, reemplazando, areaElegida]);

  function alGuardar(resultado: TrazoRespuesta) {
    setGuardando(false);
    limpiarDibujo();
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
  const arbol = useMemo(
    () => arbolDeCuantificacion(actividades, estado.data ?? []),
    [actividades, estado.data],
  );

  const filaDeFoco = actividadFocoId
    ? (estado.data ?? []).find((n) => n.nodo_id === actividadFocoId)
    : undefined;
  const actividadDeFoco = actividadFocoId ? porActividad.get(actividadFocoId) : undefined;

  const herramientasDisponibles: readonly Herramienta[] = puedeAnotar
    ? [...HERRAMIENTAS, HERRAMIENTA_NOTA]
    : HERRAMIENTAS;

  function alternar(clave: ClaveDeInterruptor) {
    if (clave === 'medidas') setMostrarMedidas(!mostrarMedidas);
    else if (clave === 'cotas') setMostrarCotas(!mostrarCotas);
    else if (clave === 'datos') setDatosAbiertos(!datosAbiertos);
    else if (clave === 'volumen') abrirVolumen();
    else if (elegidos.size > 0 || soloElegidos) setSoloElegidos(!soloElegidos);
  }

  const interruptores: readonly Interruptor[] = [
    { clave: 'medidas', activo: mostrarMedidas, atajo: 'M', descripcion: 'Mostrar medidas: puntos numerados, áreas y huecos (M)' },
    { clave: 'cotas', activo: mostrarCotas, atajo: 'C', descripcion: 'Cota: la longitud de cada tramo (C)' },
    {
      clave: 'soloElegidos',
      activo: soloElegidos,
      deshabilitado: elegidos.size === 0 && !soloElegidos,
      descripcion:
        elegidos.size > 0 || soloElegidos
          ? 'Ver solo los trazos de los conceptos elegidos en el árbol'
          : 'Elige conceptos en el árbol para ver solo sus trazos',
    },
    { clave: 'volumen', activo: volumenAbierto, descripcion: 'Calcular volumen del trazo elegido' },
    { clave: 'datos', activo: datosAbiertos, atajo: 'D', descripcion: 'Cuadro de datos: resumen de las medidas en pantalla (D)' },
  ];

  const etiquetas = useMemo(
    () =>
      mostrarMedidas
        ? featuresVisibles.flatMap((f) =>
            etiquetasDeMedidas(
              f.geometry,
              escalaDelPlano,
              f.properties.grosor_m != null ? Number(f.properties.grosor_m) : null,
            ),
          )
        : [],
    [mostrarMedidas, featuresVisibles, escalaDelPlano],
  );
  const cotas = useMemo(
    () => (mostrarCotas ? featuresVisibles.flatMap((f) => cotasDe(f.geometry, escalaDelPlano)) : []),
    [mostrarCotas, featuresVisibles, escalaDelPlano],
  );
  const resumen = useMemo(
    () => resumenDePantalla(featuresVisibles as unknown as readonly TrazoParaResumen[], escalaDelPlano),
    [featuresVisibles, escalaDelPlano],
  );
  const bandaEnCurso =
    forma === 'linea' && grosorM !== null && borrador.length >= 2
      ? bandaDeLinea(borrador, grosorM * unidadesPorMetro, alineacion)
      : [];
  const fantasma =
    forma === 'punto' && formaPunto !== null && cursor !== null
      ? poligonoDeForma(cursor, formaPunto, unidadesPorMetro)
      : [];
  // El contorno del área elegida, para estampar su forma en otro lugar.
  const contornoElegido = (() => {
    if (!areaElegida) return null;
    const exterior = partesDe(areaElegida.geometry).find((p) => p.tipo === 'anillo' && !p.hueco);
    return exterior ? normalizarContorno(sinCierre(exterior.puntos)) : null;
  })();

  function elegirConceptos(ids: readonly string[], marcar: boolean) {
    const siguiente = new Set(elegidos);
    for (const id of ids) {
      if (marcar) siguiente.add(id);
      else siguiente.delete(id);
    }
    setElegidos(siguiente);
    // Sin conceptos elegidos el filtro no tiene nada que mostrar: se apaga solo.
    if (siguiente.size === 0) setSoloElegidos(false);
  }

  function abrirVolumen() {
    // Calcular un volumen es mirar un trazo, no dibujar: se vuelve a Seleccionar.
    if (!volumenAbierto) cambiarHerramienta('seleccionar');
    setVolumenAbierto(!volumenAbierto);
  }

  // Atajos de herramienta (V, P, L, O, E, N). Se ignoran con un campo enfocado o un
  // cajón abierto, igual que los del dibujo: escribir «0.5» no debe cambiar de herramienta.
  const hayCajon = guardando || subiendoPlano || notaPunto !== null || reemplazando !== null || calibrando;
  useEffect(() => {
    if (hayCajon) return;
    function alTeclear(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const destino = e.target as HTMLElement | null;
      if (destino && /^(INPUT|SELECT|TEXTAREA)$/.test(destino.tagName)) return;
      if (destino?.isContentEditable) return;
      const tecla = e.key.toLowerCase();
      if (tecla === 'm') return setMostrarMedidas((v) => !v);
      if (tecla === 'c') return setMostrarCotas((v) => !v);
      if (tecla === 'd') return setDatosAbiertos((v) => !v);
      const h = ATAJOS[tecla];
      if (h && herramientasDisponibles.includes(h)) cambiarHerramienta(h);
    }
    window.addEventListener('keydown', alTeclear);
    return () => window.removeEventListener('keydown', alTeclear);
    // `cambiarHerramienta` lee estado del render: se rearma con él.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hayCajon, puedeAnotar, borrador, areaElegida, herramienta, mostrarMedidas, mostrarCotas, datosAbiertos]);

  const nombreDelTrazo = seleccionado
    ? (seleccionado.properties.enlaces.find((e) => e.vigente)
        ? nombreDeNodo(
            seleccionado.properties.enlaces.find((e) => e.vigente)!.tipo_nodo,
            seleccionado.properties.enlaces.find((e) => e.vigente)!.nodo_id,
          )
        : (seleccionado.properties.capa ?? 'Trazo sin enlace'))
    : '';

  const detalle = (
    <aside className="estacion__detalle" aria-label="Detalle">
      <div className="estacion__titulo">
        {seleccionado ? 'Trazo elegido' : notaElegida ? 'Nota elegida' : 'Trazos del plano'}
      </div>
      <div className="estacion__detalle-cuerpo col">
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
            <div className="row">
              {seleccionado.properties.aprobado_en ? (
                <span className="badge badge--ok">
                  Aprobado · {fmtFecha(seleccionado.properties.aprobado_en)}
                </span>
              ) : (
                <span className="badge badge--outline">Sin aprobar</span>
              )}
              {puedeAprobar && !seleccionado.properties.aprobado_en && (
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={aprobar.isPending}
                  onClick={() => aprobar.mutate({ trazoId: seleccionado.id })}
                >
                  Aprobar trazo
                </button>
              )}
            </div>
            {puedeAprobar && !seleccionado.properties.aprobado_en && (
              <div className="text-mute text-xs">
                Aprobar deja constancia de la revisión; no cambia la cantidad: el trazo
                cuenta desde que se guarda.
              </div>
            )}
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
    </aside>
  );

  const panelDelArbol = (
    <aside className="estacion__arbol" aria-label="Presupuesto">
      <div className="estacion__titulo">
        Presupuesto
        <span className="estacion__subtitulo">
          {elegidos.size === 0
            ? 'Medido contra la base'
            : `${elegidos.size} ${elegidos.size === 1 ? 'elegido' : 'elegidos'}`}
        </span>
        {elegidos.size > 0 && (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            style={{ marginLeft: 'auto' }}
            onClick={() => {
              setElegidos(new Set());
              setSoloElegidos(false);
            }}
          >
            Limpiar
          </button>
        )}
      </div>
      {estado.error ? (
        <div style={{ padding: 8 }}>
          <ErrorBanner mensaje={estado.error.message} />
        </div>
      ) : arbol.length === 0 ? (
        <div className="text-mute text-sm" style={{ padding: 10 }}>
          La obra todavía no tiene actividades: genérala para empezar a medir.
        </div>
      ) : (
        <ArbolPresupuesto
          arbol={arbol}
          elegidos={elegidos}
          onElegir={elegirConceptos}
          actividadFocoId={actividadFocoId}
        />
      )}
    </aside>
  );

  const claseEspacio = [
    'estacion',
    compacto && 'estacion--compacta',
    arbolAbierto && 'tiene-arbol',
    detalleAbierto && 'tiene-detalle',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={claseEspacio}>
      <div className="estacion__cabecera">
        {cabecera}
        <div className="estacion__plano">
          <label className="sr-only" htmlFor="cuant-plano">
            Plano
          </label>
          <select
            id="cuant-plano"
            className="select"
            value={planoElegido}
            onChange={(e) => {
              setPlanoElegido(e.target.value);
              setBorrador([]);
              setSeleccion(null);
            }}
          >
            <option value="">Sin planos</option>
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
          className="btn-icono"
          aria-label="Subir plano"
          title="Subir plano"
          onClick={() => setSubiendoPlano(true)}
        >
          <Upload size={16} aria-hidden />
        </button>
        <span className="estacion__relleno" />
        <button
          type="button"
          className={arbolAbierto ? 'btn-icono is-activo' : 'btn-icono'}
          aria-label="Mostrar u ocultar el árbol del presupuesto"
          aria-pressed={arbolAbierto}
          title="Árbol del presupuesto"
          onClick={() => setArbolAbierto(!arbolAbierto)}
        >
          <PanelLeft size={16} aria-hidden />
        </button>
        <button
          type="button"
          className={detalleAbierto ? 'btn-icono is-activo' : 'btn-icono'}
          aria-label="Mostrar u ocultar el detalle del trazo"
          aria-pressed={detalleAbierto}
          title="Detalle del trazo"
          onClick={() => setDetalleAbierto(!detalleAbierto)}
        >
          <PanelRight size={16} aria-hidden />
        </button>
      </div>

      {actividadFocoId && (
        <div className="cuant__renglon" data-testid="renglon-foco">
          <div>
            <div className="text-xs text-mute">Actividad</div>
            <div className="text-sm">
              <strong>{etiquetaActividad(actividadDeFoco, actividadFocoId)}</strong>
              {actividadDeFoco?.descripcion ? ` · ${actividadDeFoco.descripcion}` : ''}
            </div>
          </div>
          <dl className="cuant__cifras">
            <div>
              <dt>Base</dt>
              <dd>{fmtNum(filaDeFoco?.cant_base ?? actividadDeFoco?.cant_base)}</dd>
            </div>
            <div>
              <dt>Medido</dt>
              <dd data-testid="medido-foco">{filaDeFoco ? fmtNum(filaDeFoco.cantidad_medida) : '—'}</dd>
            </div>
            <div>
              <dt>Dif.</dt>
              <dd>{filaDeFoco ? fmtNum(filaDeFoco.diferencia) : '—'}</dd>
            </div>
          </dl>
        </div>
      )}

      <div
        className="estacion__cuerpo"
        style={
          {
            '--ancho-arbol': `${anchoArbol.ancho}px`,
            '--ancho-detalle': `${anchoDetalle.ancho}px`,
          } as React.CSSProperties
        }
      >
        {arbolAbierto && panelDelArbol}
        {arbolAbierto && !compacto && (
          <SeparadorDeAncho
            etiqueta="Ancho del árbol del presupuesto"
            lado="izquierda"
            ancho={anchoArbol.ancho}
            minimo={200}
            maximo={560}
            onCambio={anchoArbol.fijar}
            onSoltar={anchoArbol.recordar}
            onRestablecer={anchoArbol.restablecer}
          />
        )}

        <div className="estacion__lienzo">
          {plano === undefined ? (
            <div className="empty">
              <div className="empty-title">
                {planos.isLoading ? 'Cargando planos…' : 'Esta obra no tiene planos'}
              </div>
              {!planos.isLoading && (
                <div className="empty-sub">Sube una imagen del plano para empezar a trazar.</div>
              )}
            </div>
          ) : (
            <>
              <BarraDeHerramientas
                herramientas={herramientasDisponibles}
                activa={herramienta}
                onElegir={cambiarHerramienta}
                deshabilitadas={
                  areaElegida === null
                    ? { hueco: 'Para abrir un hueco, primero elige el área con Seleccionar' }
                    : {}
                }
                interruptores={interruptores}
                onAlternar={alternar}
                orientacion={compacto ? 'horizontal' : 'vertical'}
              />

              <div className="estacion__paneles">
                {(herramienta === 'linea' || herramienta === 'punto') && (
                  <OpcionesDeHerramienta
                    herramienta={herramienta}
                    grosorM={grosorM}
                    onGrosor={setGrosorM}
                    alineacion={alineacion}
                    onAlineacion={setAlineacion}
                    forma={formaPunto}
                    onForma={setFormaPunto}
                    contornoElegido={contornoElegido}
                  />
                )}
                {volumenAbierto && (
                  <PanelVolumen
                    key={seleccionado?.id ?? 'sin-trazo'}
                    trazo={
                      seleccionado
                        ? { id: seleccionado.id, geometry: seleccionado.geometry, nombre: nombreDelTrazo }
                        : null
                    }
                    escalaMPorUnidad={escalaDelPlano}
                    onCerrar={() => setVolumenAbierto(false)}
                  />
                )}
              </div>

              {datosAbiertos && (
                <CuadroDeDatos
                  resumen={resumen}
                  nombreDeNodo={nombreDeNodo}
                  calibrada={escalaDelPlano !== null}
                  onCerrar={() => setDatosAbiertos(false)}
                />
              )}

              <div className="estacion__hud">
                <span
                  className={`badge badge--${escalaDelPlano === null ? 'warn' : 'ok'}`}
                  title={
                    escalaDelPlano === null
                      ? 'Sin calibrar: se asume 1 unidad de plano = 1 m y las cantidades están en unidades de plano.'
                      : `1 unidad de plano = ${escalaDelPlano} m`
                  }
                >
                  {escalaDelPlano === null
                    ? 'Sin calibrar: cantidades en unidades de plano'
                    : `Escala 1 u = ${escalaDelPlano.toPrecision(4)} m`}
                </span>
                {filtrando && (
                  <span className="badge badge--info" role="status">
                    Solo {elegidos.size} {elegidos.size === 1 ? 'concepto' : 'conceptos'}
                  </span>
                )}
              </div>

              <Visor
                claveDePlano={planoElegido}
                fondoUrl={fondoUrl}
                trazos={trazosVisibles}
                notas={notasVisibles}
                seleccion={seleccion}
                herramienta={herramienta}
                borrador={borrador}
                huecoEnCurso={huecoEnCurso}
                bandaEnCurso={bandaEnCurso}
                fantasma={fantasma}
                etiquetas={etiquetas}
                cotas={cotas}
                onMover={forma === 'punto' && formaPunto !== null ? setCursor : undefined}
                onPunto={alPunto}
                onSeleccionar={setSeleccion}
              />

              <div className="estacion__mensajes">
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
              </div>
            </>
          )}
        </div>

        {detalleAbierto && !compacto && (
          <SeparadorDeAncho
            etiqueta="Ancho del detalle del trazo"
            lado="derecha"
            ancho={anchoDetalle.ancho}
            minimo={240}
            maximo={640}
            onCambio={anchoDetalle.fijar}
            onSoltar={anchoDetalle.recordar}
            onRestablecer={anchoDetalle.restablecer}
          />
        )}
        {detalleAbierto && detalle}
      </div>

      {plano !== undefined && (
        <div className="estacion__estado" aria-label="Estado del plano">
          {(forma || herramienta === 'hueco' || herramienta === 'escala') && (
            <div className="estacion__dibujo row" role="group" aria-label="Trazo en curso">
              {herramienta === 'escala' && (
                <span className="text-mute text-xs">
                  {borrador.length === 0
                    ? 'Marca el primer punto de una distancia conocida (una cota, un eje)'
                    : 'Marca el segundo punto'}
                </span>
              )}
              {herramienta === 'hueco' && (
                <>
                  <span className="text-mute text-xs">
                    Hueco: {huecoEnCurso.length} vértices · Enter lo cierra · Retroceso quita · Esc lo descarta
                  </span>
                  <button
                    type="button"
                    className="btn btn--accent btn--sm"
                    disabled={huecoEnCurso.length < PUNTOS_MINIMOS_DE_HUECO || agregarHueco.isPending}
                    onClick={() => void cerrarHueco()}
                  >
                    Cerrar hueco
                  </button>
                </>
              )}
              {forma && forma !== 'punto' && (
                <>
                  <span className="text-mute text-xs">
                    {`${borrador.length} vértices · Enter cierra · Retroceso quita · Esc descarta`}
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
              {forma === 'punto' && formaPunto !== null && (
                <span className="text-mute text-xs">
                  Clic para estampar: {formaPunto.nombre ?? NOMBRE_DE_FORMA[formaPunto.tipo]}{' '}
                  {formaPunto.anchoM} × {formaPunto.altoM} m
                </span>
              )}
            </div>
          )}
          <span>
            {featuresVisibles.length} de {features.length} {features.length === 1 ? 'trazo' : 'trazos'}
            {filtrando ? ' (filtrados)' : ''}
          </span>
          <span>
            {listaDeNotas.length} {listaDeNotas.length === 1 ? 'nota' : 'notas'}
          </span>
        </div>
      )}

      {guardando && plano && forma && (
        <AltaTrazo
          planoId={plano.id}
          versionPlano={plano.version}
          herramienta={formaEstampada !== null ? 'poligono' : forma}
          puntos={borrador}
          grosorM={forma === 'linea' ? grosorM : null}
          alineacion={forma === 'linea' && grosorM !== null ? alineacion : null}
          grosorU={grosorM !== null ? grosorM * unidadesPorMetro : null}
          forma={formaEstampada}
          actividades={actividades}
          actividadInicial={actividadFocoId}
          nodosDePrototipo={puedeEnlazarPrototipo ? nodosDePrototipo : null}
          onCerrar={() => {
            setGuardando(false);
            // Un punto se captura con un solo clic: si se cancela el cajón no
            // hay nada que seguir editando, se descarta.
            if (forma === 'punto') limpiarDibujo();
            setFormaEstampada(null);
          }}
          onGuardado={alGuardar}
        />
      )}

      {calibrando && plano && borrador.length === 2 && (
        <CalibrarEscala
          planoId={plano.id}
          puntoA={borrador[0] as Punto}
          puntoB={borrador[1] as Punto}
          escalaActual={escalaDelPlano}
          onCerrar={() => {
            setCalibrando(false);
            setBorrador([]);
          }}
          onCalibrada={(r: EscalaRespuesta) => {
            setCalibrando(false);
            setBorrador([]);
            setHerramienta('seleccionar');
            setAviso(
              `Escala calibrada: 1 unidad de plano = ${Number(r.escala_m_por_unidad).toPrecision(4)} m. ` +
                (r.recalculos.length === 0
                  ? 'Todavía no hay trazos enlazados que recalcular.'
                  : `Se recalcularon ${r.recalculos.length} ${r.recalculos.length === 1 ? 'nodo' : 'nodos'}.`),
            );
            void queryClient.invalidateQueries({
              queryKey: getListarPlanosApiV1ObrasObraIdPlanosGetQueryKey(obraId),
            });
            void queryClient.invalidateQueries({
              queryKey: getTrazosDePlanoApiV1PlanosPlanoIdTrazosGetQueryKey(planoElegido),
            });
            void queryClient.invalidateQueries({
              queryKey: getEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGetQueryKey(obraId),
            });
          }}
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

/**
 * El módulo (espacio de trabajo, D-532): una entrada propia del menú, con la
 * obra elegida a la vista. Acepta `?obra=&plano=&actividad=` para que
 * «Abrir en el módulo», desde la ventana flotante, llegue al mismo plano y a la
 * misma actividad sin que se pierda lo trazado.
 */
export default function Cuantificador() {
  const [busqueda, setBusqueda] = useSearchParams();
  const { sesion } = useSesion();
  const [creandoObra, setCreandoObra] = useState(false);
  const obraId = busqueda.get('obra') ?? '';
  const selectorDeObra = (
    <div className="estacion__obra">
      <SelectorObra
        id="cuant-obra"
        etiqueta="Obra"
        valor={obraId}
        onCambio={(id) => setBusqueda(id === '' ? {} : { obra: id })}
      />
    </div>
  );
  // La entrada del escenario «Nuevo»: la obra se crea desde aquí (Control de obra, §11.2).
  const nuevaObra =
    sesion?.rol === 'control_obra' ? (
      <button type="button" className="btn btn--sm" onClick={() => setCreandoObra(true)}>
        Nueva obra
      </button>
    ) : null;

  return (
    <div className="page page--estacion">
      {obraId === '' ? (
        <>
          <div className="estacion__cabecera">
            {selectorDeObra}
            {nuevaObra}
          </div>
          <div className="empty">
            <div className="empty-title">Elige una obra</div>
            <div className="empty-sub">Los planos y sus trazos son de una obra.</div>
          </div>
        </>
      ) : (
        <EspacioDeTrazo
          key={obraId}
          obraId={obraId}
          cabecera={
            <>
              {selectorDeObra}
              {nuevaObra}
            </>
          }
          planoInicial={busqueda.get('plano') ?? undefined}
          actividadFocoId={busqueda.get('actividad') ?? undefined}
        />
      )}
      {creandoObra && (
        <NuevaObra
          onCerrar={() => setCreandoObra(false)}
          onCreada={(id) => {
            setCreandoObra(false);
            setBusqueda({ obra: id });
          }}
        />
      )}
    </div>
  );
}
