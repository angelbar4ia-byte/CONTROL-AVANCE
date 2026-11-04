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
import { useIsMutating, useQueries } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGetQueryKey,
  getListarPlanosApiV1ObrasObraIdPlanosGetQueryKey,
  getNotasDePlanoApiV1PlanosPlanoIdNotasGetQueryKey,
  getTrazosDePlanoApiV1PlanosPlanoIdTrazosGetQueryKey,
  useAgregarHuecoApiV1TrazosTrazoIdHuecosPost,
  useQuitarHuecoApiV1TrazosTrazoIdHuecosHuecoIdDelete,
  useRegistrarTrazoApiV1PlanosPlanoIdTrazosPost,
  useTraerTrazoApiV1TrazosTrazoIdTraerPost,
  useEliminarTrazoApiV1TrazosTrazoIdDelete,
  useTransformarTrazosApiV1TrazosTransformarPost,
  useAprobarTrazoApiV1TrazosTrazoIdAprobarPost,
  useArchivoDePlanoApiV1PlanosPlanoIdArchivoGet,
  useEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGet,
  useListarPlanosApiV1ObrasObraIdPlanosGet,
  useFijarVistaApiV1PlanosPlanoIdVistaPut,
  useNotasDePlanoApiV1PlanosPlanoIdNotasGet,
  useTrazosDePlanoApiV1PlanosPlanoIdTrazosGet,
  getMatricesDeLaActividadApiV1ActividadesActividadIdMatricesGetQueryOptions,
} from '@/api/generado/cuantificacion/cuantificacion';
import {
  getListarElementosApiV1ElementosGetQueryKey,
  getListarMedicionesApiV1PlanosPlanoIdMedicionesGetQueryKey,
  usePonerTrazoEnMedicionApiV1TrazosTrazoIdMedicionPut,
  useListarElementosApiV1ElementosGet,
  useListarMedicionesApiV1PlanosPlanoIdMedicionesGet,
} from '@/api/generado/mediciones/mediciones';
import type {
  CuadrillaRespuesta,
  ElementoRespuesta,
  MedicionRespuesta,
  TrazoPeticion,
  ActividadRespuesta,
  ArchivoDePlanoRespuesta,
  EscalaRespuesta,
  NodoCuantificadoRespuesta,
  NodoPrototipoRespuesta,
  NotaPlanoDetalleRespuesta,
  PlanoDetalleRespuesta,
  TrazoRespuesta,
  TrabajoDeObraRespuesta,
  TrazosDePlanoRespuesta,
} from '@/api/generado/modelo';
import {
  getListarEnlacesDeHojaApiV1PlanosPlanoIdEnlacesGetQueryKey,
  useEliminarEnlaceDeHojaApiV1EnlacesDeHojaEnlaceIdDelete,
  useListarEnlacesDeHojaApiV1PlanosPlanoIdEnlacesGet,
} from '@/api/generado/enlaces-de-hoja/enlaces-de-hoja';
import { useListarObrasApiV1ObrasGet } from '@/api/generado/obras/obras';
import { useTrabajosDeObraApiV1ObrasObraIdTrabajosGet } from '@/api/generado/torre/torre';
import { useListarCuadrillasApiV1CuadrillasGet } from '@/api/generado/catalogos/catalogos';
import {
  useAceptarPropuestasApiV1PlanosPlanoIdPropuestasAceptarPost,
  useRechazarPropuestasApiV1PlanosPlanoIdPropuestasRechazarPost,
} from '@/api/generado/propuestas/propuestas';
import { useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet } from '@/api/generado/proyectos/proyectos';
import {
  getActividadesDeObraApiV1ObrasObraIdActividadesGetQueryKey,
  useActividadesDeObraApiV1ObrasObraIdActividadesGet,
} from '@/api/generado/torre/torre';
import { queryClient } from '@/app/queryClient';
import { useSesion } from '@/app/sesion';
import { useSearchParams } from 'react-router-dom';
import { fmtFecha, fmtNum } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { SelectorObra } from '@/lib/SelectorObra';
import { AltaNota } from './AltaNota';
import { EditorDeTrabajo } from './EditorDeTrabajo';
import { PanelDeElementos } from './PanelDeElementos';
import { PanelDeTrabajos, cuadrillasDeLosTrabajos, type TrabajoElegido } from './PanelDeTrabajos';
import { PanelDeMediciones } from './PanelDeMediciones';
import { TrazosDelPlano } from './TrazosDelPlano';
import { admiteGeometria, asignacionesEfectivas, colorDeConcepto, coloresDeMediciones, idsDeRama } from './mediciones';
import { OpcionesDeContorno } from './OpcionesDeContorno';
import { OpcionesDeNota, type ClaseDeNota } from './OpcionesDeNota';
import { bloqueDeTipo, NOMBRE_DE_TIPO, tipoDeMedicion } from './tipos';
import { girar, rotacionValida, type VistaDelPlano } from './vista';
import { AltaDeConcepto } from './AltaDeConcepto';
import { AltaPlano } from './AltaPlano';
import { AltaTrazo, type NodoDePrototipo } from './AltaTrazo';
import { ALTURA_POR_DEFECTO_M, CARAS_POR_DEFECTO, factorDeLaMedida, medidaDirecta, trazoPeticion } from './trazoPeticion';
import { motivoDeIncompatibilidad } from './mediciones';
import { CalibrarEscala } from './CalibrarEscala';
import { useAjuste, useAnchoAjustable } from '@/lib/useAjuste';
import { SeparadorDeAncho } from './SeparadorDeAncho';
import { arbolDeCuantificacion, trazosDeConceptos } from './arbol';
import { ArbolPresupuesto } from './ArbolPresupuesto';
import { Modal } from '@/lib/Modal';
import { BarraDeFunciones, BarraDeTrazo, type ClaveDeInterruptor, type Interruptor } from './BarraDeHerramientas';
import { CuadroDeDatos } from './CuadroDeDatos';
import { crearHistorial } from './historial';
import { AyudasDeDibujo } from './AyudasDeDibujo';
import {
  CLICS_DE_FORMA,
  contornoCerrado,
  siguienteTramo,
  type ModoDeContorno,
  type TramoDeContorno,
  GEOMETRIA_DE,
  ajustarAngulo,
  formaDe,
  type HerramientaDeDibujo,
} from './dibujo';
import { centroide, cotasDe, etiquetasDeMedidas, fmtMedida, sinCierre } from './etiquetas';
import {
  REFERENCIAS_POR_DEFECTO,
  buscarReferencia,
  type ReferenciasActivas,
} from './referencias';
import {
  bandaDeLinea,
  poligonoDeForma,
  normalizarContorno,
  NOMBRE_DE_FORMA,
  type Alineacion,
  type Forma,
} from './formas';
import { NavegadorDePlanos } from './NavegadorDePlanos';
import { OpcionesDeHerramienta } from './OpcionesDeHerramienta';
import { desfaseDeTexto, porTraer, versionesAnteriores } from './empalme';
import { AltaEnlaceDeHoja } from './AltaEnlaceDeHoja';
import { ConteoAutomatico } from './ConteoAutomatico';
import { TakeoffAutomatico } from './TakeoffAutomatico';
import { OpcionesDeEmpalme } from './OpcionesDeEmpalme';
import { PanelDelArbol } from './PanelDelArbol';
import { PanelDePropuestas } from './PanelDePropuestas';
import { ProponerEscala } from './ProponerEscala';
import { VanosDelTrazo } from './VanosDelTrazo';
import { PanelVolumen } from './PanelVolumen';
import { resumenDePantalla, type TrazoParaResumen } from './resumen';
import { NuevaObra } from './NuevaObra';
import { ReemplazarEnlace } from './ReemplazarEnlace';
import { Visor, type NotaVisible, type Seleccion, type TrazoVisible } from './Visor';
import {
  PUNTOS_MINIMOS_DE_HUECO,
  aWkt,
  gradosDeGiro,
  trasladar,
  geojsonAWkt,
  areaDeGeometria,
  type GeometriaBase,
  herramientaDeGeometria,
  partesDe,
  type GeometriaGeoJson,
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
  'linea',
  'polilinea',
  'arco',
  'poligono',
  'rectangulo',
  'circulo',
  'elipse',
  'contorno',
  'rectangulo_l',
  'circulo_l',
  'elipse_l',
  'punto',
  'copiar',
  'mover',
  'hueco',
  'borrar',
  'escala',
  'enlace',
  'conteo_auto',
];

/** Anotar el plano es solo de Residente y Supervisor (MODELO.md §1b); el
 *  servidor lo impone con 403, esto solo evita ofrecer un botón que fallaría. */
const HERRAMIENTA_NOTA: Herramienta = 'nota';

/** Qué se da clic, en orden, en las herramientas que se cierran solas. */
const PASOS_DE_LA_FORMA: Readonly<Record<HerramientaDeDibujo, string>> = {
  linea: 'Clic en el inicio y en el final',
  rectangulo: 'Clic en una esquina y en la opuesta',
  circulo: 'Clic en el centro y en un punto del borde',
  elipse: 'Clic en el centro, en el extremo de un eje y en un punto del otro',
  arco: 'Clic en el inicio, en un punto del arco y en el final',
  polilinea: '',
  poligono: '',
  contorno: '',
  rectangulo_l: 'Clic en una esquina y en la opuesta (recorrido cerrado)',
  circulo_l: 'Clic en el centro y en un punto del borde (recorrido cerrado)',
  elipse_l: 'Clic en el centro, en el extremo de un eje y en un punto del otro (recorrido cerrado)',
};

/** Atajo de teclado de cada herramienta de la barra. */
const ATAJOS: Readonly<Record<string, Herramienta>> = {
  v: 'seleccionar',
  h: 'mano',
  z: 'zoom',
  u: 'hueco',
  b: 'borrar',
  p: 'poligono',
  l: 'linea',
  y: 'polilinea',
  a: 'arco',
  r: 'rectangulo',
  i: 'circulo',
  j: 'elipse',
  w: 'contorno',
  o: 'punto',
  k: 'copiar',
  m: 'mover',
  e: 'escala',
  n: 'nota',
};

const NOMBRE_DE_ANOTACION: Readonly<Record<ClaseDeNota, string>> = {
  nota: 'Nota',
  texto: 'Texto',
  flecha: 'Flecha',
  llamada: 'Llamada',
};

/** Un `Point` GeoJSON como punto de plano, o `null`. */
function puntoDeGeoJson(g: { coordinates?: unknown } | null | undefined): Punto | null {
  const c = g?.coordinates;
  return Array.isArray(c) && typeof c[0] === 'number' && typeof c[1] === 'number' ? ([c[0], c[1]] as Punto) : null;
}

/** El centro de una pieza (un punto, o el contorno de una forma estampada). */
/**
 * La medición de un trazo ya guardado. **Sin botón**: al elegir otra, el cambio llega a la API en ese
 * momento. Solo ofrece las mediciones donde el trazo cabe (su tipo y su plano).
 */
function SelectorDeMedicion({
  trazo,
  mediciones,
  ocupado,
  onCambiar,
}: {
  readonly trazo: {
    readonly geometry: GeometriaGeoJson;
    readonly properties: { readonly medicion_id?: string | null; readonly forma?: unknown };
  };
  readonly mediciones: readonly MedicionRespuesta[];
  readonly ocupado: boolean;
  readonly onCambiar: (medicionId: string | null) => void;
}) {
  const base = herramientaDeGeometria(trazo.geometry);
  const esPieza = trazo.properties.forma != null;
  const caben = mediciones.filter((m) => base !== null && admiteGeometria(m.tipo, base, esPieza));
  if (mediciones.length === 0) return null;
  return (
    <div className="field">
      <label className="field__label" htmlFor="trazo-medicion">
        Medición
      </label>
      <select
        id="trazo-medicion"
        className="select"
        value={trazo.properties.medicion_id ?? ''}
        disabled={ocupado}
        onChange={(e) => onCambiar(e.target.value === '' ? null : e.target.value)}
      >
        <option value="">Suelto (sin medición)</option>
        {caben.map((m) => (
          <option key={m.id} value={m.id}>
            {m.nombre}
          </option>
        ))}
      </select>
    </div>
  );
}

