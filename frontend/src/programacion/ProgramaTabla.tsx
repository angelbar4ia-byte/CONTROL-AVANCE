/**
 * Editor de programa base en **tabla + Gantt**, con su menú de herramientas
 * (§7.4, §7.5, §7.6, §11.2 `POST /programas-base`).
 *
 * Montado en `/config/programa-gantt`, con entrada propia en el sidebar de
 * Control de obra. Se le pasa `?prototipo=<id>` y, si se reedita una versión,
 * `&base=<id>`; sin prototipo enseña el vacío y manda a la lista, que es donde
 * se elige cuál árbol WBS se va a programar.
 *
 * ## Por qué existe teniendo el canvas
 *
 * El canvas (`EditorPrograma.tsx`) es un grafo: enseña **las ligas** y es donde
 * se tienden. Es lo correcto para revisar precedencias y lo incómodo para lo
 * otro que hay que hacer con un programa base, que es recorrer 155 renglones
 * poniendo duraciones y viendo cómo se acomoda el conjunto. Esa segunda lectura
 * es la de MS Project: la tabla manda a la izquierda, el Gantt a la derecha, y
 * el árbol WBS se lee de arriba abajo sin perderse. Las dos vistas editan el
 * mismo borrador con el mismo contrato; ninguna sustituye a la otra y no se
 * comunican entre sí — se entra a una o a la otra desde la lista.
 *
 * ## Un borrador, un POST
 *
 * Igual que el canvas y por el mismo motivo: cada `POST` **versiona** (§7.5),
 * crea la versión siguiente y retira la vigente. Guardar en cada arrastre
 * dejaría cuarenta versiones de una tarde de trabajo, así que se edita en
 * memoria (`borrador.ts`, con deshacer/rehacer) y el POST sale una sola vez.
 * El precio —cerrar la pestaña pierde lo no guardado— se avisa.
 *
 * ## Las dos clases de herramienta, y por qué sólo una ensucia
 *
 * El menú (`BarraHerramientasGantt.tsx`) tiene siete pestañas. Las dos primeras
 * —Programar y Vínculos— producen **gestos deshacibles**: `gestos.ts` los
 * traduce a acciones de `borrador.ts` y `despacharVarias` los apila como un
 * solo paso atrás, aunque el gesto valga doscientas acciones. Las cinco
 * restantes cambian la mirada y nada más: viven en `vistaGantt.ts`, se guardan
 * en `localStorage` y **no tocan el borrador ni ponen la pantalla en "sin
 * guardar"**. Encender la ruta crítica no es editar el programa.
 *
 * ## Lo que se adelanta al backend
 *
 * Los ciclos de precedencias (`ciclos.ts`). El backend responde 422 **sin
 * escribir nada** del programa completo si hay uno, así que descubrirlo al
 * guardar cuesta la sesión entera; aquí se señala el renglón que participa, se
 * explica al tender el vínculo que lo cerraría y no se deja guardar. La ruta
 * crítica y las fechas reales de una obra siguen siendo del motor (§6): lo que
 * traza esta pantalla es la cadena sin holgura **del borrador**, sobre su eje
 * relativo, y se rotula como tal (`rutaCritica.ts`).
 *
 * ## Días relativos, fechas opcionales
 *
 * El eje arranca en el Día 1 porque un programa base **es una plantilla**: se
 * reusa en cuarenta casas y no tiene fechas propias (§7.5). El interruptor de
 * fechas es una simulación contra un arranque concreto —"si empezara el lunes
 * 3, ¿qué días caerían?"— y se rotula como tal (`ejePrograma.ts`).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { usePresupuestoDePrototipoApiV1PrototiposPrototipoIdPresupuestoGet } from '@/api/generado/presupuesto/presupuesto';
import {
  useCrearProgramaBaseApiV1ProgramasBasePost,
  useListarItemsProgramaBaseApiV1ProgramasBaseProgramaBaseIdItemsGet,
  useListarProgramasBaseApiV1ProgramasBaseGet,
} from '@/api/generado/programacion/programacion';
import {
  useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet,
  useListarPrototiposApiV1PrototiposGet,
} from '@/api/generado/proyectos/proyectos';
import type {
  ClaseNodo,
  ItemProgramaBaseRespuesta,
  NodoPrototipoRespuesta,
  PartidaRespuesta,
  PresupuestoRespuesta,
  ProgramaBaseRespuesta,
  PrototipoRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtNum } from '@/lib/formato';
import { useDensidad } from '@/shell/SelectorDensidad';
import { resolverArrastre, empezarArrastre, type ClaseArrastre } from './arrastre';
import { construirBandas, saltosDeCalendario, zoomParaAjustar } from './bandasPrograma';
import { tonosDeFrente } from './barras';
import {
  BarraHerramientasGantt,
  type AccionesHerramientas,
  type SeleccionHerramientas,
} from './BarraHerramientasGantt';
import {
  deshacer as deshacerHistorial,
  despachar,
  despacharVarias,
  historialInicial,
  puedeDeshacer,
  puedeRehacer,
  rehacer as rehacerHistorial,
  type Accion,
  type Historial,
} from './borrador';
import { SEMANA_NATURAL, alternarDia, descripcionDeSemana, normalizarDias } from './calendario';
import { buscarCiclo } from './ciclos';
import { columnasVisibles, desplazamientosCongelados } from './columnasPrograma';
import type { EntradaConector } from './conectores';
import { construirEje, etiquetaDeDia } from './ejePrograma';
import {
  aplanarPrograma,
  colapsadosDeEntrada,
  colapsarANivel,
  filtrarPorTexto,
  profundidadMaxima,
  resumirFilas,
} from './filasPrograma';
import { GanttPrograma } from './GanttPrograma';
import * as gestos from './gestos';
import { armarBorrador, aristas, itemsDelBorrador, type TipoLiga } from './grafo';
import { alternarColapso, visiblesEnJerarquia } from './jerarquia';
import { colocar, duracionDelPrograma, nombreCorto } from './planificacion';
import { puedeAdministrarProgramasBase } from './reglas';
import { RejillaCantidades } from './RejillaCantidades';
import { magnitudesDeFilas, rejillaDeCantidades } from './reparto';
import { RUTA_CRITICA_VACIA, trazarRutaCritica } from './rutaCritica';
import { SINCRONIA_INICIAL, alDesplazar, reiniciarSincronia } from './sincronia';
import { TablaPrograma } from './TablaPrograma';
import {
  ANCHO_TABLA_MAXIMO,
  ANCHO_TABLA_MINIMO,
  CLAVE_PREFERENCIAS,
  VISTA_GANTT_INICIAL,
  deserializarVista,
  recortarAnchoTabla,
  serializarVista,
  temaEfectivo,
  type VistaGantt,
} from './vistaGantt';

export default function ProgramaTabla() {
  const { sesion } = useSesion();
  const rol = sesion?.rol ?? null;
  const administra = rol !== null && puedeAdministrarProgramasBase(rol);

  const [parametros] = useSearchParams();
  const prototipoId = parametros.get('prototipo') ?? '';
  const baseId = parametros.get('base');
  const navegar = useNavigate();

  const prototiposQ = useListarPrototiposApiV1PrototiposGet<PrototipoRespuesta[], ErrorApi>(
    {},
    { query: { enabled: administra } },
  );
  const nodosQ = useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet<
    NodoPrototipoRespuesta[],
    ErrorApi
  >(prototipoId, { query: { enabled: administra && prototipoId !== '' } });
  const itemsQ = useListarItemsProgramaBaseApiV1ProgramasBaseProgramaBaseIdItemsGet<
    ItemProgramaBaseRespuesta[],
    ErrorApi
  >(baseId ?? '', { query: { enabled: administra && baseId !== null } });
  const basesQ = useListarProgramasBaseApiV1ProgramasBaseGet<ProgramaBaseRespuesta[], ErrorApi>(
    { prototipo_id: prototipoId },
    { query: { enabled: administra && baseId !== null && prototipoId !== '' } },
  );
  // Unidad, cantidad e importe son del **presupuesto vigente** del prototipo,
  // unidos por `prototipo_nodo_id`, igual que en `ArbolPrototipo`: el nodo del
  // árbol no las trae. Sin presupuesto cargado esas columnas quedan vacías, que
  // es preferible a inventarlas.
  const presupuestoQ = usePresupuestoDePrototipoApiV1PrototiposPrototipoIdPresupuestoGet<
    PresupuestoRespuesta,
    ErrorApi
  >(prototipoId, { query: { enabled: administra && prototipoId !== '', retry: false } });

  const prototipo = useMemo(
    () => (prototiposQ.data ?? []).find((p) => p.id === prototipoId) ?? null,
    [prototiposQ.data, prototipoId],
  );

  const [historial, setHistorial] = useState<Historial | null>(null);
  const [huerfanos, setHuerfanos] = useState<readonly ItemProgramaBaseRespuesta[]>([]);
  const [sucio, setSucio] = useState(false);
  const [colapsados, setColapsados] = useState<ReadonlySet<string>>(new Set());
  const [seleccionado, setSeleccionado] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState('');
  const [inicioSimulado, setInicioSimulado] = useState(hoyIso());
  const [diasHabiles, setDiasHabiles] = useState<readonly number[]>(SEMANA_NATURAL);
  const [profundidad, setProfundidad] = useState<ClaseNodo>('concepto');
  const [aviso, setAviso] = useState<string | null>(null);
  const [rechazo, setRechazo] = useState<string | null>(null);
  const tirador = useRef<{ readonly x: number; readonly ancho: number } | null>(null);
  // El ancho **mientras** se arrastra el divisor. Vive aparte de la vista a
  // propósito: la vista se persiste en `localStorage` en cada cambio, y un
  // arrastre son decenas de cambios por segundo. Se confirma al soltar, que es
  // cuando el usuario decidió el reparto. El `ref` acompaña al estado porque
  // el manejador de `pointerup` necesita el último valor sin leerlo desde
  // dentro de un actualizador de estado, que React puede llamar dos veces.
  const [anchoArrastre, setAnchoArrastre] = useState<number | null>(null);
  const ultimoAncho = useRef<number | null>(null);

  const densidad = useDensidad((s) => s.densidad);
  const fijarDensidad = useDensidad((s) => s.fijar);

  // --- Preferencias de vista y apariencia (`localStorage`) -----------------
  // Se leen una sola vez, en el inicializador perezoso: leerlas en un efecto
  // dejaría el primer render con el default y produciría el parpadeo de tema
  // que todo el mundo reconoce como "la página cargó clara y luego se puso
  // oscura".
  const [vista, setVista] = useState<VistaGantt>(() => {
    try {
      return deserializarVista(window.localStorage.getItem(CLAVE_PREFERENCIAS));
    } catch {
      // Un navegador con el almacenamiento bloqueado no puede costar la
      // pantalla: se abre con los valores de fábrica.
      return VISTA_GANTT_INICIAL;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(CLAVE_PREFERENCIAS, serializarVista(vista));
    } catch {
      // Sin almacenamiento la preferencia dura lo que la pestaña. No es un
      // error que merezca interrumpir a nadie.
    }
  }, [vista]);

  // "Sistema" se resuelve aquí y no con un `@media` en la hoja, para que el
  // módulo lleve un solo atributo y la hoja un solo juego de tokens oscuros.
  const [prefiereOscuro, setPrefiereOscuro] = useState(() => consultaOscuro()?.matches ?? false);
  useEffect(() => {
    const consulta = consultaOscuro();
    if (!consulta) return undefined;
    const alCambiar = (evento: MediaQueryListEvent) => setPrefiereOscuro(evento.matches);
    consulta.addEventListener('change', alCambiar);
    return () => consulta.removeEventListener('change', alCambiar);
  }, []);
  const tema = temaEfectivo(vista.tema, prefiereOscuro);

  const listo = nodosQ.isSuccess && (baseId === null || itemsQ.isSuccess);

  // El borrador se arma una sola vez, cuando llegan los datos: rearmarlo en
  // cada render tiraría lo capturado. A diferencia del canvas no se acomoda
  // nada — aquí las cajas no tienen posición, el orden es el del árbol.
  useEffect(() => {
    if (!listo || historial !== null || prototipo === null) return;
    const { borrador, huerfanos: sueltos } = armarBorrador({
      prototipoId,
      nombre: '',
      nodos: nodosQ.data ?? [],
      items: itemsQ.data ?? [],
    });
    setHistorial(historialInicial(borrador));
    setHuerfanos(sueltos);
  }, [listo, historial, prototipo, prototipoId, nodosQ.data, itemsQ.data]);

  // Al reeditar, el calendario y la profundidad arrancan en los de la versión
  // abierta; un programa nuevo arranca en semana natural, que es el default del
  // backend. Se siembran una sola vez, para no pisar lo que ya se haya movido.
  //
  // `sembrado` es estado y no un `ref` a propósito: el colapso de entrada
  // depende de la profundidad, y con un ref el efecto que lo siembra no se
  // enteraría de que ya hay profundidad cuando la versión abierta trae
  // justamente el default (`concepto`) y `setProfundidad` no cambia nada.
  const [sembrado, setSembrado] = useState(baseId === null);
  useEffect(() => {
    if (sembrado || baseId === null || !basesQ.isSuccess) return;
    const abierta = (basesQ.data ?? []).find((base) => base.id === baseId);
    setSembrado(true);
    if (!abierta) return;
    setDiasHabiles(normalizarDias(abierta.calendario?.dias_habiles));
    setProfundidad(abierta.profundidad_captura ?? 'concepto');
  }, [sembrado, baseId, basesQ.isSuccess, basesQ.data]);

  const borrador = historial?.presente ?? null;

  const colocado = useMemo(
    () => (borrador ? colocar(borrador) : new Map()),
    [borrador],
  );
  const ciclo = useMemo(
    () =>
      borrador
        ? buscarCiclo(borrador.cajas.map((caja) => caja.id), aristas(borrador))
        : null,
    [borrador],
  );
  const enCiclo = useMemo(() => new Set(ciclo ?? []), [ciclo]);

  const partidas = useMemo<ReadonlyMap<string, PartidaRespuesta>>(() => {
    const mapa = new Map<string, PartidaRespuesta>();
    for (const partida of presupuestoQ.data?.partidas ?? []) {
      if (partida.prototipo_nodo_id) mapa.set(partida.prototipo_nodo_id, partida);
    }
    return mapa;
  }, [presupuestoQ.data]);

  const todas = useMemo(
    () =>
      borrador ? aplanarPrograma({ borrador, colocado, partidas, enCiclo }) : [],
    [borrador, colocado, partidas, enCiclo],
  );

  // El colapso de entrada se siembra con la profundidad de captura, una sola
  // vez y cuando ya hay filas **y** ya se sabe la profundidad: sembrarlo en
  // cada cambio volvería a plegar lo que el usuario acabara de abrir, y
  // sembrarlo antes de que llegue la versión abierta lo plegaría con el default
  // en vez de con lo que el equipo guardó.
  const colapsoSembrado = useRef(false);
  useEffect(() => {
    if (colapsoSembrado.current || !sembrado || todas.length === 0) return;
    colapsoSembrado.current = true;
    setColapsados(colapsadosDeEntrada(todas, profundidad));
  }, [sembrado, todas, profundidad]);

  const filtradas = useMemo(() => filtrarPorTexto(todas, busqueda), [todas, busqueda]);
  const visibles = useMemo(
    () => visiblesEnJerarquia(filtradas, colapsados),
    [filtradas, colapsados],
  );

  const eje = useMemo(
    () =>
      construirEje({
        finMaximo: duracionDelPrograma(colocado),
        pxPorDia: vista.zoom,
        modo: vista.modoEje,
        inicio: inicioSimulado,
        diasHabiles,
        hoy: hoyIso(),
      }),
    [colocado, vista.zoom, vista.modoEje, inicioSimulado, diasHabiles],
  );

  const bandas = useMemo(() => construirBandas(eje, vista.escala), [eje, vista.escala]);
  const saltos = useMemo(
    () => (vista.fondoGantt === 'inhabiles' ? saltosDeCalendario(eje) : []),
    [eje, vista.fondoGantt],
  );

  // La ruta crítica se traza sobre el árbol **completo** y no sobre lo visible:
  // una etapa colapsada tiene que poder decir que la cadena pasa por dentro.
  const ruta = useMemo(
    () =>
      vista.rutaCritica
        ? trazarRutaCritica(todas, vista.toleranciaHolguraDias)
        : RUTA_CRITICA_VACIA,
    [vista.rutaCritica, vista.toleranciaHolguraDias, todas],
  );

  const magnitudes = useMemo(() => magnitudesDeFilas(todas, partidas), [todas, partidas]);

  // El rollup de la rejilla necesita el árbol completo por el mismo motivo que
  // la ruta crítica: el renglón de una etapa plegada suma lo que hay dentro.
  const rejilla = useMemo(
    () =>
      vista.modalidad === 'cantidades'
        ? rejillaDeCantidades({
            filas: todas,
            periodos: bandas.inferior,
            magnitudes,
            magnitud: vista.magnitud,
          })
        : new Map(),
    [vista.modalidad, vista.magnitud, todas, bandas.inferior, magnitudes],
  );

  const tonoPorNodo = useMemo(() => {
    if (!borrador) return new Map<string, number>();
    const frentePorNodo = new Map(borrador.cajas.map((caja) => [caja.id, caja.frenteId]));
    const tonos = tonosDeFrente(frentePorNodo, todas.map((fila) => fila.nodoId));
    const salida = new Map<string, number>();
    for (const [nodoId, frenteId] of frentePorNodo) {
      const tono = frenteId === null ? undefined : tonos.get(frenteId);
      if (tono !== undefined) salida.set(nodoId, tono);
    }
    return salida;
  }, [borrador, todas]);

  const columnas = useMemo(() => columnasVisibles(vista.columnas), [vista.columnas]);
  const congelados = useMemo(
    () => desplazamientosCongelados(columnas, vista.fijarColumnas),
    [columnas, vista.fijarColumnas],
  );

  // Sólo se trazan las flechas entre renglones **dibujados**: una liga cuyo
  // extremo está plegado dentro de una etapa no tiene barra a la que apuntar, y
  // colgarla del resumen mentiría sobre qué depende de qué (`conectores.ts`).
  const ligas = useMemo<readonly EntradaConector[]>(() => {
    if (!borrador) return [];
    const dibujados = new Set(visibles.map((fila) => fila.nodoId));
    const salida: EntradaConector[] = [];
    for (const caja of borrador.cajas) {
      if (!dibujados.has(caja.id)) continue;
      for (const cable of caja.entradas) {
        if (!dibujados.has(cable.desde)) continue;
        salida.push({
          desde: cable.desde,
          hasta: caja.id,
          tipo: cable.tipo,
          alerta: enCiclo.has(caja.id) && enCiclo.has(cable.desde),
        });
      }
    }
    return salida;
  }, [borrador, visibles, enCiclo]);

  const resumen = useMemo(() => resumirFilas(todas), [todas]);
  const guardado = useMemo(
    () => (borrador ? itemsDelBorrador(borrador) : { items: [], avisos: [] }),
    [borrador],
  );

  const despacha = useCallback((accion: Accion) => {
    setHistorial((previo) => (previo === null ? previo : despachar(previo, accion)));
    setSucio(true);
  }, []);

  /**
   * Un gesto del menú: o se despacha entero —como un solo paso de deshacer— o
   * se explica por qué no se pudo. Nunca se descarta en silencio.
   */
  const aplicarGesto = useCallback((gesto: gestos.Gesto) => {
    if (!gesto.ok) {
      setRechazo(gesto.motivo);
      return;
    }
    setRechazo(null);
    setHistorial((previo) =>
      previo === null ? previo : despacharVarias(previo, gesto.acciones),
    );
    setSucio(true);
  }, []);

  /**
   * Clava (o suelta) el arranque de una actividad. `null` la desclava y la
   * devuelve a donde manda su cadena de precedencias.
   */
  const cambiarInicio = useCallback(
    (nodoId: string, dia: number | null) => {
      if (!borrador) return;
      aplicarGesto(
        dia === null
          ? gestos.desclavar(borrador, nodoId)
          : gestos.noIniciarAntesDe(borrador, colocado, nodoId, dia),
      );
    },
    [borrador, colocado, aplicarGesto],
  );

  const alternar = useCallback((nodoId: string) => {
    setColapsados((previos) => alternarColapso(previos, nodoId));
  }, []);

  /**
   * Elegir otro renglón retira el rechazo del gesto anterior. El motivo se
   * refiere siempre a **una** actividad ("ésta no depende de ninguna otra"),
   * y dejarlo puesto al cambiar de selección lo convierte en un reproche
   * sobre la actividad equivocada.
   */
  const seleccionar = useCallback((nodoId: string | null) => {
    setSeleccionado(nodoId);
    setRechazo(null);
  }, []);

  /**
   * Capturar días en la tabla pasa por el gesto y no por la acción cruda:
   * `fijarDuracion` es quien resuelve la herencia del árbol —repartir hacia
   * abajo, vaciar hacia arriba— y `aplicarGesto` apila todo eso como un solo
   * paso de deshacer.
   */
  const cambiarDuracion = useCallback(
    (nodoId: string, dias: number | null) => {
      if (!borrador) return;
      aplicarGesto(gestos.fijarDuracion(borrador, nodoId, dias));
    },
    [borrador, aplicarGesto],
  );

  /**
   * Fin de un arrastre. La aritmética está en `arrastre.ts`; aquí sólo se
   * despacha lo que decida, o se explica por qué no se pudo — que es el caso de
   * mover una actividad sin predecesoras, que no tiene dónde guardarse.
   */
  const alSoltar = useCallback(
    (cajaId: string, clase: ClaseArrastre, deltaDias: number) => {
      if (!borrador) return;
      const caja = borrador.cajas.find((c) => c.id === cajaId);
      if (!caja) return;
      const inicio = empezarArrastre(caja, colocado, clase, 0);
      const resultado = resolverArrastre(borrador, inicio, deltaDias);
      if (resultado.ok) {
        setRechazo(null);
        despacha(resultado.accion);
        return;
      }
      if (resultado.motivo !== null) setRechazo(resultado.motivo);
    },
    [borrador, colocado, despacha],
  );

  // --- Scroll sincronizado (`sincronia.ts`) --------------------------------
  const refTabla = useRef<HTMLDivElement>(null);
  const refGantt = useRef<HTMLDivElement>(null);
  const sincronia = useRef(SINCRONIA_INICIAL);

  const desplazar = useCallback((lado: 'tabla' | 'gantt', scrollTop: number) => {
    const paso = alDesplazar(sincronia.current, lado, scrollTop);
    sincronia.current = paso.estado;
    if (paso.escribirEn === null) return;
    const destino = paso.escribirEn === 'tabla' ? refTabla.current : refGantt.current;
    if (destino) destino.scrollTop = paso.scrollTop;
  }, []);

  // Plegar, filtrar o cambiar de programa cambia la altura de la lista: el
  // desplazamiento guardado deja de corresponder a nada y un eco pendiente de
  // la altura anterior bloquearía el primer scroll de la nueva. Cambiar de
  // modalidad monta otro contenedor a la derecha y vale lo mismo.
  useEffect(() => {
    sincronia.current = reiniciarSincronia(refTabla.current?.scrollTop ?? 0);
  }, [visibles.length, vista.modalidad]);

  // Cerrar la pestaña con cambios sin guardar los pierde: el borrador vive solo
  // en memoria, a propósito (una versión por sesión, no por gesto).
  useEffect(() => {
    if (!sucio) return undefined;
    function alSalir(evento: BeforeUnloadEvent) {
      evento.preventDefault();
      evento.returnValue = '';
    }
    window.addEventListener('beforeunload', alSalir);
    return () => window.removeEventListener('beforeunload', alSalir);
  }, [sucio]);

  useEffect(() => {
    function alTeclear(evento: KeyboardEvent) {
      if (!(evento.ctrlKey || evento.metaKey) || evento.key.toLowerCase() !== 'z') return;
      const destino = evento.target as HTMLElement | null;
      // Ctrl+Z dentro de un campo es el deshacer del campo, no el del editor.
      if (destino && /^(INPUT|TEXTAREA|SELECT)$/.test(destino.tagName)) return;
      evento.preventDefault();
      setHistorial((previo) =>
        previo === null
          ? previo
          : evento.shiftKey
            ? rehacerHistorial(previo)
            : deshacerHistorial(previo),
      );
      setSucio(true);
    }
    window.addEventListener('keydown', alTeclear);
    return () => window.removeEventListener('keydown', alTeclear);
  }, []);

  const crear = useCrearProgramaBaseApiV1ProgramasBasePost<ErrorApi>({
    mutation: {
      onSuccess: (respuesta) => {
        setRechazo(null);
        setSucio(false);
        setAviso(`Versión ${respuesta.version} guardada con ${respuesta.n_items} renglones.`);
      },
      onError: (error) =>
        setRechazo(error.campo ? `${error.campo}: ${error.message}` : error.message),
    },
  });

  function guardar(): void {
    if (!borrador) return;
    if (ciclo !== null) {
      setRechazo('Hay un ciclo de precedencias: el programa no se puede guardar (§6).');
      return;
    }
    setRechazo(null);
    crear.mutate({
      data: {
        prototipo_id: borrador.prototipoId,
        nombre: borrador.nombre.trim() === '' ? null : borrador.nombre.trim(),
        items: [...guardado.items],
        // El backend deriva el `tipo` (natural ⇔ los siete días); aquí sólo
        // viaja el conjunto, que es el único dato capturable (§7.5).
        calendario: { dias_habiles: [...diasHabiles] },
        profundidad_captura: profundidad,
      },
    });
  }

  // --- Lo que el menú necesita saber de la selección -----------------------
  const seleccion = useMemo<SeleccionHerramientas | null>(() => {
    if (borrador === null || seleccionado === null) return null;
    const caja = borrador.cajas.find((c) => c.id === seleccionado);
    const fila = todas.find((f) => f.nodoId === seleccionado);
    if (!caja || !fila) return null;

    const porId = new Map(borrador.cajas.map((c) => [c.id, c]));
    return {
      nodoId: caja.id,
      etiqueta: nombreCorto(caja),
      esResumen: fila.esResumen,
      capturado: fila.capturado,
      inicioDias: fila.inicioDias,
      terminoDias: fila.finDias === null ? null : Math.max(0, fila.finDias - 1),
      diasLaborables: fila.diasLaborables,
      nTramos: caja.tramos.length,
      predecesoras: caja.entradas.map((cable) => ({
        desde: cable.desde,
        etiqueta: nombreCorto(porId.get(cable.desde)),
        tipo: cable.tipo,
        lagDias: cable.lagDias,
      })),
      candidatas: gestos
        .candidatasAPredecesora(borrador, caja.id)
        .map((otra) => ({ id: otra.id, etiqueta: nombreCorto(otra) })),
    };
  }, [borrador, seleccionado, todas]);

  /**
   * Las herramientas que cambian el programa.
   *
   * Todas pasan por `gestos.ts` y por `aplicarGesto`: ninguna despacha una
   * acción por su cuenta. Es lo que garantiza que un botón que no puede hacer
   * su trabajo explique por qué, y que un gesto de doscientas acciones siga
   * siendo un solo paso de deshacer.
   */
  const acciones = useMemo<AccionesHerramientas>(() => {
    const conCaja = <T extends unknown[]>(
      hacer: (borradorActual: NonNullable<typeof borrador>, cajaId: string, ...args: T) => gestos.Gesto,
    ) => (...args: T) => {
      if (borrador === null || seleccionado === null) {
        setRechazo('Elige primero un renglón de la tabla.');
        return;
      }
      aplicarGesto(hacer(borrador, seleccionado, ...args));
    };

    return {
      aplazar: conCaja((b, id, dias: number) => gestos.aplazar(b, colocado, id, dias)),
      noIniciarAntesDe: conCaja((b, id, dia: number) =>
        gestos.noIniciarAntesDe(b, colocado, id, dia),
      ),
      fijarDuracion: conCaja((b, id, dias: number) => gestos.fijarDuracion(b, id, dias)),
      fijarInicio: conCaja((b, id, dia: number) => {
        const puesto = colocado.get(id);
        if (!puesto) {
          return { ok: false, motivo: 'La actividad no está colocada todavía (§7.5).' } as const;
        }
        return gestos.aplazar(b, colocado, id, Math.round(dia - puesto.inicioDias));
      }),
      fijarTermino: conCaja((b, id, dia: number) => gestos.fijarTermino(b, colocado, id, dia)),
      dividir: conCaja((b, id) => {
        const caja = b.cajas.find((c) => c.id === id);
        if (!caja) return { ok: false, motivo: 'La actividad ya no está en el programa.' } as const;
        return gestos.dividir(b, id, gestos.diaMedioDe(caja));
      }),
      interrumpir: conCaja((b, id, indice: number, dias: number) =>
        gestos.interrumpir(b, id, indice, dias),
      ),
      unirTramos: conCaja((b, id, indice: number) => gestos.unirTramos(b, id, indice)),
      reiniciarActividad: conCaja((b, id) => gestos.reiniciarActividad(b, id)),
      reiniciarPrograma: () => {
        if (borrador === null) return;
        aplicarGesto(gestos.reiniciarPrograma(borrador));
      },
      vincular: conCaja((b, id, desde: string, tipo: TipoLiga, lagDias: number) =>
        gestos.vincular(b, desde, id, tipo, lagDias),
      ),
      desvincular: conCaja((b, id, desde: string) => gestos.desvincular(b, desde, id)),
      invertir: conCaja((b, id, desde: string) => gestos.invertirVinculo(b, desde, id)),
      retipar: conCaja((b, id, desde: string, tipo: TipoLiga) =>
        gestos.retipar(b, desde, id, tipo),
      ),
      retrasar: conCaja((b, id, desde: string, lagDias: number) =>
        gestos.retrasar(b, desde, id, lagDias),
      ),
    };
  }, [borrador, seleccionado, colocado, aplicarGesto]);

  /** "Ajustar": el zoom que hace caber el programa en el ancho que hay. */
  const ajustarZoom = useCallback(() => {
    const ancho = refGantt.current?.clientWidth ?? 0;
    setVista((previa) => ({ ...previa, zoom: zoomParaAjustar(eje.dias, ancho - 16) }));
  }, [eje.dias]);

  const rotularDia = useCallback((dia: number) => etiquetaDeDia(eje, dia), [eje]);

  if (!sesion || rol === null) return null;

  if (!administra) {
    return (
      <Marco tema={tema} paleta={vista.paleta}>
        <div className="text-mute text-sm" style={{ padding: '24px 12px' }}>
          Los programas base de duraciones los administra Control de obra (§11.2).
        </div>
      </Marco>
    );
  }

  if (prototipoId === '') {
    return (
      <Marco tema={tema} paleta={vista.paleta}>
        <div className="empty">
          <div className="empty-title">Falta el prototipo</div>
          <div className="empty-sub">
            Esta vista se abre desde la lista de Programas base, que es donde se elige el
            prototipo cuyo árbol WBS se va a programar.
          </div>
          <Link className="btn" to="/config/programas-base">
            Ir a Programas base
          </Link>
        </div>
      </Marco>
    );
  }

  return (
    <Marco
      tema={tema}
      paleta={vista.paleta}
      titulo={prototipo ? `${prototipo.clave} · ${prototipo.nombre}` : 'Programa base'}
      acciones={
        <>
          <button
            type="button"
            className="btn"
            onClick={() => {
              if (sucio && !window.confirm('Hay cambios sin guardar. ¿Salir de todos modos?')) {
                return;
              }
              navegar('/config/programas-base');
            }}
          >
            Volver
          </button>
          <button
            type="button"
            className="btn btn--accent"
            disabled={borrador === null || crear.isPending || ciclo !== null}
            onClick={guardar}
          >
            {crear.isPending ? 'Guardando…' : 'Guardar versión'}
          </button>
        </>
      }
    >
      {nodosQ.isError && (
        <ErrorBanner mensaje={nodosQ.error.message} campo={nodosQ.error.campo} />
      )}
      {itemsQ.isError && (
        <ErrorBanner mensaje={itemsQ.error.message} campo={itemsQ.error.campo} />
      )}
      {rechazo !== null && (
        <div className="badge badge--danger" role="alert">
          {rechazo}
        </div>
      )}
      {aviso !== null && (
        <div className="badge badge--ok" role="status">
          {aviso}
        </div>
      )}
      {ciclo !== null && (
        <div className="badge badge--danger" role="alert">
          Hay un ciclo de precedencias entre {ciclo.length - 1} renglones: el backend lo
          rechazaría sin escribir nada (§6). Quítalo desde Vínculos o desde el canvas.
        </div>
      )}
      {huerfanos.length > 0 && (
        <div className="badge badge--warn">
          {huerfanos.length} renglón(es) de la versión abierta apuntan a nodos que ya no están
          en el árbol y no se dibujan.
        </div>
      )}

      <BarraHerramientasGantt
        vista={vista}
        onVista={setVista}
        acciones={acciones}
        seleccion={seleccion}
        rotularDia={rotularDia}
        ruta={ruta}
        diasHabiles={diasHabiles}
        onDiasHabiles={setDiasHabiles}
        onAlternarDia={(dia) => setDiasHabiles((previos) => alternarDia(previos, dia))}
        inicioSimulado={inicioSimulado}
        onInicioSimulado={setInicioSimulado}
        onAjustarZoom={ajustarZoom}
        profundidadMaxima={profundidadMaxima(todas)}
        onColapsarANivel={(nivel) => setColapsados(colapsarANivel(todas, nivel))}
        densidad={densidad}
        onDensidad={fijarDensidad}
        puedeDeshacer={historial !== null && puedeDeshacer(historial)}
        puedeRehacer={historial !== null && puedeRehacer(historial)}
        onDeshacer={() =>
          setHistorial((previo) => (previo === null ? previo : deshacerHistorial(previo)))
        }
        onRehacer={() =>
          setHistorial((previo) => (previo === null ? previo : rehacerHistorial(previo)))
        }
        editable
      />

      <div className="filterbar">
        <input
          className="input search"
          placeholder="Buscar por clave o descripción"
          value={busqueda}
          onChange={(evento) => setBusqueda(evento.target.value)}
          aria-label="Buscar renglón"
        />

        <span className="topbar__spacer" />

        {sucio && <span className="badge badge--warn">sin guardar</span>}
        <span className="text-xs text-mute mono">
          {resumen.nCapturados}/{resumen.nNodos} capturados · {fmtNum(resumen.diasTotales)} d ·{' '}
          {descripcionDeSemana(diasHabiles)}
        </span>
      </div>

      {guardado.avisos.map((avisoGuardado) => (
        <div key={avisoGuardado.clase} className="text-xs text-mute">
          {avisoGuardado.mensaje}
        </div>
      ))}

      {borrador === null ? (
        <div className="text-mute text-sm" style={{ padding: '24px 12px' }}>
          Cargando el árbol del prototipo…
        </div>
      ) : (
        <div
          className="prog-split"
          style={{
            ['--prog-tabla-w' as string]: `${anchoArrastre ?? vista.anchoTabla}px`,
          }}
        >
          <TablaPrograma
            filas={visibles}
            eje={eje}
            columnas={columnas}
            congelados={congelados}
            vista={vista}
            magnitudes={magnitudes}
            criticas={ruta.criticas}
            colapsados={colapsados}
            seleccionado={seleccionado}
            editable
            onAlternar={alternar}
            onSeleccionar={seleccionar}
            onDuracion={cambiarDuracion}
            onInicio={cambiarInicio}
            contenedorRef={refTabla}
            onScroll={(top) => desplazar('tabla', top)}
          />
          {/* El reparto entre las dos mitades es del usuario: hay días en que
              lo que se revisa son las columnas y días en que es el calendario.
              Se mueve con el ratón y con las flechas, que es lo que lo hace
              alcanzable sin ratón (§12.10). */}
          <div
            className="prog-split__tirador"
            role="separator"
            aria-orientation="vertical"
            aria-label="Repartir el ancho entre la tabla y el Gantt"
            aria-valuenow={anchoArrastre ?? vista.anchoTabla}
            aria-valuemin={ANCHO_TABLA_MINIMO}
            aria-valuemax={ANCHO_TABLA_MAXIMO}
            tabIndex={0}
            onPointerDown={(evento) => {
              evento.currentTarget.setPointerCapture(evento.pointerId);
              tirador.current = { x: evento.clientX, ancho: vista.anchoTabla };
            }}
            onPointerMove={(evento) => {
              const inicio = tirador.current;
              if (inicio === null) return;
              const ancho = recortarAnchoTabla(inicio.ancho + evento.clientX - inicio.x);
              ultimoAncho.current = ancho;
              setAnchoArrastre(ancho);
            }}
            onPointerUp={() => {
              tirador.current = null;
              // Al soltar, y sólo al soltar, el reparto pasa a la preferencia.
              const ancho = ultimoAncho.current;
              ultimoAncho.current = null;
              setAnchoArrastre(null);
              if (ancho !== null) setVista((previa) => ({ ...previa, anchoTabla: ancho }));
            }}
            onKeyDown={(evento) => {
              const paso = evento.key === 'ArrowLeft' ? -24 : evento.key === 'ArrowRight' ? 24 : 0;
              if (paso === 0) return;
              evento.preventDefault();
              setVista((previa) => ({
                ...previa,
                anchoTabla: recortarAnchoTabla(previa.anchoTabla + paso),
              }));
            }}
          />
          {vista.modalidad === 'gantt' ? (
            <GanttPrograma
              filas={visibles}
              eje={eje}
              bandas={bandas}
              saltos={saltos}
              ligas={ligas}
              vista={vista}
              criticas={ruta.criticas}
              magnitudes={magnitudes}
              tonoPorNodo={tonoPorNodo}
              seleccionado={seleccionado}
              editable
              onSeleccionar={seleccionar}
              onSoltar={alSoltar}
              contenedorRef={refGantt}
              onScroll={(top) => desplazar('gantt', top)}
            />
          ) : (
            <RejillaCantidades
              filas={visibles}
              periodos={bandas.inferior}
              rejilla={rejilla}
              magnitud={vista.magnitud}
              seleccionado={seleccionado}
              onSeleccionar={seleccionar}
              contenedorRef={refGantt}
              onScroll={(top) => desplazar('gantt', top)}
            />
          )}
        </div>
      )}

      <p className="text-xs text-mute mt-8">
        {vista.modalidad === 'gantt' ? (
          <>
            Arrastrar el cuerpo de una barra corre la actividad cambiando el lag de la
            precedencia que la detiene; arrastrar su borde derecho cambia la duración. Las
            barras de nivel y etapa son el resumen derivado de sus hijos y no se arrastran
            (§7.4).
          </>
        ) : (
          <>
            Las cantidades por periodo son <strong>derivadas</strong> de la cantidad del
            presupuesto y de la colocación del borrador, y son de sólo lectura: el reparto no
            existe como dato en el contrato, así que capturarlo a mano sería otra fase. Una
            pausa no consume cantidad (§7.6).
          </>
        )}
      </p>
    </Marco>
  );
}