function centroDeLaPieza(geometria: GeometriaGeoJson): Punto | null {
  const primero = partesDe(geometria)[0];
  if (!primero) return null;
  if (primero.tipo === 'punto') return primero.puntos[0] as Punto;
  if (primero.tipo === 'anillo') return centroide(primero.puntos);
  return null;
}

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
  // El contorno mezcla tramos rectos y arcos: cómo se llegó a cada clic después del primero, y cómo es el siguiente.
  const [tramosContorno, setTramosContorno] = useState<readonly TramoDeContorno[]>([]);
  const [modoContorno, setModoContorno] = useState<ModoDeContorno>('recto');
  /** El concepto que se está midiendo (clic en el árbol): manda el tipo de medición y es el que trae el cajón de guardar. */
  const [conceptoActivo, setConceptoActivo] = useState<string | null>(null);
  /** Si lo que se mide es una matriz interna del concepto activo (nervaduras, trabes…): su id, clave y unidad. */
  const [matrizActiva, setMatrizActiva] = useState<{ id: string; clave: string; unidad: string | null } | null>(null);
  // El hueco que se está dibujando sobre el área elegida (la ventana de un muro, el cubo de una
  // escalera). Se descuenta del área al cerrarlo con Enter.
  const [huecoEnCurso, setHuecoEnCurso] = useState<readonly Punto[]>([]);
  // Opciones de las herramientas: el grosor y la alineación de una línea, la forma de un punto.
  const [grosorM, setGrosorM] = useState<number | null>(null);
  /** Pendiente en % de la línea que se traza (un tramo inclinado); `null` = horizontal. */
  const [pendientePct, setPendientePct] = useState<number | null>(null);
  const [alineacion, setAlineacion] = useState<Alineacion>('centro');
  const [formaPunto, setFormaPunto] = useState<Forma | null>(null);
  /** La forma con la que se está guardando el trazo (solo cuando nació de un punto con forma). */
  const [formaEstampada, setFormaEstampada] = useState<Forma | null>(null);
  const [cursor, setCursor] = useState<Punto | null>(null);
  // Ayudas de dibujo: ortogonal (por defecto a 90°, que da 0° y 180° y las verticales) y referencia a objetos.
  const [ortogonal, setOrtogonal] = useState(true);
  const [pasoGrados, setPasoGrados] = useState(90);
  const [baseGrados, setBaseGrados] = useState(0);
  const [referenciasOn, setReferenciasOn] = useState(true);
  const [referencias, setReferencias] = useState<ReferenciasActivas>(REFERENCIAS_POR_DEFECTO);
  /** Mayús apretada: invierte el ortogonal mientras se mantiene. */
  const mayus = useRef(false);
  /** Cuántas copias lleva la pieza que se repite con «Copiar en lote». */
  const copias = useRef(0);
  const [ayudasAbiertas, setAyudasAbiertas] = useState(false);
  // Deshacer y rehacer: la pila vive en esta sesión y se vacía al cambiar de plano. Un trazo que se
  // recrea (deshacer un borrado, rehacer un trazo) nace con id nuevo: `alias` lleva del viejo al nuevo
  // para que las acciones anteriores sigan encontrándolo.
  const [historial] = useState(() => crearHistorial());
  const [, setVersionHistorial] = useState(0);
  const [trabajandoHistorial, setTrabajandoHistorial] = useState(false);
  const alias = useRef(new Map<string, string>());
  /** Lo que se está por guardar: la geometría final (un círculo ya es un polígono de muchos lados). */
  const [aGuardar, setAGuardar] = useState<{ tipo: GeometriaBase; puntos: readonly Punto[] } | null>(null);
  /** El trazo que se está por borrar, a la espera de que se confirme. */
  const [porBorrar, setPorBorrar] = useState<string | null>(null);
  const [mostrarMedidas, setMostrarMedidas] = useState(false);
  const [mostrarCotas, setMostrarCotas] = useState(false);
  const [datosAbiertos, setDatosAbiertos] = useState(false);
  // Empalme de versiones: la versión anterior como fantasma, su desfase y lo que ya se trajo.
  const [empalmeAbierto, setEmpalmeAbierto] = useState(false);
  const [empalmeVersionId, setEmpalmeVersionId] = useState('');
  const [empalmeDx, setEmpalmeDx] = useState('0');
  const [empalmeDy, setEmpalmeDy] = useState('0');
  const [fantasmaElegido, setFantasmaElegido] = useState<string | null>(null);
  const [traidos, setTraidos] = useState<ReadonlySet<string>>(new Set());
  const [trayendo, setTrayendo] = useState(false);
  const [empalmeOpacidad, setEmpalmeOpacidad] = useState(55);
  const [proponiendoEscala, setProponiendoEscala] = useState(false);
  // Enlaces entre hojas: la zona que se marca con dos clics y a dónde lleva.
  const [zonaDeEnlace, setZonaDeEnlace] = useState<readonly [Punto, Punto] | null>(null);
  // Conteo automático: el símbolo que se marcó con dos clics y las coincidencias que se ven de antemano.
  const [zonaDePlantilla, setZonaDePlantilla] = useState<readonly [Punto, Punto] | null>(null);
  const [previasAuto, setPreviasAuto] = useState<readonly GeometriaGeoJson[]>([]);
  const verCoincidencias = useCallback(
    (centros: readonly Punto[]) => setPreviasAuto(centros.map((c) => ({ type: 'Point', coordinates: [c[0], c[1]] }) as GeometriaGeoJson)),
    [],
  );
  const [takeoffAbierto, setTakeoffAbierto] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [subiendoPlano, setSubiendoPlano] = useState(false);
  const [seleccion, setSeleccion] = useState<Seleccion | null>(null);
  const [notaPunto, setNotaPunto] = useState<Punto | null>(null);
  /** Qué se anota con la herramienta Nota, y a dónde apunta si es una flecha o una llamada. */
  const [claseDeNota, setClaseDeNota] = useState<ClaseDeNota>('nota');
  const [notaDestino, setNotaDestino] = useState<Punto | null>(null);
  const [reemplazando, setReemplazando] = useState<string | null>(null);
  const [calibrando, setCalibrando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [elegidos, setElegidos] = useState<ReadonlySet<string>>(new Set());
  const [soloElegidos, setSoloElegidos] = useState(false);
  const [volumenAbierto, setVolumenAbierto] = useState(false);
  const [arbolAbierto, setArbolAbierto] = useAjuste('arbol', !compacto);
  // La segunda pestaña del panel lateral: el navegador de planos (el presupuesto es la primera).
  const [pestana, setPestana] = useState<'presupuesto' | 'planos' | 'mediciones' | 'trazos' | 'elementos' | 'trabajos' | 'arbol'>('presupuesto');
  /** La medición activa (la capa sombra): lo que se dibuja entra a ella. */
  const [medicionActivaId, setMedicionActivaId] = useState<string | null>(null);
  const [detalleAbierto, setDetalleAbierto] = useAjuste('detalle', !compacto);
  // El ancho de los dos paneles laterales se ajusta arrastrando su borde y se recuerda.
  const anchoArbol = useAnchoAjustable('ancho-arbol', 300, 200, 560);
  const anchoDetalle = useAnchoAjustable('ancho-detalle', 320, 240, 640);

  const planos = useListarPlanosApiV1ObrasObraIdPlanosGet<
    PlanoDetalleRespuesta[],
    ErrorApi
  >(obraId, { query: { enabled: obraId !== '' } });
  const listaDePlanos = useMemo(() => planos.data ?? [], [planos.data]);
  const medicionesConsulta = useListarMedicionesApiV1PlanosPlanoIdMedicionesGet<MedicionRespuesta[], ErrorApi>(
    planoElegido,
    { query: { enabled: planoElegido !== '' } },
  );
  const listaDeMediciones = useMemo(() => medicionesConsulta.data ?? [], [medicionesConsulta.data]);
  /** Cada medición lleva su color: el plano, el panel y la etiqueta de medida lo comparten. */
  const coloresDeMedicion = useMemo(() => coloresDeMediciones(listaDeMediciones), [listaDeMediciones]);
  // Todo cambio llega a la API en el momento: no hay botón de guardar. Esto solo dice si algo va en camino.
  const guardandoAhora = useIsMutating() > 0;
  const meterEnMedicion = usePonerTrazoEnMedicionApiV1TrazosTrazoIdMedicionPut<ErrorApi>();
  const elementosConsulta = useListarElementosApiV1ElementosGet<ElementoRespuesta[], ErrorApi>();
  const listaDeElementos = useMemo(() => elementosConsulta.data ?? [], [elementosConsulta.data]);
  /** El peso de un elemento cambia cantidades de presupuesto (kg y ton): lo ponen Control de obra y Costos. */
  const puedePonerPeso = sesion?.rol === 'control_obra' || sesion?.rol === 'costos';
  // Trabajos: el costo de una cuadrilla es del catálogo de costos, así que lo ven Control de obra, Super
  // intendente y Costos; solo Control de obra lo edita (las rutas de edición son suyas).
  const puedeVerTrabajos = sesion?.rol === 'control_obra' || sesion?.rol === 'super_intendente' || sesion?.rol === 'costos';
  const puedeEditarTrabajos = sesion?.rol === 'control_obra';
  const [trabajoElegido, setTrabajoElegido] = useState<TrabajoElegido | null>(null);
  const medicionActiva = medicionActivaId ? (listaDeMediciones.find((m) => m.id === medicionActivaId) ?? null) : null;

  // Al llegar la lista, se abre el primer plano para no dejar al usuario frente
  // a un vacío.
  useEffect(() => {
    if (planoElegido === '' && listaDePlanos[0]) setPlanoElegido(listaDePlanos[0].id);
  }, [listaDePlanos, planoElegido]);
  useEffect(() => {
    if (planoElegido !== '') onPlanoCambiado?.(planoElegido);
  }, [planoElegido, onPlanoCambiado]);

  const plano = listaDePlanos.find((p) => p.id === planoElegido);

  // Cómo se ve el plano (girado, en espejo). Se guarda con el plano; mientras llega la respuesta se
  // muestra lo que se acaba de pedir.
  const fijarVista = useFijarVistaApiV1PlanosPlanoIdVistaPut<ErrorApi>();
  const [vistaPedida, setVistaPedida] = useState<{ planoId: string; vista: VistaDelPlano } | null>(null);
  const vistaGuardada: VistaDelPlano = {
    rotacionGrados: rotacionValida(plano?.rotacion_grados),
    volteoH: plano?.volteo_horizontal ?? false,
    volteoV: plano?.volteo_vertical ?? false,
  };
  const vistaDelPlano = vistaPedida && vistaPedida.planoId === planoElegido ? vistaPedida.vista : vistaGuardada;
  function cambiarVista(nueva: VistaDelPlano) {
    setVistaPedida({ planoId: planoElegido, vista: nueva });
    fijarVista.mutate(
      {
        planoId: planoElegido,
        data: {
          rotacion_grados: nueva.rotacionGrados,
          volteo_horizontal: nueva.volteoH,
          volteo_vertical: nueva.volteoV,
        },
      },
      {
        onSuccess: () => {
          void queryClient.invalidateQueries({ queryKey: getListarPlanosApiV1ObrasObraIdPlanosGetQueryKey(obraId) });
        },
        onError: (err) => {
          setVistaPedida(null);
          setAviso(`No se pudo cambiar la vista del plano: ${err.message}`);
        },
      },
    );
  }
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
  const trabajosConsulta = useTrabajosDeObraApiV1ObrasObraIdTrabajosGet<TrabajoDeObraRespuesta[], ErrorApi>(
    obraId,
    { query: { enabled: obraId !== '' && puedeVerTrabajos } },
  );
  const listaDeTrabajos = useMemo(() => trabajosConsulta.data ?? [], [trabajosConsulta.data]);
  const cuadrillasConsulta = useListarCuadrillasApiV1CuadrillasGet<CuadrillaRespuesta[], ErrorApi>(undefined, {
    query: { enabled: puedeEditarTrabajos && pestana === 'trabajos' },
  });
  const cuadrillasDelCatalogo = useMemo(() => cuadrillasConsulta.data ?? [], [cuadrillasConsulta.data]);
  const cuadrillasDeLaObra = useMemo(() => cuadrillasDeLosTrabajos(listaDeTrabajos), [listaDeTrabajos]);
  /** Lo medido de cada actividad: con la cantidad presupuestada, da la del concepto en Trabajos. */
  const medidaPorActividad = useMemo(
    () => new Map((estado.data ?? []).filter((n) => n.tipo_nodo === 'actividad').map((n) => [n.nodo_id, n.cantidad_medida])),
    [estado.data],
  );
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

  // Las propuestas por revisar no son medidas: se ven aparte y nada de lo que se mide las toca.
  const todosLosTrazos = useMemo(() => trazosConsulta.data?.features ?? [], [trazosConsulta.data]);
  const features = useMemo(() => todosLosTrazos.filter((f) => !f.properties.propuesta), [todosLosTrazos]);
  const propuestasDelPlano = useMemo(() => todosLosTrazos.filter((f) => f.properties.propuesta), [todosLosTrazos]);
  const [propuestasDescartadas, setPropuestasDescartadas] = useState<ReadonlySet<string>>(new Set());
  const propuestasElegidas = propuestasDelPlano.filter((f) => !propuestasDescartadas.has(f.id));
  const aceptarPropuestas = useAceptarPropuestasApiV1PlanosPlanoIdPropuestasAceptarPost<ErrorApi>();
  const rechazarPropuestas = useRechazarPropuestasApiV1PlanosPlanoIdPropuestasRechazarPost<ErrorApi>();
  const resumenDePropuestas = useMemo(() => {
    const por = new Map<string, { concepto: string; n: number; origen: string }>();
    for (const f of propuestasDelPlano) {
      const a = actividades.find((x) => x.id === f.properties.propuesta_actividad_id);
      const concepto = String(a?.concepto_clave ?? a?.descripcion ?? 'un concepto');
      const origen = String(f.properties.propuesta_origen ?? '');
      const clave = `${concepto}|${origen}`;
      por.set(clave, { concepto, origen, n: (por.get(clave)?.n ?? 0) + 1 });
    }
    return [...por.values()];
  }, [propuestasDelPlano, actividades]);
  async function resolverPropuestas(accion: 'aceptar' | 'rechazar') {
    const ids = propuestasElegidas.map((f) => f.id);
    if (ids.length === 0) return;
    try {
      if (accion === 'aceptar') {
        await aceptarPropuestas.mutateAsync({ planoId: planoElegido, data: { trazo_ids: ids } });
        setAviso(`${ids.length} ${ids.length === 1 ? 'propuesta aceptada' : 'propuestas aceptadas'}: ya miden su concepto.`);
      } else {
        await rechazarPropuestas.mutateAsync({ planoId: planoElegido, data: { trazo_ids: ids } });
        setAviso(`${ids.length} ${ids.length === 1 ? 'propuesta rechazada' : 'propuestas rechazadas'}.`);
      }
      setPropuestasDescartadas(new Set());
    } catch (err) {
      setAviso(`No se pudo ${accion} las propuestas: ${err instanceof Error ? err.message : 'error'}`);
    } finally {
      invalidarTrazos();
    }
  }
  const versionesPrevias = useMemo(() => versionesAnteriores(listaDePlanos, planoElegido), [listaDePlanos, planoElegido]);
  const empalmeVersion = versionesPrevias.find((v) => v.id === empalmeVersionId) ?? versionesPrevias[0];
  const trazosAnteriores = useTrazosDePlanoApiV1PlanosPlanoIdTrazosGet<TrazosDePlanoRespuesta, ErrorApi>(
    empalmeVersion?.id ?? '',
    { query: { enabled: empalmeAbierto && empalmeVersion !== undefined } },
  );
  const fantasmasPorTraer = useMemo(
    () => porTraer(trazosAnteriores.data?.features ?? [], traidos),
    [trazosAnteriores.data, traidos],
  );
  const traerTrazo = useTraerTrazoApiV1TrazosTrazoIdTraerPost<ErrorApi>();
  const enlacesConsulta = useListarEnlacesDeHojaApiV1PlanosPlanoIdEnlacesGet(planoElegido, {
    query: { enabled: planoElegido !== '' },
  });
  const quitarEnlace = useEliminarEnlaceDeHojaApiV1EnlacesDeHojaEnlaceIdDelete<ErrorApi>();
  const enlacesVisibles = useMemo(
    () =>
      (enlacesConsulta.data ?? []).map((e) => ({
        id: e.id,
        x: e.x,
        y: e.y,
        ancho: e.ancho,
        alto: e.alto,
        etiqueta: e.etiqueta,
        destinoId: e.destino_plano_id,
      })),
    [enlacesConsulta.data],
  );
  const hojasDeDestino = useMemo(() => listaDePlanos.filter((p) => p.id !== planoElegido), [listaDePlanos, planoElegido]);
  function usarEnlace(enlace: { id: string; destinoId: string; etiqueta: string }, accion: 'abrir' | 'quitar') {
    if (accion === 'abrir') {
      setPlanoElegido(enlace.destinoId);
      setBorrador([]);
      setSeleccion(null);
      return;
    }
    quitarEnlace.mutate(
      { enlaceId: enlace.id },
      {
        onSuccess: () => {
          setAviso(`Enlace «${enlace.etiqueta}» quitado.`);
          void queryClient.invalidateQueries({
            queryKey: getListarEnlacesDeHojaApiV1PlanosPlanoIdEnlacesGetQueryKey(planoElegido),
          });
        },
        onError: (err) => setAviso(`No se pudo quitar el enlace: ${err.message}`),
      },
    );
  }
  // Otro plano: el empalme y lo elegido no se arrastran.
  useEffect(() => {
    setEmpalmeAbierto(false);
    setFantasmaElegido(null);
    setTraidos(new Set());
    setEmpalmeVersionId('');
  }, [planoElegido]);
  async function traerFantasmas(ids: readonly string[]) {
    if (ids.length === 0 || trayendo) return;
    setTrayendo(true);
    let hechos = 0;
    try {
      for (const id of ids) {
        await traerTrazo.mutateAsync({
          trazoId: id,
          data: { plano_destino_id: planoElegido, dx: String(desfaseDeTexto(empalmeDx)), dy: String(desfaseDeTexto(empalmeDy)) },
        });
        hechos += 1;
        setTraidos((t) => new Set(t).add(id));
      }
      setFantasmaElegido(null);
      setAviso(hechos === 1 ? 'Trazo traído a esta versión.' : `${hechos} trazos traídos a esta versión.`);
    } catch (err) {
      setAviso(
        `${hechos > 0 ? `Se trajeron ${hechos}; ` : ''}no se pudo traer el siguiente: ${err instanceof Error ? err.message : 'error'}`,
      );
    } finally {
      setTrayendo(false);
      invalidarTrazos();
      if (empalmeVersion) {
        void queryClient.invalidateQueries({
          queryKey: getTrazosDePlanoApiV1PlanosPlanoIdTrazosGetQueryKey(empalmeVersion.id),
        });
      }
    }
  }
  // Los trazos de la medición activa (y de sus submediciones), para resaltarlos en el plano.
  const trazosDeLaMedicion = useMemo(() => {
    if (!medicionActiva) return new Set<string>();
    const ids = idsDeRama(listaDeMediciones, medicionActiva.id);
    return new Set(
      features.filter((f) => f.properties.medicion_id && ids.has(f.properties.medicion_id)).map((f) => f.id),
    );
  }, [medicionActiva, listaDeMediciones, features]);
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
  const geometriasVisibles = useMemo(() => featuresVisibles.map((f) => f.geometry), [featuresVisibles]);
  const trazosVisibles = useMemo<TrazoVisible[]>(
    () =>
      featuresVisibles.map((f) => ({
        id: f.id,
        geometry: f.geometry,
        porRevisar: f.properties.por_revisar,
        aprobado: f.properties.aprobado_en != null,
        resaltado: trazosDeLaMedicion.has(f.id),
        // El color de su medición; sin medición, el de su concepto (para distinguir los trazos de cada concepto).
        ...(() => {
          const deMedicion = f.properties.medicion_id ? coloresDeMedicion.get(f.properties.medicion_id) : undefined;
          const concepto = f.properties.enlaces.find((e) => e.vigente && e.tipo_nodo !== 'prototipo_nodo')?.nodo_id;
          const color = deMedicion ?? (concepto ? colorDeConcepto(concepto) : undefined);
          return color ? { color } : {};
        })(),
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
    [featuresVisibles, unidadesPorMetro, trazosDeLaMedicion, coloresDeMedicion],
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
          ? [
              {
                id: n.id,
                punto: [c[0], c[1]] as Punto,
                texto: n.texto,
                porRevisar: n.por_revisar,
                tipo: n.tipo,
                destino: puntoDeGeoJson(n.destino),
              },
            ]
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

  const forma: HerramientaDeTrazo | null = [
    'poligono',
    'rectangulo',
    'circulo',
    'elipse',
    'contorno',
    'rectangulo_l',
    'circulo_l',
    'elipse_l',
    'arco',
    'linea',
    'polilinea',
    'punto',
  ].includes(herramienta)
    ? (herramienta as HerramientaDeTrazo)
    : null;
  /** Las que se cierran solas al dar el último clic; las demás terminan con Enter. */
  const clicsDeLaForma = forma && forma !== 'punto' ? CLICS_DE_FORMA[forma] : undefined;
  /** Dónde funcionan las ayudas: al dibujar, abrir un hueco, estampar un punto y calibrar. */
  const asistida = forma !== null || herramienta === 'hueco' || herramienta === 'escala' || herramienta === 'copiar' || herramienta === 'mover';
  /** Solo los tramos rectos se alinean a un ángulo (no las curvas ni los rectángulos, ni la calibración, que mide una distancia cualquiera). */
  const usaOrtogonal =
    herramienta === 'poligono' ||
    herramienta === 'polilinea' ||
    herramienta === 'linea' ||
    herramienta === 'hueco' ||
    // El contorno solo alinea sus tramos rectos, no el punto por donde pasa un arco.
    (herramienta === 'contorno' && modoContorno === 'recto' && tramosContorno[tramosContorno.length - 1] !== 'am');

  /** Un hueco solo se abre sobre un área (un polígono trazado, no una línea con grosor). */
  const areaElegida =
    seleccionado !== null && areaDeGeometria(seleccionado.geometry) > 0 ? seleccionado : null;

  /**
   * La pieza que se repite con «Copiar en lote»: un punto, o una forma estampada (un castillo, una
   * columna). Es lo que se cuenta, y lo que se quiere poner en muchos lugares sin volver a llenar
   * sus enlaces.
   */
  const piezaElegida =
    seleccionado !== null &&
    (seleccionado.geometry.type === 'Point' || seleccionado.properties.forma != null)
      ? seleccionado
      : null;

  const agregarHueco = useAgregarHuecoApiV1TrazosTrazoIdHuecosPost<ErrorApi>();
  const eliminar = useEliminarTrazoApiV1TrazosTrazoIdDelete<ErrorApi>();
  const registrarTrazo = useRegistrarTrazoApiV1PlanosPlanoIdTrazosPost<ErrorApi>();
  const quitarHueco = useQuitarHuecoApiV1TrazosTrazoIdHuecosHuecoIdDelete<ErrorApi>();
  const transformar = useTransformarTrazosApiV1TrazosTransformarPost<ErrorApi>();
  const [anguloLibre, setAnguloLibre] = useState('15');

  const refrescarHistorial = () => setVersionHistorial((v) => v + 1);
  /** El id con el que existe hoy un trazo, si se recreó una o varias veces al deshacer y rehacer. */
  const vigente = (id: string): string => {
    let actual = id;
    while (alias.current.has(actual)) actual = alias.current.get(actual) as string;
    return actual;
  };
  function invalidarTrazos() {
    // Lo que miden las mediciones (y cuántos trazos llevan) cambia con cada trazo.
    void queryClient.invalidateQueries({
      queryKey: getListarMedicionesApiV1PlanosPlanoIdMedicionesGetQueryKey(planoElegido),
    });
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
  /** Vuelve a registrar un trazo con el mismo cuerpo; el viejo `id` pasa a apuntar al nuevo. */
  async function recrear(original: string, planoId: string, data: TrazoPeticion) {
    const r = await registrarTrazo.mutateAsync({ planoId, data });
    alias.current.set(vigente(original), r.trazo_id);
  }
  async function deshacerUltimo() {
    if (trabajandoHistorial) return;
    setTrabajandoHistorial(true);
    try {
      const a = await historial.deshacer();
      if (a) {
        setSeleccion(null);
        setAviso(`Deshecho: ${a.etiqueta}.`);
        invalidarTrazos();
      }
    } catch (err) {
      setAviso(`No se pudo deshacer: ${err instanceof Error ? err.message : 'error'}`);
    } finally {
      setTrabajandoHistorial(false);
      refrescarHistorial();
    }
  }
  async function rehacerUltimo() {
    if (trabajandoHistorial) return;
    setTrabajandoHistorial(true);
    try {
      const a = await historial.rehacer();
      if (a) {
        setSeleccion(null);
        setAviso(`Rehecho: ${a.etiqueta}.`);
        invalidarTrazos();
      }
    } catch (err) {
      setAviso(`No se pudo rehacer: ${err instanceof Error ? err.message : 'error'}`);
    } finally {
      setTrabajandoHistorial(false);
      refrescarHistorial();
    }
  }

  /** Con la herramienta Borrar, un clic sobre un trazo pide confirmar su borrado; sobre nada, no hace nada. */
  function alElegirEnElPlano(elegido: Seleccion | null) {
    if (herramienta === 'borrar') {
      if (elegido?.tipo === 'trazo') {
        setSeleccion(elegido);
        setPorBorrar(elegido.id);
      }
      return;
    }
    setSeleccion(elegido);
  }

  /** Lo que hace falta para volver a crear un trazo igual (deshacer un borrado, copiar una pieza): enlaces vigentes, grosor, pendiente y forma. */
  function datosParaRecrear(feature: (typeof features)[number], wkt: string): TrazoPeticion {
    const p = feature.properties;
    return {
      version_plano: p.version_plano,
      fuente: p.fuente,
      capa: p.capa ?? null,
      geometria_wkt: wkt,
      enlaces: p.enlaces
        .filter((e) => e.vigente)
        .map((e) => ({
          medida: e.medida,
          factor: e.factor,
          ...(e.tipo_nodo === 'actividad'
            ? { actividad_id: e.nodo_id, ...(e.matriz_concepto_id ? { matriz_concepto_id: e.matriz_concepto_id } : {}) }
            : { prototipo_nodo_id: e.nodo_id }),
        })),
      ...(p.grosor_m != null && p.alineacion ? { grosor_m: String(p.grosor_m), alineacion: p.alineacion } : {}),
      ...(p.forma ? { forma: p.forma } : {}),
      ...(p.pendiente_pct != null ? { pendiente_pct: String(p.pendiente_pct) } : {}),
      ...(p.medicion_id ? { medicion_id: p.medicion_id } : {}),
    } as TrazoPeticion;
  }

  async function confirmarBorrado() {
    if (porBorrar === null) return;
    const id = porBorrar;
    setPorBorrar(null);
    const feature = features.find((f) => f.id === id);
    const planoDelTrazo = planoElegido;
    try {
      const r = await eliminar.mutateAsync({ trazoId: id });
      // Con lo que tenía el trazo se puede volver a crear (deshacer); recupera su geometría, sus
      // enlaces vigentes, su grosor y su forma. La aprobación no vuelve: el trazo recreado es nuevo.
      const wkt = feature ? geojsonAWkt(feature.geometry) : null;
      if (feature && wkt) {
        const data = datosParaRecrear(feature, wkt);
        historial.registrar({
          etiqueta: 'trazo borrado',
          deshacer: () => recrear(id, planoDelTrazo, data),
          rehacer: async () => {
            await eliminar.mutateAsync({ trazoId: vigente(id) });
          },
        });
        refrescarHistorial();
      }
      setSeleccion(null);
      const total = r.recalculos[0]?.cantidad_total;
      setAviso(
        total === undefined
          ? 'Trazo borrado.'
          : `Trazo borrado. Cantidad medida del nodo: ${fmtNum(total)}.`,
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
    } catch (err) {
      setAviso(err instanceof Error ? err.message : 'No se pudo borrar el trazo.');
    }
  }

  /** Mueve el trazo elegido `dx`, `dy` (unidades del plano); se deshace con el desplazamiento opuesto. */
  async function moverTrazo(id: string, dx: number, dy: number) {
    if (dx === 0 && dy === 0) return;
    try {
      await transformar.mutateAsync({ data: { trazo_ids: [id], dx, dy } });
      historial.registrar({
        etiqueta: 'trazo movido',
        deshacer: async () => {
          await transformar.mutateAsync({ data: { trazo_ids: [vigente(id)], dx: -dx, dy: -dy } });
        },
        rehacer: async () => {
          await transformar.mutateAsync({ data: { trazo_ids: [vigente(id)], dx, dy } });
        },
      });
      refrescarHistorial();
      setAviso('Trazo movido. Sus medidas no cambian.');
      invalidarTrazos();
    } catch (err) {
      setAviso(`No se pudo mover el trazo: ${err instanceof Error ? err.message : 'error'}`);
    }
  }

  /** Gira el trazo elegido `grados` (los del servidor) sobre su centro; el pivote devuelto permite deshacerlo exacto. */
  async function girarTrazo(id: string, grados: number) {
    if (grados === 0) return;
    try {
      const r = await transformar.mutateAsync({ data: { trazo_ids: [id], grados } });
      const pivote = r.trazos[0]?.pivote ?? null;
      historial.registrar({
        etiqueta: 'trazo girado',
        deshacer: async () => {
          await transformar.mutateAsync({
            data: { trazo_ids: [vigente(id)], grados: -grados, ...(pivote ? { pivote } : {}) },
          });
        },
        rehacer: async () => {
          await transformar.mutateAsync({
            data: { trazo_ids: [vigente(id)], grados, ...(pivote ? { pivote } : {}) },
          });
        },
      });
      refrescarHistorial();
      setAviso('Trazo girado. Sus medidas no cambian.');
      invalidarTrazos();
    } catch (err) {
      setAviso(`No se pudo girar el trazo: ${err instanceof Error ? err.message : 'error'}`);
    }
  }

  /** Una copia de la pieza elegida centrada en `p`: mismos enlaces, misma forma, sin abrir el cajón. */
  async function copiarPieza(p: Punto) {
    if (piezaElegida === null) return;
    const centro = centroDeLaPieza(piezaElegida.geometry);
    if (centro === null) return;
    const dx = p[0] - centro[0];
    const dy = p[1] - centro[1];
    const partes = partesDe(piezaElegida.geometry);
    const exterior = partes.find((x) => x.tipo === 'anillo' && !x.hueco);
    const wkt =
      piezaElegida.geometry.type === 'Point'
        ? aWkt('punto', [p])
        : exterior
          ? aWkt(
              'poligono',
              sinCierre(exterior.puntos).map((v) => [v[0] + dx, v[1] + dy] as Punto),
            )
          : null;
    if (wkt === null) return;
    const data = datosParaRecrear(piezaElegida, wkt);
    const planoId = planoElegido;
    try {
      const r = await registrarTrazo.mutateAsync({ planoId, data });
      copias.current += 1;
      let nuevoId = r.trazo_id;
      historial.registrar({
        etiqueta: 'copia de la pieza',
        deshacer: async () => {
          await eliminar.mutateAsync({ trazoId: vigente(nuevoId) });
        },
        rehacer: async () => {
          const otra = await registrarTrazo.mutateAsync({ planoId, data });
          alias.current.set(vigente(nuevoId), otra.trazo_id);
          nuevoId = otra.trazo_id;
        },
      });
      refrescarHistorial();
      setAviso(`Copia ${copias.current} hecha. Sigue dando clic para repetirla; Esc termina.`);
      invalidarTrazos();
    } catch (err) {
      setAviso(`No se pudo copiar la pieza: ${err instanceof Error ? err.message : 'error'}`);
    }
  }

  function limpiarDibujo() {
    setBorrador([]);
    setTramosContorno([]);
    setHuecoEnCurso([]);
    setFormaEstampada(null);
    setAGuardar(null);
  }

  function cambiarHerramienta(nueva: Herramienta) {
    if (nueva === 'hueco' && areaElegida === null) {
      setAviso('Para abrir un hueco, primero elige el área con la herramienta Seleccionar.');
      return;
    }
    if (nueva === 'copiar' && piezaElegida === null) {
      setAviso('Para copiar en lote, primero elige con Seleccionar el punto o la pieza que quieres repetir.');
      return;
    }
    if (nueva === 'mover' && seleccionado === null) {
      setAviso('Para mover, primero elige el trazo con Seleccionar.');
      return;
    }
    copias.current = 0;
    setHerramienta(nueva);
    limpiarDibujo();
    setCursor(null);
    setAviso(null);
    // Moverse, acercar y abrir un hueco no sueltan lo elegido: el hueco se abre sobre ello.
    if (nueva !== 'seleccionar' && nueva !== 'mano' && nueva !== 'zoom' && nueva !== 'hueco' && nueva !== 'copiar' && nueva !== 'mover' && nueva !== 'borrar') {
      setSeleccion(null);
    }
  }

  function alPunto(p: Punto) {
    setAviso(null);
    if (herramienta === 'nota') {
      if (claseDeNota === 'nota' || claseDeNota === 'texto') {
        setNotaPunto(p);
      } else if (borrador.length === 0) {
        setBorrador([p]); // el primer clic: el inicio de la flecha, o lo que señala la llamada
      } else if (claseDeNota === 'flecha') {
        setNotaPunto(borrador[0] as Punto);
        setNotaDestino(p);
      } else {
        setNotaPunto(p);
        setNotaDestino(borrador[0] as Punto);
      }
      return;
    }
    if (herramienta === 'copiar') {
      void copiarPieza(p);
      return;
    }
    if (herramienta === 'mover') {
      // Dos clics: el punto base y el destino. Al segundo se mueve y se vuelve a Seleccionar.
      const base = borrador[0];
      if (base === undefined) {
        setBorrador([p]);
      } else if (seleccionado !== null) {
        const id = seleccionado.id as string;
        cambiarHerramienta('seleccionar');
        void moverTrazo(id, p[0] - base[0], p[1] - base[1]);
      }
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
    if (herramienta === 'conteo_auto') {
      // Dos esquinas del símbolo que se busca; al segundo clic se hace la búsqueda.
      const siguiente = borrador.length >= 2 ? [p] : [...borrador, p];
      setBorrador(siguiente);
      if (siguiente.length === 2) setZonaDePlantilla([siguiente[0] as Punto, siguiente[1] as Punto]);
      return;
    }
    if (herramienta === 'enlace') {
      // Dos esquinas de la zona; al segundo clic se pide a dónde lleva.
      const siguiente = borrador.length >= 2 ? [p] : [...borrador, p];
      setBorrador(siguiente);
      if (siguiente.length === 2) setZonaDeEnlace([siguiente[0] as Punto, siguiente[1] as Punto]);
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
        cerrarTrazo('poligono', poligonoDeForma(p, formaPunto, unidadesPorMetro), formaPunto);
      } else {
        cerrarTrazo('punto', [p], null);
      }
      return;
    }
    if (forma === 'contorno') {
      // Un clic sobre el primer vértice (la referencia a objetos lo pega exacto) cierra el contorno.
      const primero = borrador[0];
      if (
        primero &&
        borrador.length >= 3 &&
        tramosContorno[tramosContorno.length - 1] !== 'am' &&
        Math.hypot(p[0] - primero[0], p[1] - primero[1]) < 1e-9
      ) {
        cerrarContorno();
        return;
      }
      if (borrador.length > 0) setTramosContorno([...tramosContorno, siguienteTramo(tramosContorno, modoContorno)]);
      setBorrador([...borrador, p]);
      return;
    }
    const clics = [...borrador, p];
    if (clicsDeLaForma !== undefined && clics.length >= clicsDeLaForma) {
      // Rectángulo, círculo, elipse, arco y línea terminan con su último clic.
      const hecha = formaDe(forma as HerramientaDeDibujo, clics, null, baseGrados);
      if (hecha) {
        setBorrador(clics);
        cerrarTrazo(hecha.tipo, hecha.puntos, null);
      }
      return;
    }
    setBorrador(clics);
  }

  /** Cierra el contorno: el último vértice se une al primero y lo dibujado es un área. */
  function cerrarContorno() {
    const anillo = contornoCerrado(borrador, tramosContorno);
    if (anillo) {
      cerrarTrazo('poligono', anillo, null);
    }
  }

  /**
   * Cierra una figura. Con un destino claro (concepto, matriz o medición activos) el trazo se guarda solo,
   * sin botón (D-588): la cantidad cambia al cerrar. Si falta destino o hay que elegir la medida, abre el cajón.
   */
  function cerrarTrazo(tipo: GeometriaBase, puntos: readonly Punto[], conForma: Forma | null) {
    const abrirCajon = () => {
      setAGuardar({ tipo, puntos });
      if (conForma) setFormaEstampada(conForma);
      setGuardando(true);
    };
    if (!plano) return abrirCajon();
    const conGrosor = tipo === 'linea' && grosorUsado !== null;
    const base = {
      versionPlano: plano.version,
      herramienta: tipo,
      puntos,
      grosorM: tipo === 'linea' ? grosorUsado : null,
      alineacion: conGrosor ? alineacion : null,
      pendientePct: tipo === 'linea' ? pendientePct : null,
      forma: conForma,
    };
    let data: TrazoPeticion | null = null;
    let factor = '1';
    if (medicionActiva) {
      if (motivoDeIncompatibilidad(medicionActiva.tipo, tipo, conForma !== null) === null) {
        data = trazoPeticion({ ...base, medicionId: medicionActiva.id, enlaces: [] });
      }
    } else if (conceptoEnFoco) {
      const medida = medidaDirecta(tipoDelConcepto, tipo, conGrosor, conForma !== null);
      if (medida) {
        factor = factorDeLaMedida(tipoDelConcepto, tipo, conGrosor, medida);
        data = trazoPeticion({
          ...base,
          enlaces: [{ actividadId: conceptoEnFoco, ...(matrizActiva ? { matrizId: matrizActiva.id } : {}), medida, factor }],
        });
      }
    }
    if (!data) return abrirCajon();
    const planoId = plano.id;
    const cuerpo = data;
    registrarTrazo.mutateAsync({ planoId, data: cuerpo }).then(
      (r) => {
        alGuardar(r, { planoId, data: cuerpo });
        if (factor !== '1') {
          // Una línea sobre un concepto en m²: se dice cómo se convirtió el largo en área, y que se puede cambiar.
          setAviso(
            `Línea medida como área: largo × ${ALTURA_POR_DEFECTO_M} m de altura × ${CARAS_POR_DEFECTO} caras. ` +
              `Cantidad medida del nodo: ${fmtNum(r.recalculos[0]?.cantidad_total)}. El factor se cambia en el detalle del trazo.`,
          );
        }
      },
      () => abrirCajon(),
    );
  }

  function quitarUltimoClic() {
    setBorrador((a) => a.slice(0, -1));
    setTramosContorno((t) => t.slice(0, -1));
  }

  function terminar() {
    if (forma === 'contorno') {
      cerrarContorno();
      return;
    }
    if (forma && forma !== 'punto' && trazoCompleto(GEOMETRIA_DE[forma as HerramientaDeDibujo], borrador)) {
      cerrarTrazo(GEOMETRIA_DE[forma as HerramientaDeDibujo], borrador, null);
    }
  }

  /**
   * La ayuda de dibujo: a dónde va de verdad el punto que se apunta. La referencia a objetos manda
   * (cierra exacto contra lo que ya hay); si no hay ninguna cerca, el ortogonal alinea el tramo al
   * ángulo de trabajo. Mayús invierte el ortogonal mientras se mantiene.
   */
  function asistir(bruto: Punto, porPixel: number) {
    const enCurso = herramienta === 'hueco' ? huecoEnCurso : borrador;
    const desde = enCurso.length > 0 ? (enCurso[enCurso.length - 1] as Punto) : null;
    const referencia = referenciasOn
      ? buscarReferencia(
          { geometrias: geometriasVisibles, enCurso: enCurso.length > 0 ? [enCurso] : [] },
          bruto,
          10 * porPixel,
          referencias,
          desde,
        )
      : null;
    if (referencia) return { punto: referencia.punto, referencia };
    if (desde && usaOrtogonal && ortogonal !== mayus.current) {
      return { punto: ajustarAngulo(desde, bruto, { pasoGrados, baseGrados }), referencia: null };
    }
    return { punto: bruto, referencia: null };
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
      const areaId = areaElegida.id;
      const wkt = aWkt('poligono', huecoEnCurso);
      let huecoId = r.hueco_id;
      historial.registrar({
        etiqueta: 'hueco abierto',
        deshacer: async () => {
          await quitarHueco.mutateAsync({ trazoId: vigente(areaId), huecoId });
        },
        rehacer: async () => {
          const nuevo = await agregarHueco.mutateAsync({ trazoId: vigente(areaId), data: { geometria_wkt: wkt } });
          huecoId = nuevo.hueco_id;
        },
      });
      refrescarHistorial();
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
    const dibujando = forma !== null || herramienta === 'hueco' || herramienta === 'copiar' || herramienta === 'mover' || herramienta === 'nota';
    if (!dibujando || guardando || subiendoPlano || notaPunto !== null || reemplazando !== null) return;
    function alTeclear(e: KeyboardEvent) {
      const destino = e.target as HTMLElement | null;
      if (destino && /^(INPUT|SELECT|TEXTAREA)$/.test(destino.tagName)) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        if (herramienta === 'hueco') void cerrarHueco();
        else terminar();
      } else if (e.key === 'Backspace') {
        e.preventDefault();
        if (herramienta === 'hueco') setHuecoEnCurso((actual) => actual.slice(0, -1));
        else quitarUltimoClic();
      } else if (e.key.toLowerCase() === 't' && herramienta === 'contorno') {
        setModoContorno((m) => (m === 'recto' ? 'arco' : 'recto'));
      } else if (e.key === 'Escape') {
        if (herramienta === 'copiar' || (herramienta === 'mover' && borrador.length === 0)) {
          cambiarHerramienta('seleccionar');
        } else limpiarDibujo();
      }
    }
    window.addEventListener('keydown', alTeclear);
    return () => window.removeEventListener('keydown', alTeclear);
    // `cerrarHueco` y `limpiarDibujo` leen estado del render: se rearma con él.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forma, herramienta, borrador, huecoEnCurso, guardando, subiendoPlano, notaPunto, reemplazando, areaElegida]);

  function alGuardar(
    resultado: TrazoRespuesta,
    solicitud: { readonly planoId: string; readonly data: TrazoPeticion },
  ) {
    const original = resultado.trazo_id;
    historial.registrar({
      etiqueta: 'trazo guardado',
      deshacer: async () => {
        await eliminar.mutateAsync({ trazoId: vigente(original) });
      },
      rehacer: () => recrear(original, solicitud.planoId, solicitud.data),
    });
    refrescarHistorial();
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
    void queryClient.invalidateQueries({
      queryKey: getListarMedicionesApiV1PlanosPlanoIdMedicionesGetQueryKey(planoElegido),
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
  /** Lo que la pestaña «Trazos» necesita para nombrar y colorear cada trazo. */
  const opcionesDeLaListaDeTrazos = {
    nombreDeNodo,
    nombreDeMedicion: (id: string) => listaDeMediciones.find((m) => m.id === id)?.nombre,
    colorDe: (f: (typeof features)[number]) => {
      const deMedicion = f.properties.medicion_id ? coloresDeMedicion.get(f.properties.medicion_id) : undefined;
      const concepto = f.properties.enlaces.find((e) => e.vigente && e.tipo_nodo !== 'prototipo_nodo')?.nodo_id;
      return deMedicion ?? (concepto ? colorDeConcepto(concepto) : undefined);
    },
  };
  const arbol = useMemo(
    () => arbolDeCuantificacion(actividades, estado.data ?? []),
    [actividades, estado.data],
  );

  const conceptoEnFoco = conceptoActivo ?? actividadFocoId;
  const filaDeFoco = conceptoEnFoco
    ? (estado.data ?? []).find((n) => n.nodo_id === conceptoEnFoco)
    : undefined;
  const actividadDeFoco = conceptoEnFoco ? porActividad.get(conceptoEnFoco) : undefined;
  /** El tipo de medición que pide el concepto en foco (por su unidad) y el bloque de herramientas que le toca. */
  const tipoDelConcepto = tipoDeMedicion(matrizActiva ? matrizActiva.unidad : actividadDeFoco?.unidad);
  const unidadEnFoco = matrizActiva ? matrizActiva.unidad : actividadDeFoco?.unidad;
  // Con una medición activa manda su tipo; si no, el del concepto que se mide.
  const bloqueActivo = medicionActiva ? medicionActiva.tipo : bloqueDeTipo(tipoDelConcepto);
  // Un concepto lineal (ml: bastones, trabes) mide el largo de la línea: el grosor que haya quedado en las opciones
  // solo vale para un muro (m²) y no debe volver «muro» lo que se traza para medir largo.
  const grosorUsado = (medicionActiva ? medicionActiva.tipo : tipoDelConcepto) === 'lineal' ? null : grosorM;

  const herramientasDisponibles: readonly Herramienta[] = puedeAnotar
    ? [...HERRAMIENTAS, HERRAMIENTA_NOTA]
    : HERRAMIENTAS;

  function alternar(clave: ClaveDeInterruptor) {
    if (clave === 'medidas') setMostrarMedidas(!mostrarMedidas);
    else if (clave === 'cotas') setMostrarCotas(!mostrarCotas);
    else if (clave === 'datos') setDatosAbiertos(!datosAbiertos);
    else if (clave === 'volumen') abrirVolumen();
    else if (clave === 'takeoff') setTakeoffAbierto(fondoUrl !== null && !takeoffAbierto);
    else if (clave === 'escalaAuto') setProponiendoEscala(esPdf && archivo.data?.url !== undefined);
    else if (clave === 'empalme') {
      if (versionesPrevias.length > 0 || empalmeAbierto) setEmpalmeAbierto(!empalmeAbierto);
    }
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
    {
      clave: 'takeoff',
      activo: takeoffAbierto,
      deshabilitado: fondoUrl === null,
      descripcion:
        fondoUrl !== null
          ? 'Takeoff automático: propone áreas y muros que encuentra en la imagen (por revisar)'
          : 'El takeoff automático busca en la imagen del plano: este plano no tiene una (imagen o PDF)',
    },
    {
      clave: 'escalaAuto',
      activo: proponiendoEscala,
      deshabilitado: !esPdf || archivo.data?.url === undefined,
      descripcion: esPdf
        ? 'Proponer la escala que dice la hoja (la confirmas tú)'
        : 'La escala automática lee el texto de un plano en PDF',
    },
    {
      clave: 'empalme',
      activo: empalmeAbierto,
      deshabilitado: versionesPrevias.length === 0 && !empalmeAbierto,
      descripcion:
        versionesPrevias.length > 0 || empalmeAbierto
          ? 'Empalmar la versión anterior del plano: verla de fantasma, alinearla y traer sus trazos'
          : 'Este plano no tiene una versión anterior que empalmar',
    },
  ];

  // Para escribir «clave y concepto · matriz · medición» sobre cada medida se necesitan los nombres de las matrices
  // de los conceptos que aparecen en los trazos; solo se piden con «Mostrar medidas» encendido.
  const actividadesConMatriz = useMemo(
    () =>
      mostrarMedidas
        ? [...new Set(featuresVisibles.flatMap((f) => f.properties.enlaces.filter((e) => e.matriz_concepto_id).map((e) => e.nodo_id)))]
        : [],
    [mostrarMedidas, featuresVisibles],
  );
  const datosDeMatriz = useQueries({
    queries: actividadesConMatriz.map((id) =>
      getMatricesDeLaActividadApiV1ActividadesActividadIdMatricesGetQueryOptions(id),
    ),
    combine: (resultados) => {
      const nombres = new Map<string, { nombre: string; unidad: string | null }>();
      for (const r of resultados) {
        const datos = r.data as unknown as
          | { matrices?: readonly { concepto_id: string; clave: string; descripcion: string; unidad?: string | null }[] }
          | undefined;
        for (const m of datos?.matrices ?? []) {
          nombres.set(m.concepto_id, { nombre: `${m.clave} ${m.descripcion}`.trim(), unidad: m.unidad ?? null });
        }
      }
      return nombres;
    },
  });
  /** «EST-10101 LOSA ENTREPISO 3.00 · MOE-10001 MO LOSA MACIZA · RECAMARA 1»: a qué concepto, matriz y medición pertenece el trazo. */
  const tituloDelTrazo = (f: (typeof features)[number]): string | undefined => {
    const enlace = f.properties.enlaces.find((e) => e.vigente && e.tipo_nodo !== 'prototipo_nodo');
    const medicion = f.properties.medicion_id ? listaDeMediciones.find((m) => m.id === f.properties.medicion_id) : undefined;
    const asignada = medicion?.asignaciones[0];
    const actividad = enlace ? porActividad.get(enlace.nodo_id) : undefined;
    const concepto = actividad
      ? `${actividad.concepto_clave ?? ''} ${actividad.descripcion ?? ''}`.trim()
      : asignada
        ? `${asignada.concepto_clave} ${asignada.descripcion}`.trim()
        : '';
    const matriz = enlace?.matriz_concepto_id
      ? (datosDeMatriz.get(enlace.matriz_concepto_id)?.nombre ?? '')
      : (asignada?.matriz_clave ?? '');
    const partes = [concepto, matriz, medicion?.nombre ?? ''].filter((x) => x !== '');
    return partes.length > 0 ? partes.join(' · ') : undefined;
  };
  /** Lo que el trazo cuenta para su concepto o matriz, con la unidad de ese concepto: «2.40 m3», no la medida geométrica. */
  const valorDelTrazo = (f: (typeof features)[number]): string | undefined => {
    // Sin calibrar la cantidad está en unidades de plano: ponerle la unidad del concepto (m2) sería mentir; se queda en u².
    if (escalaDelPlano === null) return undefined;
    const enlace = f.properties.enlaces.find((e) => e.vigente && e.tipo_nodo !== 'prototipo_nodo');
    if (!enlace) return undefined;
    const unidad = enlace.matriz_concepto_id
      ? datosDeMatriz.get(enlace.matriz_concepto_id)?.unidad
      : porActividad.get(enlace.nodo_id)?.unidad;
    return unidad ? `${fmtMedida(Number(enlace.cantidad))} ${unidad}` : undefined;
  };
  const etiquetas = useMemo(
    () =>
      mostrarMedidas
        ? (() => {
            // Se numeran las piezas contadas con la herramienta Punto (un punto o una forma
            // estampada), en el orden en que se hicieron; los vértices de un trazo no cuentan.
            let siguiente = 0;
            return featuresVisibles.flatMap((f) => {
              const esPunto = f.geometry.type === 'Point' || f.properties.forma != null;
              return etiquetasDeMedidas(
                f.geometry,
                escalaDelPlano,
                f.properties.grosor_m != null ? Number(f.properties.grosor_m) : null,
                esPunto ? (siguiente += 1) : null,
                f.properties.pendiente_pct,
                {
                  ...(tituloDelTrazo(f) ? { titulo: tituloDelTrazo(f) as string } : {}),
                  ...(valorDelTrazo(f) ? { valor: valorDelTrazo(f) as string } : {}),
                  ...(f.properties.medicion_id && coloresDeMedicion.has(f.properties.medicion_id)
                    ? { color: coloresDeMedicion.get(f.properties.medicion_id) as string }
                    : {}),
                },
              );
            });
          })()
        : [],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mostrarMedidas, featuresVisibles, escalaDelPlano, datosDeMatriz, listaDeMediciones, coloresDeMedicion, porActividad],
  );
  const cotas = useMemo(
    () => (mostrarCotas ? featuresVisibles.flatMap((f) => cotasDe(f.geometry, escalaDelPlano, f.properties.pendiente_pct)) : []),
    [mostrarCotas, featuresVisibles, escalaDelPlano],
  );
  const resumen = useMemo(
    () => resumenDePantalla(featuresVisibles as unknown as readonly TrazoParaResumen[], escalaDelPlano),
    [featuresVisibles, escalaDelPlano],
  );
  /** Estas herramientas se ven como la línea que une sus clics; las demás, como la forma que resultaría. */
  const polilineaEnCurso = forma === 'poligono' || forma === 'polilinea' || forma === 'linea';
  const previa =
    forma && forma !== 'punto' && borrador.length > 0
      ? formaDe(forma as HerramientaDeDibujo, borrador, cursor, baseGrados, tramosContorno)
      : null;
  const bandaEnCurso =
    (forma === 'linea' || forma === 'polilinea') && grosorUsado !== null && previa && previa.puntos.length >= 2
      ? bandaDeLinea(previa.puntos, grosorUsado * unidadesPorMetro, alineacion)
      : [];
  const fantasma = (() => {
    if (forma === 'punto' && formaPunto !== null && cursor !== null) {
      return poligonoDeForma(cursor, formaPunto, unidadesPorMetro);
    }
    // Copiar en lote: el contorno de la pieza elegida, siguiendo al cursor.
    if (herramienta === 'copiar' && piezaElegida !== null && cursor !== null) {
      const centro = centroDeLaPieza(piezaElegida.geometry);
      const anillo = partesDe(piezaElegida.geometry).find((x) => x.tipo === 'anillo' && !x.hueco);
      if (centro && anillo) {
        return sinCierre(anillo.puntos).map((v) => [v[0] + cursor[0] - centro[0], v[1] + cursor[1] - centro[1]] as Punto);
      }
    }
    // Mover: el contorno del trazo elegido, desplazado lo que va del punto base al cursor.
    if (herramienta === 'mover' && seleccionado !== null && borrador[0] !== undefined && cursor !== null) {
      const anillo = partesDe(seleccionado.geometry).find((x) => x.tipo === 'anillo' && !x.hueco);
      if (anillo) {
        const dx = cursor[0] - borrador[0][0];
        const dy = cursor[1] - borrador[0][1];
        return sinCierre(anillo.puntos).map((v) => trasladar(v, dx, dy));
      }
    }
    return [];
  })();
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
  const hayCajon =
    guardando || subiendoPlano || notaPunto !== null || reemplazando !== null || calibrando || porBorrar !== null;
  useEffect(() => {
    if (hayCajon) return;
    function alTeclear(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const destino = e.target as HTMLElement | null;
      if (destino && /^(INPUT|SELECT|TEXTAREA)$/.test(destino.tagName)) return;
      if (destino?.isContentEditable) return;
      if ((e.key === 'Delete' || e.key === 'Backspace') && seleccionado && herramienta !== 'poligono' && herramienta !== 'linea' && herramienta !== 'hueco') {
        e.preventDefault();
        setPorBorrar(seleccionado.id);
        return;
      }
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
  }, [hayCajon, puedeAnotar, borrador, areaElegida, seleccionado, herramienta, mostrarMedidas, mostrarCotas, datosAbiertos]);

  // Al cambiar de plano se olvida lo que se podía deshacer y la medición activa: ya no es lo que se está viendo.
  useEffect(() => {
    setMedicionActivaId(null);
    historial.limpiar();
    alias.current.clear();
    refrescarHistorial();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planoElegido]);

  // Ctrl+Z deshace (con un trazo a medias, quita su último vértice); Ctrl+Y o Ctrl+Mayús+Z rehace.
  useEffect(() => {
    function alTeclear(e: KeyboardEvent) {
      if (!(e.ctrlKey || e.metaKey)) return;
      const destino = e.target as HTMLElement | null;
      if (destino && /^(INPUT|SELECT|TEXTAREA)$/.test(destino.tagName)) return;
      if (hayCajon) return;
      const tecla = e.key.toLowerCase();
      if (tecla === 'z' && !e.shiftKey) {
        e.preventDefault();
        if (herramienta === 'hueco' && huecoEnCurso.length > 0) setHuecoEnCurso((a) => a.slice(0, -1));
        else if (forma && borrador.length > 0) quitarUltimoClic();
        else void deshacerUltimo();
      } else if (tecla === 'y' || (tecla === 'z' && e.shiftKey)) {
        e.preventDefault();
        void rehacerUltimo();
      }
    }
    window.addEventListener('keydown', alTeclear);
    return () => window.removeEventListener('keydown', alTeclear);
    // Los manejadores leen el estado de este render: se rearma con él.
     
  });

  // Mayús invierte el ortogonal mientras se mantiene; F8 y F3 encienden y apagan ortogonal y referencia.
  useEffect(() => {
    const suelta = () => {
      mayus.current = false;
    };
    function alApretar(e: KeyboardEvent) {
      if (e.key === 'Shift') mayus.current = true;
      else if (e.key === 'F8') {
        e.preventDefault();
        setOrtogonal((v) => !v);
      } else if (e.key === 'F3') {
        e.preventDefault();
        setReferenciasOn((v) => !v);
      }
    }
    function alSoltar(e: KeyboardEvent) {
      if (e.key === 'Shift') mayus.current = false;
    }
    window.addEventListener('keydown', alApretar);
    window.addEventListener('keyup', alSoltar);
    window.addEventListener('blur', suelta);
    return () => {
      window.removeEventListener('keydown', alApretar);
      window.removeEventListener('keyup', alSoltar);
      window.removeEventListener('blur', suelta);
    };
  }, []);

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
        {pestana === 'trabajos' && trabajoElegido && puedeVerTrabajos
          ? trabajoElegido.tipo === 'cuadrilla'
            ? 'Trabajo · cuadrilla'
            : 'Trabajo · destajo'
          : seleccionado
          ? 'Trazo elegido'
          : notaElegida
            ? `${NOMBRE_DE_ANOTACION[notaElegida.tipo ?? 'nota']} elegida`
            : 'Trazos del plano'}
      </div>
      <div className="estacion__detalle-cuerpo col">
        {pestana === 'trabajos' && trabajoElegido && puedeVerTrabajos ? (
          <EditorDeTrabajo
            elegido={trabajoElegido}
            trabajos={listaDeTrabajos}
            cuadrillasDeLaObra={cuadrillasDeLaObra}
            cuadrillasDelCatalogo={cuadrillasDelCatalogo}
            medidaPorActividad={medidaPorActividad}
            puedeEditar={puedeEditarTrabajos}
            onCambio={(mensaje) => {
              void trabajosConsulta.refetch();
              void cuadrillasConsulta.refetch();
              setAviso(mensaje);
            }}
            onError={(m) => setAviso(m)}
            onVerConcepto={(actividadId) => {
              setPestana('presupuesto');
              setConceptoActivo(actividadId);
            }}
          />
        ) : notaElegida ? (
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
            <SelectorDeMedicion
              trazo={seleccionado}
              mediciones={listaDeMediciones}
              ocupado={meterEnMedicion.isPending}
              onCambiar={(medicionId) =>
                meterEnMedicion.mutate(
                  { trazoId: seleccionado.id, data: { medicion_id: medicionId } },
                  {
                    onSuccess: () => {
                      setAviso(medicionId ? 'Trazo metido en la medición.' : 'Trazo fuera de su medición: ya no suma por ella.');
                      invalidarTrazos();
                    },
                    onError: (err) => setAviso(err.message),
                  },
                )
              }
            />
            {seleccionado.geometry.type === 'LineString' && (
              <VanosDelTrazo
                trazoId={seleccionado.id as string}
                puedeEditar
                onCambio={(aviso) => {
                  setAviso(aviso);
                  invalidarTrazos();
                }}
                onError={(m) => setAviso(m)}
              />
            )}
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
      <div className="estacion__pestanas" role="tablist" aria-label="Panel lateral">
        <button
          type="button"
          role="tab"
          id="pestana-presupuesto"
          aria-selected={pestana === 'presupuesto'}
          aria-controls="panel-presupuesto"
          className={pestana === 'presupuesto' ? 'estacion__pestana is-activa' : 'estacion__pestana'}
          onClick={() => setPestana('presupuesto')}
        >
          Presupuesto
        </button>
        <button
          type="button"
          role="tab"
          id="pestana-planos"
          aria-selected={pestana === 'planos'}
          aria-controls="panel-planos"
          className={pestana === 'planos' ? 'estacion__pestana is-activa' : 'estacion__pestana'}
          onClick={() => setPestana('planos')}
        >
          Planos <span className="estacion__contador">{listaDePlanos.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          id="pestana-mediciones"
          aria-selected={pestana === 'mediciones'}
          aria-controls="panel-mediciones"
          className={pestana === 'mediciones' ? 'estacion__pestana is-activa' : 'estacion__pestana'}
          onClick={() => setPestana('mediciones')}
        >
          Mediciones <span className="estacion__contador">{listaDeMediciones.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          id="pestana-trazos"
          aria-selected={pestana === 'trazos'}
          aria-controls="panel-trazos"
          className={pestana === 'trazos' ? 'estacion__pestana is-activa' : 'estacion__pestana'}
          onClick={() => setPestana('trazos')}
        >
          Trazos <span className="estacion__contador">{features.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          id="pestana-elementos"
          aria-selected={pestana === 'elementos'}
          aria-controls="panel-elementos"
          className={pestana === 'elementos' ? 'estacion__pestana is-activa' : 'estacion__pestana'}
          onClick={() => setPestana('elementos')}
        >
          Elementos <span className="estacion__contador">{listaDeElementos.length}</span>
        </button>
        {puedeVerTrabajos && (
          <button
            type="button"
            role="tab"
            id="pestana-trabajos"
            aria-selected={pestana === 'trabajos'}
            aria-controls="panel-trabajos"
            className={pestana === 'trabajos' ? 'estacion__pestana is-activa' : 'estacion__pestana'}
            onClick={() => setPestana('trabajos')}
          >
            Trabajos <span className="estacion__contador">{listaDeTrabajos.length}</span>
          </button>
        )}
        {puedePonerPeso && (
          <button
            type="button"
            role="tab"
            id="pestana-arbol"
            aria-selected={pestana === 'arbol'}
            aria-controls="panel-arbol"
            className={pestana === 'arbol' ? 'estacion__pestana is-activa' : 'estacion__pestana'}
            onClick={() => setPestana('arbol')}
          >
            Árbol
          </button>
        )}
      </div>
      {pestana === 'arbol' && puedePonerPeso ? (
        <div role="tabpanel" id="panel-arbol" aria-labelledby="pestana-arbol" className="estacion__panel-pestana">
          <>
          <div className="estacion__subencabezado">
            <span className="estacion__subtitulo">Conceptos de la obra</span>
            <AltaDeConcepto
              obraId={obraId}
              onError={(m) => setAviso(m)}
              onCreado={(actividadId, claveNueva) => {
                void queryClient.invalidateQueries({
                  queryKey: getEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGetQueryKey(obraId),
                });
                void queryClient.invalidateQueries({
                  queryKey: getActividadesDeObraApiV1ObrasObraIdActividadesGetQueryKey(obraId),
                });
                setMatrizActiva(null);
                setConceptoActivo(actividadId);
                setAviso(`Concepto ${claveNueva} creado: llega sin cantidad, se mide en el plano.`);
              }}
            />
          </div>
          <PanelDelArbol
            obraId={obraId}
            actividades={actividades}
            onCambio={(aviso) => {
              setAviso(aviso);
              void queryClient.invalidateQueries({
                queryKey: getActividadesDeObraApiV1ObrasObraIdActividadesGetQueryKey(obraId),
              });
              void queryClient.invalidateQueries({
                queryKey: getEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGetQueryKey(obraId),
              });
            }}
            onError={(m) => setAviso(m)}
          />
          </>
        </div>
      ) : pestana === 'trazos' ? (
        <div role="tabpanel" id="panel-trazos" aria-labelledby="pestana-trazos" className="estacion__panel-pestana">
          <TrazosDelPlano
            trazos={features}
            elegidoId={seleccion?.tipo === 'trazo' ? seleccion.id : null}
            opciones={opcionesDeLaListaDeTrazos}
            onElegir={(trazoId) => setSeleccion({ tipo: 'trazo', id: trazoId })}
          />
        </div>
      ) : pestana === 'trabajos' && puedeVerTrabajos ? (
        <div role="tabpanel" id="panel-trabajos" aria-labelledby="pestana-trabajos" className="estacion__panel-pestana">
          <PanelDeTrabajos
            trabajos={listaDeTrabajos}
            medidaPorActividad={medidaPorActividad}
            elegido={trabajoElegido}
            cargando={trabajosConsulta.isLoading}
            onElegir={setTrabajoElegido}
          />
        </div>
      ) : pestana === 'elementos' ? (
        <div role="tabpanel" id="panel-elementos" aria-labelledby="pestana-elementos" className="estacion__panel-pestana">
          <PanelDeElementos
            elementos={listaDeElementos}
            puedePonerPeso={puedePonerPeso}
            onCambio={(aviso) => {
              void elementosConsulta.refetch();
              if (aviso) setAviso(aviso);
            }}
            onError={(m) => setAviso(m)}
          />
        </div>
      ) : pestana === 'mediciones' ? (
        <div role="tabpanel" id="panel-mediciones" aria-labelledby="pestana-mediciones" className="estacion__panel-pestana">
          <PanelDeMediciones
            planoId={planoElegido}
            mediciones={listaDeMediciones}
            cargando={medicionesConsulta.isLoading}
            actividades={actividades}
            elementos={listaDeElementos}
            conceptoEnFoco={conceptoEnFoco}
            destino={
              conceptoEnFoco
                ? {
                    actividadId: conceptoEnFoco,
                    ...(matrizActiva ? { matrizId: matrizActiva.id } : {}),
                    nombre: matrizActiva
                      ? `${matrizActiva.clave}`
                      : `${actividadDeFoco?.concepto_clave ?? ''} ${actividadDeFoco?.descripcion ?? ''}`.trim(),
                    unidad: unidadEnFoco ?? null,
                  }
                : null
            }
            onPedirDestino={() => setPestana('presupuesto')}
            activaId={medicionActivaId}
            onActivar={(m) => {
              setMedicionActivaId(m ? m.id : null);
              // Dibujar en una medición pide su tipo: se suelta lo que se estaba trazando.
              limpiarDibujo();
            }}
            onCambio={(aviso) => {
              if (aviso) setAviso(aviso);
              void queryClient.invalidateQueries({
                queryKey: getListarMedicionesApiV1PlanosPlanoIdMedicionesGetQueryKey(planoElegido),
              });
              void queryClient.invalidateQueries({ queryKey: getListarElementosApiV1ElementosGetQueryKey() });
              invalidarTrazos();
            }}
            onError={(mensaje) => setAviso(mensaje)}
          />
        </div>
      ) : pestana === 'planos' ? (
        <div role="tabpanel" id="panel-planos" aria-labelledby="pestana-planos" className="estacion__panel-pestana">
          <NavegadorDePlanos
            planos={listaDePlanos}
            cargando={planos.isLoading}
            activoId={planoElegido}
            onElegir={(id) => {
              setPlanoElegido(id);
              setBorrador([]);
              setSeleccion(null);
            }}
            onSubir={() => setSubiendoPlano(true)}
          />
        </div>
      ) : (
      <div role="tabpanel" id="panel-presupuesto" aria-labelledby="pestana-presupuesto" className="estacion__panel-pestana">
      <div className="estacion__subencabezado">
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
          actividadFocoId={conceptoEnFoco}
          onActivar={(id) => {
            setMatrizActiva(null);
            setConceptoActivo((actual) => (actual === id && !matrizActiva ? null : id));
          }}
          matrizActivaId={matrizActiva?.id ?? null}
          onActivarMatriz={(actividadId, m) => {
            if (matrizActiva?.id === m.id && conceptoActivo === actividadId) {
              setMatrizActiva(null);
              return;
            }
            setConceptoActivo(actividadId);
            setMatrizActiva(m);
          }}
        />
      )}
      </div>
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

  /** La barra se divide en dos: TRAZO (en el plano, lo que se dibuja) y FUNCIONES (en la cabecera, lo demás). */
  const barra = (cual: 'trazo' | 'funciones') => {
    const Barra = cual === 'trazo' ? BarraDeTrazo : BarraDeFunciones;
    return (
      <Barra
            herramientas={herramientasDisponibles}
            activa={herramienta}
            onElegir={cambiarHerramienta}
            deshabilitadas={{
              ...(areaElegida === null
                ? { hueco: 'Para abrir un hueco, primero elige el área con Seleccionar' }
                : {}),
              ...(fondoUrl === null
                ? { conteo_auto: 'El conteo automático busca en la imagen del plano: este plano no tiene una (imagen o PDF)' }
                : {}),
              ...(seleccionado === null ? { mover: 'Para mover, primero elige el trazo con Seleccionar' } : {}),
              ...(piezaElegida === null
                ? { copiar: 'Para copiar en lote, primero elige con Seleccionar el punto o la pieza que quieres repetir' }
                : {}),
            }}
            interruptores={interruptores}
            bloqueActivo={bloqueActivo}
            historial={[
              {
                clave: 'deshacer',
                etiqueta: 'Deshacer',
                deshabilitado: historial.siguienteAdeshacer() === null || trabajandoHistorial,
                descripcion: historial.siguienteAdeshacer()
                  ? `Deshacer: ${historial.siguienteAdeshacer()?.etiqueta} (Ctrl+Z)`
                  : 'Nada que deshacer',
                onClick: () => void deshacerUltimo(),
              },
              {
                clave: 'rehacer',
                etiqueta: 'Rehacer',
                deshabilitado: historial.siguienteArehacer() === null || trabajandoHistorial,
                descripcion: historial.siguienteArehacer()
                  ? `Rehacer: ${historial.siguienteArehacer()?.etiqueta} (Ctrl+Y)`
                  : 'Nada que rehacer',
                onClick: () => void rehacerUltimo(),
              },
            ]}
            acciones={[
              {
                clave: 'eliminar',
                etiqueta: 'Eliminar selección',
                deshabilitado: seleccionado === null,
                descripcion:
                  seleccionado === null
                    ? 'Elige un trazo con Seleccionar para poder eliminarlo'
                    : 'Eliminar el trazo elegido (Supr)',
                onClick: () => seleccionado && setPorBorrar(seleccionado.id),
              },
            ]}
            vista={[
              {
                clave: 'girarIzquierda',
                etiqueta: 'Girar el plano a la izquierda',
                descripcion: 'Girar el plano 90° a la izquierda (solo la vista)',
                onClick: () => cambiarVista(girar(vistaDelPlano, false)),
              },
              {
                clave: 'girarDerecha',
                etiqueta: 'Girar el plano a la derecha',
                descripcion: 'Girar el plano 90° a la derecha (solo la vista)',
                onClick: () => cambiarVista(girar(vistaDelPlano, true)),
              },
              {
                clave: 'voltearH',
                etiqueta: 'Voltear el plano de izquierda a derecha',
                activo: vistaDelPlano.volteoH,
                descripcion: 'Voltear el plano en espejo, de izquierda a derecha (solo la vista)',
                onClick: () => cambiarVista({ ...vistaDelPlano, volteoH: !vistaDelPlano.volteoH }),
              },
              {
                clave: 'voltearV',
                etiqueta: 'Voltear el plano de arriba abajo',
                activo: vistaDelPlano.volteoV,
                descripcion: 'Voltear el plano en espejo, de arriba abajo (solo la vista)',
                onClick: () => cambiarVista({ ...vistaDelPlano, volteoV: !vistaDelPlano.volteoV }),
              },
            ]}
            onAlternar={alternar}
            orientacion={compacto ? 'horizontal' : 'vertical'}
      />
    );
  };

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
        {plano !== undefined && barra('funciones')}
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

      {conceptoEnFoco && (
        <div className="cuant__renglon" data-testid="renglon-foco">
          <div>
            <div className="text-xs text-mute">Actividad</div>
            <div className="text-sm">
              <strong>{etiquetaActividad(actividadDeFoco, conceptoEnFoco)}</strong>
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
              {barra('trazo')}

              <div className="estacion__ayudas">
        {ayudasAbiertas && asistida && herramienta !== 'escala' && (
          <AyudasDeDibujo
            ortogonal={ortogonal}
            onOrtogonal={setOrtogonal}
            pasoGrados={pasoGrados}
            onPaso={setPasoGrados}
            baseGrados={baseGrados}
            onBase={setBaseGrados}
            referenciasOn={referenciasOn}
            onReferenciasOn={setReferenciasOn}
            referencias={referencias}
            onReferencia={(tipo, on) => setReferencias((r) => ({ ...r, [tipo]: on }))}
          />
        )}
              </div>

              <div className="estacion__paneles">
                {(herramienta === 'linea' ||
                  herramienta === 'polilinea' ||
                  herramienta === 'arco' ||
                  herramienta === 'rectangulo_l' ||
                  herramienta === 'circulo_l' ||
                  herramienta === 'elipse_l' ||
                  herramienta === 'punto') && (
                  <OpcionesDeHerramienta
                    herramienta={herramienta === 'punto' ? 'punto' : 'linea'}
                    grosorM={grosorM}
                    onGrosor={setGrosorM}
                    pendientePct={pendientePct}
                    onPendiente={setPendientePct}
                    alineacion={alineacion}
                    onAlineacion={setAlineacion}
                    forma={formaPunto}
                    onForma={setFormaPunto}
                    contornoElegido={contornoElegido}
                  />
                )}
                {herramienta === 'contorno' && <OpcionesDeContorno modo={modoContorno} onModo={setModoContorno} />}
                {propuestasDelPlano.length > 0 && (
                  <PanelDePropuestas
                    total={propuestasDelPlano.length}
                    elegidas={propuestasElegidas.length}
                    resumen={resumenDePropuestas}
                    trabajando={aceptarPropuestas.isPending || rechazarPropuestas.isPending}
                    onAceptar={() => void resolverPropuestas('aceptar')}
                    onRechazar={() => void resolverPropuestas('rechazar')}
                    onElegirTodas={() => setPropuestasDescartadas(new Set())}
                  />
                )}
                {empalmeAbierto && empalmeVersion && (
                  <OpcionesDeEmpalme
                    versiones={versionesPrevias}
                    versionId={empalmeVersion.id}
                    onVersion={(id) => {
                      setEmpalmeVersionId(id);
                      setFantasmaElegido(null);
                    }}
                    dx={empalmeDx}
                    dy={empalmeDy}
                    onDesfase={(x, y) => {
                      setEmpalmeDx(x);
                      setEmpalmeDy(y);
                    }}
                    porTraer={fantasmasPorTraer.length}
                    elegido={fantasmaElegido !== null}
                    trabajando={trayendo}
                    onTraerElegido={() => fantasmaElegido && void traerFantasmas([fantasmaElegido])}
                    onTraerTodos={() => void traerFantasmas(fantasmasPorTraer.map((f) => f.id))}
                    onCerrar={() => setEmpalmeAbierto(false)}
                    opacidad={empalmeOpacidad}
                    onOpacidad={setEmpalmeOpacidad}
                  />
                )}
                {herramienta === 'nota' && (
                  <OpcionesDeNota
                    clase={claseDeNota}
                    onClase={(c) => {
                      setClaseDeNota(c);
                      setBorrador([]);
                    }}
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
                  mediciones={listaDeMediciones}
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
                vistaDelPlano={vistaDelPlano}
                fondoUrl={fondoUrl}
                trazos={trazosVisibles}
                empalme={empalmeAbierto ? fantasmasPorTraer.map((f) => ({ id: f.id, geometry: f.geometry })) : undefined}
                empalmeDesfase={[desfaseDeTexto(empalmeDx), desfaseDeTexto(empalmeDy)]}
                empalmeElegidoId={fantasmaElegido}
                empalmeOpacidad={empalmeOpacidad / 100}
                onElegirFantasma={setFantasmaElegido}
                enlaces={enlacesVisibles}
                propuestas={[
                  ...propuestasDelPlano.map((f) => ({ id: f.id, geometry: f.geometry, elegida: !propuestasDescartadas.has(f.id) })),
                  ...previasAuto.map((g, i) => ({ id: `previa-${i}`, geometry: g, elegida: true })),
                ]}
                onAlternarPropuesta={(id) =>
                  !id.startsWith('previa-') &&
                  setPropuestasDescartadas((d) => {
                    const n = new Set(d);
                    if (n.has(id)) n.delete(id);
                    else n.add(id);
                    return n;
                  })
                }
                onUsarEnlace={usarEnlace}
                notas={notasVisibles}
                seleccion={seleccion}
                herramienta={herramienta}
                borrador={polilineaEnCurso ? borrador : []}
                marcas={polilineaEnCurso ? [] : borrador}
                previa={previa}
                asistir={asistida ? asistir : undefined}
                huecoEnCurso={huecoEnCurso}
                bandaEnCurso={bandaEnCurso}
                fantasma={fantasma}
                etiquetas={etiquetas}
                cotas={cotas}
                onMover={asistida ? setCursor : undefined}
                onPunto={alPunto}
                onSeleccionar={alElegirEnElPlano}
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
          {seleccionado !== null && (herramienta === 'seleccionar' || herramienta === 'mover') && (
            <div className="estacion__dibujo row" role="group" aria-label="Mover y girar el trazo">
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => cambiarHerramienta('mover')}>
                Mover
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                aria-label="Girar 90° a la izquierda"
                onClick={() => void girarTrazo(seleccionado.id as string, gradosDeGiro('izquierda', 90, vistaDelPlano))}
              >
                ↺ 90°
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                aria-label="Girar 90° a la derecha"
                onClick={() => void girarTrazo(seleccionado.id as string, gradosDeGiro('derecha', 90, vistaDelPlano))}
              >
                ↻ 90°
              </button>
              <input
                className="input"
                aria-label="Ángulo de giro (grados)"
                inputMode="decimal"
                style={{ width: 52 }}
                value={anguloLibre}
                onChange={(e) => setAnguloLibre(e.target.value)}
              />
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                aria-label="Girar el ángulo escrito a la derecha"
                disabled={!Number.isFinite(Number(anguloLibre)) || Number(anguloLibre) === 0 || Math.abs(Number(anguloLibre)) > 360}
                onClick={() => void girarTrazo(seleccionado.id as string, gradosDeGiro('derecha', Number(anguloLibre), vistaDelPlano))}
              >
                Girar ↻
              </button>
            </div>
          )}
          {(forma || herramienta === 'hueco' || herramienta === 'escala' || herramienta === 'copiar' || herramienta === 'mover' || herramienta === 'enlace' || herramienta === 'conteo_auto') && (
            <div className="estacion__dibujo row" role="group" aria-label="Trazo en curso">
              {herramienta === 'mover' && (
                <span className="text-mute text-xs">
                  {borrador.length === 0
                    ? 'Mover: clic en el punto base'
                    : 'Clic en el destino · Esc cancela'}
                </span>
              )}
              {herramienta === 'copiar' && (
                <span className="text-mute text-xs">
                  Copiar en lote: clic donde va cada copia · {copias.current}{' '}
                  {copias.current === 1 ? 'copia' : 'copias'} · Esc termina
                </span>
              )}
              {herramienta === 'conteo_auto' && (
                <span className="text-mute text-xs">
                  {borrador.length === 0
                    ? 'Conteo automático: clic en una esquina del símbolo que quieres contar'
                    : 'Clic en la esquina opuesta del símbolo'}
                </span>
              )}
              {herramienta === 'enlace' && (
                <span className="text-mute text-xs">
                  {borrador.length === 0
                    ? 'Enlace a otra hoja: clic en una esquina de la zona (un detalle, un corte)'
                    : 'Clic en la esquina opuesta'}
                </span>
              )}
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
              {forma && forma !== 'punto' && clicsDeLaForma === undefined && (
                <>
                  <span className="text-mute text-xs">
                    {forma === 'contorno'
                      ? `${borrador.length} clics · modo ${modoContorno === 'arco' ? 'arco' : 'recto'} (T) · Enter cierra el contorno · Retroceso quita · Esc descarta`
                      : `${borrador.length} vértices · Enter cierra · Retroceso quita · Esc descarta`}
                  </span>
                  <button
                    type="button"
                    className="btn btn--accent btn--sm"
                    disabled={
                      forma === 'contorno'
                        ? contornoCerrado(borrador, tramosContorno) === null
                        : !trazoCompleto(GEOMETRIA_DE[forma as HerramientaDeDibujo], borrador)
                    }
                    onClick={terminar}
                  >
                    {forma === 'contorno' ? 'Cerrar contorno' : 'Terminar trazo'}
                  </button>
                </>
              )}
              {forma && forma !== 'punto' && clicsDeLaForma !== undefined && (
                <span className="text-mute text-xs">
                  {PASOS_DE_LA_FORMA[forma as HerramientaDeDibujo]} · clic {borrador.length + 1} de {clicsDeLaForma} · Esc descarta
                </span>
              )}
              {forma === 'punto' && formaPunto !== null && (
                <span className="text-mute text-xs">
                  Clic para estampar: {formaPunto.nombre ?? NOMBRE_DE_FORMA[formaPunto.tipo]} {formaPunto.anchoM} ×{' '}
                  {formaPunto.altoM} m
                </span>
              )}
            </div>
          )}
          {asistida && herramienta !== 'escala' && (
            <button
              type="button"
              className={ayudasAbiertas ? 'estado-pastilla is-activa' : 'estado-pastilla'}
              aria-pressed={ayudasAbiertas}
              aria-label="Ayudas de dibujo"
              title="Ajustar el ortogonal (ángulo de trabajo) y la referencia a objetos"
              onClick={() => setAyudasAbiertas(!ayudasAbiertas)}
            >
              AYUDAS
            </button>
          )}
          <button
            type="button"
            className={ortogonal ? 'estado-pastilla is-activa' : 'estado-pastilla'}
            aria-pressed={ortogonal}
            title="Ortogonal (F8). Mantén Mayús para invertirlo un momento."
            onClick={() => setOrtogonal(!ortogonal)}
          >
            ORTO {pasoGrados}°
          </button>
          <button
            type="button"
            className={referenciasOn ? 'estado-pastilla is-activa' : 'estado-pastilla'}
            aria-pressed={referenciasOn}
            title="Referencia a objetos (F3)"
            onClick={() => setReferenciasOn(!referenciasOn)}
          >
            REF
          </button>
          <span>
            {medicionActiva ? (
              <span data-testid="tipo-del-concepto" title="La medición activa: lo que dibujes entra a ella">
                Medición «{medicionActiva.nombre}» · {NOMBRE_DE_TIPO[medicionActiva.tipo]} ({medicionActiva.unidad}) ·{' '}
              </span>
            ) : (
              tipoDelConcepto !== null && (
                <span data-testid="tipo-del-concepto" title="El tipo de medición sale de la unidad del concepto elegido">
                  {matrizActiva ? `${matrizActiva.clave} · ` : ''}
                  {NOMBRE_DE_TIPO[tipoDelConcepto]} ({unidadEnFoco}) ·{' '}
                </span>
              )
            )}
            {featuresVisibles.length} de {features.length} {features.length === 1 ? 'trazo' : 'trazos'}
            {filtrando ? ' (filtrados)' : ''}
          </span>
          <span>
            {listaDeNotas.length} {listaDeNotas.length === 1 ? 'nota' : 'notas'}
          </span>
          <span data-testid="autoguardado" aria-live="polite" title="Cada cambio llega a la API al momento">
            {guardandoAhora ? 'Guardando…' : 'Todo guardado'}
          </span>
        </div>
      )}

      {porBorrar !== null && (
        <Modal titulo="Borrar trazo" onCerrar={() => setPorBorrar(null)}>
          <div className="sheet__body col gap-12">
            <p className="text-sm">
              Vas a borrar <strong>{nombreDelTrazo || 'el trazo elegido'}</strong>
              {seleccionado && seleccionado.properties.enlaces.length > 0
                ? ` y sus ${seleccionado.properties.enlaces.length} ${seleccionado.properties.enlaces.length === 1 ? 'enlace' : 'enlaces'}`
                : ''}
              {seleccionado && seleccionado.properties.n_huecos ? ` y sus ${seleccionado.properties.n_huecos} huecos` : ''}.
              La cantidad de cada concepto que alimentaba se recalcula. No se puede deshacer.
            </p>
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button type="button" className="btn" onClick={() => setPorBorrar(null)}>
                Cancelar
              </button>
              <button type="button" className="btn btn--danger" onClick={() => void confirmarBorrado()}>
                Borrar trazo
              </button>
            </div>
          </div>
        </Modal>
      )}

      {guardando && plano && aGuardar && (
        <AltaTrazo
          planoId={plano.id}
          versionPlano={plano.version}
          herramienta={aGuardar.tipo}
          puntos={aGuardar.puntos}
          grosorM={aGuardar.tipo === 'linea' ? grosorUsado : null}
          alineacion={aGuardar.tipo === 'linea' && grosorUsado !== null ? alineacion : null}
          grosorU={grosorUsado !== null ? grosorUsado * unidadesPorMetro : null}
          pendientePct={aGuardar.tipo === 'linea' ? pendientePct : null}
          forma={formaEstampada}
          actividades={actividades}
          actividadInicial={conceptoEnFoco}
          matrizInicial={matrizActiva?.id}
          medicion={
            medicionActiva
              ? {
                  id: medicionActiva.id,
                  nombre: medicionActiva.nombre,
                  tipo: medicionActiva.tipo,
                  nAsignaciones: asignacionesEfectivas(listaDeMediciones, medicionActiva.id),
                }
              : null
          }
          nodosDePrototipo={puedeEnlazarPrototipo ? nodosDePrototipo : null}
          onCerrar={() => {
            setGuardando(false);
            // Un punto o una forma de pocos clics se captura de una vez: si se cancela el cajón no
            // hay nada que seguir editando, se descarta. Un polígono o una polilínea se pueden seguir.
            if (forma === 'punto' || clicsDeLaForma !== undefined) limpiarDibujo();
            setFormaEstampada(null);
            setAGuardar(null);
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

      {takeoffAbierto && plano && fondoUrl !== null && (
        <TakeoffAutomatico
          planoId={plano.id}
          fondoUrl={fondoUrl}
          actividades={actividades.map((a) => ({ id: a.id, etiqueta: etiquetaActividad(a, a.id), tipo: tipoDeMedicion(a.unidad) }))}
          escalaMPorUnidad={escalaDelPlano}
          onVistaPrevia={setPreviasAuto}
          onCerrar={() => setTakeoffAbierto(false)}
          onPropuestas={(cuantas, descartadas) => {
            setTakeoffAbierto(false);
            setAviso(
              `${cuantas} ${cuantas === 1 ? 'propuesta' : 'propuestas'} del takeoff: revísalas, no suman hasta aceptarlas.` +
                (descartadas > 0 ? ` ${descartadas} no se pudieron medir y se omitieron.` : ''),
            );
            invalidarTrazos();
          }}
        />
      )}

      {zonaDePlantilla !== null && plano && fondoUrl !== null && (
        <ConteoAutomatico
          planoId={plano.id}
          fondoUrl={fondoUrl}
          puntoA={zonaDePlantilla[0]}
          puntoB={zonaDePlantilla[1]}
          actividades={actividades
            .filter((a) => tipoDeMedicion(a.unidad) === 'conteo')
            .map((a) => ({ id: a.id, etiqueta: etiquetaActividad(a, a.id) }))}
          actividadInicialId={conceptoActivo ?? undefined}
          onVistaPrevia={verCoincidencias}
          onCerrar={() => {
            setZonaDePlantilla(null);
            setBorrador([]);
          }}
          onPropuestas={(cuantas) => {
            setZonaDePlantilla(null);
            setBorrador([]);
            setHerramienta('seleccionar');
            setAviso(`${cuantas} ${cuantas === 1 ? 'coincidencia propuesta' : 'coincidencias propuestas'}: revísalas, no suman hasta aceptarlas.`);
            invalidarTrazos();
          }}
        />
      )}

      {zonaDeEnlace !== null && plano && (
        <AltaEnlaceDeHoja
          planoId={plano.id}
          puntoA={zonaDeEnlace[0]}
          puntoB={zonaDeEnlace[1]}
          destinos={hojasDeDestino}
          onCerrar={() => {
            setZonaDeEnlace(null);
            setBorrador([]);
          }}
          onCreado={(etiqueta) => {
            setZonaDeEnlace(null);
            setBorrador([]);
            setHerramienta('seleccionar');
            setAviso(`Enlace «${etiqueta}» creado: un clic en la zona lleva a esa hoja.`);
            void queryClient.invalidateQueries({
              queryKey: getListarEnlacesDeHojaApiV1PlanosPlanoIdEnlacesGetQueryKey(planoElegido),
            });
          }}
        />
      )}

      {proponiendoEscala && plano && archivo.data?.url && (
        <ProponerEscala
          planoId={plano.id}
          urlDelPdf={archivo.data.url}
          escalaActual={escalaDelPlano}
          onCerrar={() => setProponiendoEscala(false)}
          onAplicada={(r: EscalaRespuesta) => {
            setProponiendoEscala(false);
            setAviso(
              `Escala aplicada: 1 unidad de plano = ${Number(r.escala_m_por_unidad).toPrecision(4)} m. ` +
                (r.recalculos.length === 0
                  ? 'Todavía no hay trazos enlazados que recalcular.'
                  : `Se recalcularon ${r.recalculos.length} ${r.recalculos.length === 1 ? 'nodo' : 'nodos'}.`),
            );
            void queryClient.invalidateQueries({ queryKey: getListarPlanosApiV1ObrasObraIdPlanosGetQueryKey(obraId) });
            void queryClient.invalidateQueries({ queryKey: getTrazosDePlanoApiV1PlanosPlanoIdTrazosGetQueryKey(planoElegido) });
            void queryClient.invalidateQueries({ queryKey: getEstadoDeCuantificacionApiV1ObrasObraIdCuantificacionGetQueryKey(obraId) });
          }}
        />
      )}

      {notaPunto !== null && plano && (
        <AltaNota
          planoId={plano.id}
          versionPlano={plano.version}
          punto={notaPunto}
          tipo={claseDeNota}
          destino={notaDestino}
          actividades={actividades}
          onCerrar={() => {
            setNotaPunto(null);
            setNotaDestino(null);
            setBorrador([]);
          }}
          onGuardada={() => {
            setNotaPunto(null);
            setNotaDestino(null);
            setBorrador([]);
            setAviso(`${NOMBRE_DE_ANOTACION[claseDeNota]} guardada.`);
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