/**
 * Encabezado de la pantalla, igual en los tres estados (sin rol, sin
 * prototipo, editor).
 *
 * Es también donde vive el **alcance del tema**: `data-tema` y `data-paleta`
 * van en este contenedor y no en `<body>`. El resto de la app es hoy sólo
 * clara y tiene una veintena de colores literales fuera de los tokens —el
 * comparativo de cargas, las bandas del Gantt de obra, los KPI en alerta—, así
 * que teñir el `<body>` dejaría esas pantallas con parches claros sobre fondo
 * oscuro. Acotado al módulo, el juego de tokens oscuro sólo tiene que cubrir
 * lo que este módulo pinta, que sí está tokenizado al cien por cien.
 */
function Marco({
  titulo = 'Programa base · tabla y Gantt',
  acciones,
  tema,
  paleta,
  children,
}: {
  readonly titulo?: string;
  readonly acciones?: React.ReactNode;
  readonly tema: 'claro' | 'oscuro';
  readonly paleta: 'color' | 'mono';
  readonly children: React.ReactNode;
}) {
  return (
    <div className="page prog-modulo" data-tema={tema} data-paleta={paleta}>
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Configuración · Programas base</div>
          <h1 className="page__title">{titulo}</h1>
          <div className="page__subtitle">
            Tabla jerárquica y Gantt sobre el árbol WBS del prototipo. Un borrador en memoria;
            guardar crea la versión siguiente (§7.5).
          </div>
        </div>
        {acciones !== undefined && <div className="page__actions">{acciones}</div>}
      </div>
      {children}
    </div>
  );
}

/** Hoy en `YYYY-MM-DD` local, que es como el `<input type="date">` lo espera. */
function hoyIso(): string {
  const ahora = new Date();
  const mes = String(ahora.getMonth() + 1).padStart(2, '0');
  const dia = String(ahora.getDate()).padStart(2, '0');
  return `${ahora.getFullYear()}-${mes}-${dia}`;
}

/**
 * La consulta de tema del sistema, o `null` donde no exista.
 *
 * `matchMedia` no está en jsdom por defecto, así que sin esta guarda la
 * pantalla no montaría en las pruebas de render — y tampoco en un navegador
 * viejo. La ausencia se lee como "no prefiere oscuro", que es el default.
 */
function consultaOscuro(): MediaQueryList | null {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null;
  return window.matchMedia('(prefers-color-scheme: dark)');
}
