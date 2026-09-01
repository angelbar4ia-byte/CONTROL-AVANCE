/**
 * Editor gráfico de programas base (§7.5, §11.2 `POST /programas-base`).
 *
 * Montado en `/config/programas-base/editor`, al que se llega desde la lista
 * de Programas base con `?prototipo=<id>` y, si se está reeditando una
 * versión, `&base=<id>`. Todo el bloque es de Control de obra (§11.2).
 *
 * ## Qué sustituye
 *
 * Hasta esta fase un programa base se capturaba tecleando **UUIDs a mano**
 * —el nodo del prototipo, la etapa y la `ref` de cada dependencia— porque el
 * contrato no exponía el árbol. `GET /prototipos/{id}/nodos` ya existe, y con
 * él el grafo se puede dibujar: nodos = nodos del WBS, cables = dependencias
 * (`grafo.ts`). Aquí no se teclea ningún identificador.
 *
 * ## Borrador local, un solo guardado
 *
 * Cada `POST` **versiona** (§7.5): crea la versión siguiente y retira la
 * vigente. Guardar en cada arrastre dejaría cuarenta versiones de una tarde.
 * Por eso el canvas edita en memoria (`borrador.ts`, con deshacer/rehacer) y
 * el `POST` sale una sola vez, al presionar Guardar. El precio —cerrar la
 * pestaña pierde lo no guardado— se avisa con el `beforeunload` y con el
 * distintivo "sin guardar" de la barra.
 *
 * ## Lo que se valida aquí y lo que sigue siendo del backend
 *
 * El motor del CPM no se duplica: la ruta crítica, la holgura y las fechas
 * siguen siendo del backend y este editor no las calcula. Lo que sí se
 * adelanta es lo que el backend rechaza con un 422 **sin escribir nada**: un
 * ciclo de precedencias y unos tramos inválidos. Descubrir cualquiera de los
 * dos al guardar significaría perder la sesión completa y no saber cuál de
 * los treinta cables lo provocó; detectarlo al tender el cable lo convierte en
 * un cable que no se pega.
 *
 * ## Estado vacío
 *
 * Un prototipo sin programa base no arranca en un canvas en blanco: arranca
 * con **una caja por etapa y por concepto** de su árbol WBS, en gris, sin
 * duración. Capturar el programa es llenar duraciones y tender cables, no
 * dar de alta renglones uno por uno.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Background,
  BackgroundVariant,
  ConnectionMode,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type OnConnectStartParams,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useCrearProgramaBaseApiV1ProgramasBasePost } from '@/api/generado/programacion/programacion';
import { useListarItemsProgramaBaseApiV1ProgramasBaseProgramaBaseIdItemsGet } from '@/api/generado/programacion/programacion';
import { useListarProgramasBaseApiV1ProgramasBaseGet } from '@/api/generado/programacion/programacion';
import {
  useListarFrentesApiV1FrentesGet,
  useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet,
  useListarPrototiposApiV1PrototiposGet,
} from '@/api/generado/proyectos/proyectos';
import type {
  FrenteRespuesta,
  ItemProgramaBaseRespuesta,
  NodoPrototipoRespuesta,
  ProgramaBaseRespuesta,
  PrototipoRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { acomodarEnCapas } from './acomodo';
import {
  deshacer as deshacerHistorial,
  despachar,
  historialInicial,
  marcar,
  puedeDeshacer,
  puedeRehacer,
  rehacer as rehacerHistorial,
  type Accion,
  type Historial,
} from './borrador';
import { BarraProgramacion, type ModoPuntero } from './BarraProgramacion';
import { buscarCiclo, cerrariaCiclo } from './ciclos';
import { CableDependencia, type CableCanvas } from './CableDependencia';
import {
  armarBorrador,
  aristas,
  esForaneo,
  esRenglon,
  idsVisibles,
  itemsDelBorrador,
  esTipoLiga,
  type Borrador,
  type TipoLiga,
  type Vista,
} from './grafo';
import {
  SEMANA_NATURAL,
  alternarDia,
  mismosDias,
  normalizarDias,
} from './calendario';
import { NodoActividad, type CajaCanvas } from './NodoActividad';
import { PanelCaja } from './PanelCaja';
import { colocar, duracionDelPrograma, traslapesConTrabajo } from './planificacion';
import { puedeAdministrarProgramasBase } from './reglas';

const TIPOS_NODO = { actividad: NodoActividad };
const TIPOS_CABLE = { dependencia: CableDependencia };

export default function EditorPrograma() {
  return (
    <ReactFlowProvider>
      <Pantalla />
    </ReactFlowProvider>
  );
}

function Pantalla() {
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
  const frentesQ = useListarFrentesApiV1FrentesGet<FrenteRespuesta[], ErrorApi>(
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
  // Los items no traen el calendario —es del programa, no del renglón— y no
  // hay endpoint de un solo programa base: se saca de la lista del prototipo,
  // que ya viene filtrada y es la misma que alimenta la pantalla anterior.
  const basesQ = useListarProgramasBaseApiV1ProgramasBaseGet<
    ProgramaBaseRespuesta[],
    ErrorApi
  >(
    { prototipo_id: prototipoId },
    { query: { enabled: administra && baseId !== null && prototipoId !== '' } },
  );

  const prototipo = useMemo(
    () => (prototiposQ.data ?? []).find((p) => p.id === prototipoId) ?? null,
    [prototiposQ.data, prototipoId],
  );
  const frentes = useMemo(() => frentesQ.data ?? [], [frentesQ.data]);

  // El calendario es del programa completo, no del grafo, así que vive fuera
  // del historial: cambiarlo no es un gesto del canvas que tenga sentido
  // deshacer con Ctrl+Z junto a un arrastre de caja. Sí ensucia el borrador.
  const [diasHabiles, setDiasHabiles] = useState<readonly number[]>(SEMANA_NATURAL);

  const [historial, setHistorial] = useState<Historial | null>(null);
  const [huerfanos, setHuerfanos] = useState<readonly ItemProgramaBaseRespuesta[]>([]);
  const [sucio, setSucio] = useState(false);
  const [vista, setVista] = useState<Vista>({ modo: 'etapas' });
  const [modo, setModo] = useState<ModoPuntero>('seleccionar');
  const [tipoLigaPorDefecto, setTipoLigaPorDefecto] = useState<TipoLiga>('FS');
  const [seleccionada, setSeleccionada] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [rechazo, setRechazo] = useState<string | null>(null);
  const anclajeSalida = useRef<string | null>(null);

  const { fitView } = useReactFlow();

  const listo = nodosQ.isSuccess && (baseId === null || itemsQ.isSuccess);

  // El borrador se arma una sola vez, cuando llegan los datos: rearmarlo en
  // cada render tiraría lo capturado. Los datos que llegan después (frentes)
  // no lo tocan porque no forman parte del grafo.
  useEffect(() => {
    if (!listo || historial !== null || prototipo === null) return;
    const { borrador, huerfanos: sueltos } = armarBorrador({
      prototipoId,
      nombre: '',
      nodos: nodosQ.data ?? [],
      items: itemsQ.data ?? [],
    });
    // Las posiciones no viajan en el contrato, así que siempre se calculan al
    // abrir. Mover una caja no sobrevive al cierre de la pantalla.
    const posiciones = acomodarEnCapas(
      borrador.cajas.map((caja) => ({ id: caja.id, orden: caja.orden })),
      aristas(borrador),
    );
    const acomodado: Borrador = {
      ...borrador,
      cajas: borrador.cajas.map((caja) => ({
        ...caja,
        ...(posiciones.get(caja.id) ?? { x: 0, y: 0 }),
      })),
    };
    setHistorial(historialInicial(acomodado));
    setHuerfanos(sueltos);
  }, [listo, historial, prototipo, prototipoId, nodosQ.data, itemsQ.data]);

  const borrador = historial?.presente ?? null;

  // Al reeditar, el calendario arranca en el de la versión abierta; un
  // programa nuevo arranca en natural, que es el default del backend y el
  // comportamiento histórico del motor. Se siembra una sola vez —igual que el
  // borrador— para no pisar lo que el usuario ya haya movido en la barra.
  const calendarioSembrado = useRef(false);
  useEffect(() => {
    if (calendarioSembrado.current || baseId === null || !basesQ.isSuccess) return;
    const abierta = (basesQ.data ?? []).find((base) => base.id === baseId);
    if (!abierta) return;
    calendarioSembrado.current = true;
    setDiasHabiles(normalizarDias(abierta.calendario?.dias_habiles));
  }, [baseId, basesQ.isSuccess, basesQ.data]);

  const calendarioOriginal = useMemo<readonly number[]>(() => {
    if (baseId === null) return SEMANA_NATURAL;
    const abierta = (basesQ.data ?? []).find((base) => base.id === baseId);
    return normalizarDias(abierta?.calendario?.dias_habiles);
  }, [baseId, basesQ.data]);

  const cambiarDias = useCallback(
    (dias: readonly number[]) => {
      setDiasHabiles((previos) => {
        const nuevos = normalizarDias(dias);
        if (mismosDias(previos, nuevos)) return previos;
        // El calendario mueve todas las fechas del cronograma, así que
        // cambiarlo ensucia el borrador aunque no se haya tocado una caja.
        if (!mismosDias(nuevos, calendarioOriginal)) setSucio(true);
        return nuevos;
      });
    },
    [calendarioOriginal],
  );

  const alternarDiaHabil = useCallback(
    (dia: number) => cambiarDias(alternarDia(diasHabiles, dia)),
    [cambiarDias, diasHabiles],
  );

  const despacha = useCallback((accion: Accion) => {
    setHistorial((previo) => (previo === null ? previo : despachar(previo, accion)));
    setSucio(true);
  }, []);

  const gesto = useCallback(() => {
    setHistorial((previo) => (previo === null ? previo : marcar(previo)));
  }, []);

  // Cerrar la pestaña con cambios sin guardar los pierde: el borrador vive
  // solo en memoria, a propósito (una versión por sesión, no por gesto).
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
      // Ctrl+Z dentro de un campo es el deshacer del campo, no el del canvas.
      if (destino && /^(INPUT|TEXTAREA|SELECT)$/.test(destino.tagName)) return;
      evento.preventDefault();
      setHistorial((previo) =>
        previo === null ? previo : evento.shiftKey ? rehacerHistorial(previo) : deshacerHistorial(previo),
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
        setAviso(
          `Versión ${respuesta.version} guardada con ${respuesta.n_items} renglones.`,
        );
      },
      onError: (error) => setRechazo(error.campo ? `${error.campo}: ${error.message}` : error.message),
    },
  });

  const colocado = useMemo(() => (borrador ? colocar(borrador) : new Map()), [borrador]);
  const traslapes = useMemo(
    () => (borrador ? traslapesConTrabajo(borrador, colocado) : []),
    [borrador, colocado],
  );
  const ciclo = useMemo(
    () =>
      borrador
        ? buscarCiclo(borrador.cajas.map((caja) => caja.id), aristas(borrador))
        : null,
    [borrador],
  );

  const guardado = useMemo(
    () => (borrador ? itemsDelBorrador(borrador) : { items: [], avisos: [] }),
    [borrador],
  );

  const visibles = useMemo(
    () => (borrador ? idsVisibles(borrador, vista) : new Set<string>()),
    [borrador, vista],
  );

  const nodosCanvas = useMemo<CajaCanvas[]>(() => {
    if (!borrador) return [];
    const conAviso = new Set(traslapes.map((traslape) => traslape.cajaId));
    const enCiclo = new Set(ciclo ?? []);
    const frentePorId = new Map(frentes.map((frente) => [frente.id, frente]));

    return borrador.cajas
      .filter((caja) => visibles.has(caja.id))
      .map((caja) => ({
        id: caja.id,
        type: 'actividad' as const,
        position: { x: caja.x, y: caja.y },
        selected: caja.id === seleccionada,
        draggable: modo === 'seleccionar',
        data: {
          clave: caja.clave,
          nombre: caja.nombre,
          tipo: caja.tipo,
          duracionDias: caja.duracionDias,
          tramos: caja.tramos,
          frenteClave: caja.frenteId ? (frentePorId.get(caja.frenteId)?.clave ?? null) : null,
          foraneo: esForaneo(caja, vista),
          conAviso: conAviso.has(caja.id),
          enCiclo: enCiclo.has(caja.id),
          abrible: caja.tipo === 'etapa',
        },
      }));
  }, [borrador, visibles, vista, traslapes, ciclo, frentes, seleccionada, modo]);

  const cablesCanvas = useMemo<CableCanvas[]>(() => {
    if (!borrador) return [];
    const conAviso = new Set(
      traslapes.map((traslape) => `${traslape.predecesoraId}->${traslape.cajaId}`),
    );
    return borrador.cajas
      .filter((caja) => visibles.has(caja.id))
      .flatMap((caja) =>
        caja.entradas
          .filter((cable) => visibles.has(cable.desde))
          .map((cable) => ({
            id: `${cable.desde}->${caja.id}`,
            type: 'dependencia' as const,
            source: cable.desde,
            target: caja.id,
            // El anclaje es la semántica: la primera letra del tipo dice de
            // qué extremo sale y la segunda por cuál entra (§7.5).
            sourceHandle: cable.tipo.startsWith('S') ? 'inicio' : 'fin',
            targetHandle: cable.tipo.endsWith('S') ? 'inicio' : 'fin',
            markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
            data: {
              tipoLiga: cable.tipo,
              lagDias: cable.lagDias,
              conAviso: conAviso.has(`${cable.desde}->${caja.id}`),
            },
          })),
      );
  }, [borrador, visibles, traslapes]);

  const alCambiarNodos = useCallback(
    (cambios: NodeChange<CajaCanvas>[]) => {
      for (const cambio of cambios) {
        if (cambio.type === 'position' && cambio.position) {
          despacha({ tipo: 'mover', cajaId: cambio.id, ...cambio.position });
        }
      }
    },
    [despacha],
  );

  const alConectar = useCallback(
    (conexion: Connection) => {
      if (!borrador) return;
      // El arrastre siempre va predecesora → sucesora, como en MS Project.
      const desde = conexion.source;
      const hasta = conexion.target;
      if (cerrariaCiclo(aristas(borrador), desde, hasta)) {
        setRechazo(
          'Ese cable cerraría un ciclo de precedencias: el backend rechazaría el programa completo (§6).',
        );
        return;
      }
      const salida = conexion.sourceHandle === 'inicio' ? 'S' : 'F';
      const entrada = conexion.targetHandle === 'inicio' ? 'S' : 'F';
      const derivado = `${salida}${entrada}`;
      setRechazo(null);
      despacha({
        tipo: 'conectar',
        desde,
        hasta,
        // Los anclajes mandan cuando los dos se conocen; el tipo de la barra
        // es el respaldo para cuando la conexión no nace de un anclaje.
        tipoLiga: esTipoLiga(derivado) ? (derivado as TipoLiga) : tipoLigaPorDefecto,
      });
    },
    [borrador, despacha, tipoLigaPorDefecto],
  );

  const alAcomodar = useCallback(() => {
    if (!borrador) return;
    gesto();
    // Se acomoda solo lo visible: reacomodar el árbol entero movería cajas que
    // el usuario no está viendo y que colocó a mano en la otra vista.
    const dentro = borrador.cajas.filter((caja) => visibles.has(caja.id));
    despacha({
      tipo: 'acomodar',
      posiciones: acomodarEnCapas(
        dentro.map((caja) => ({ id: caja.id, orden: caja.orden })),
        aristas(borrador).filter(
          (arista) => visibles.has(arista.desde) && visibles.has(arista.hasta),
        ),
      ),
    });
    window.setTimeout(() => void fitView({ duration: 200, padding: 0.2 }), 0);
  }, [borrador, visibles, despacha, gesto, fitView]);

  function guardar() {
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
        // El backend deriva el `tipo` (natural ⇔ los siete días); aquí solo
        // viaja el conjunto, que es el único dato capturable (§7.5).
        calendario: { dias_habiles: [...diasHabiles] },
      },
    });
  }

  if (!sesion || rol === null) return null;

  if (!administra) {
    return (
      <div className="page">
        <div className="page__header">
          <div className="page__titlewrap">
            <div className="page__eyebrow mono">Configuración</div>
            <h1 className="page__title">Editor de programa base</h1>
          </div>
        </div>
        <div className="text-mute text-sm" style={{ padding: '24px 12px' }}>
          Los programas base de duraciones los administra Control de obra (§11.2).
        </div>
      </div>
    );
  }

  if (prototipoId === '') {
    return (
      <div className="page">
        <div className="page__header">
          <div className="page__titlewrap">
            <h1 className="page__title">Editor de programa base</h1>
          </div>
        </div>
        <div className="empty">
          <div className="empty-title">Falta el prototipo</div>
          <div className="empty-sub">
            El editor se abre desde la lista de Programas base, que es donde se elige el
            prototipo cuyo árbol WBS se va a programar.
          </div>
          <Link className="btn" to="/config/programas-base">
            Ir a Programas base
          </Link>
        </div>
      </div>
    );
  }

  const errores = [prototiposQ.error, frentesQ.error, nodosQ.error, itemsQ.error].filter(
    (error): error is ErrorApi => error !== null && error !== undefined,
  );

  const cajaSeleccionada =
    borrador && seleccionada !== null
      ? (borrador.cajas.find((caja) => caja.id === seleccionada) ?? null)
      : null;

  const etapaAbierta =
    vista.modo === 'conceptos-de' && borrador
      ? (borrador.cajas.find((caja) => caja.id === vista.etapaNodoId)?.nombre ?? null)
      : null;

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Configuración · Programas base</div>
          <h1 className="page__title">
            {prototipo ? `${prototipo.clave} · ${prototipo.nombre}` : 'Editor de programa base'}
          </h1>
          <div className="page__subtitle">
            Nodos del árbol WBS y sus precedencias. Cada guardado crea una versión nueva
            (§7.5); mientras tanto todo vive en esta pestaña.
          </div>
        </div>
        <div className="page__actions">
          <input
            className="input"
            style={{ width: 240 }}
            aria-label="Nombre de la versión"
            placeholder="Nombre de la versión (opcional)"
            value={borrador?.nombre ?? ''}
            onChange={(e) => despacha({ tipo: 'nombre', nombre: e.target.value })}
          />
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
        </div>
      </div>

      {aviso !== null && (
        <div className="mb-8" role="status">
          <span className="badge badge--ok">{aviso}</span>
        </div>
      )}

      {errores.map((error, indice) => (
        <div className="mb-8" key={`${error.status}-${indice}`}>
          <ErrorBanner mensaje={error.message} />
        </div>
      ))}

      {rechazo !== null && (
        <div className="mb-8">
          <ErrorBanner mensaje={rechazo} />
        </div>
      )}

      <BarraProgramacion
        modo={modo}
        onModo={setModo}
        tipoLigaPorDefecto={tipoLigaPorDefecto}
        onTipoLiga={setTipoLigaPorDefecto}
        vista={vista}
        onVista={setVista}
        nombreEtapaAbierta={etapaAbierta}
        onAcomodar={alAcomodar}
        onAjustar={() => void fitView({ duration: 200, padding: 0.2 })}
        puedeDeshacer={historial !== null && puedeDeshacer(historial)}
        puedeRehacer={historial !== null && puedeRehacer(historial)}
        onDeshacer={() => {
          setHistorial((previo) => (previo === null ? previo : deshacerHistorial(previo)));
          setSucio(true);
        }}
        onRehacer={() => {
          setHistorial((previo) => (previo === null ? previo : rehacerHistorial(previo)));
          setSucio(true);
        }}
        onGuardar={guardar}
        guardando={crear.isPending}
        sucio={sucio}
        renglones={guardado.items.length}
        diasHabiles={diasHabiles}
        onDiasHabiles={cambiarDias}
        onAlternarDia={alternarDiaHabil}
      />

      {guardado.avisos.map((mensaje) => (
        <div className="mb-8" key={mensaje.clase}>
          <span className="badge badge--warn">{mensaje.mensaje}</span>
        </div>
      ))}

      {traslapes.length > 0 && (
        <div className="mb-8">
          <span
            className="badge badge--warn"
            title="Las dependencias son a nivel actividad, no a nivel tramo: el editor avisa y no reacomoda nada (§7.6)."
          >
            {traslapes.length}{' '}
            {traslapes.length === 1 ? 'sucesora cae' : 'sucesoras caen'} sobre un tramo de
            trabajo de su predecesora, no sobre su pausa.
          </span>
        </div>
      )}

      {huerfanos.length > 0 && (
        <div className="mb-8">
          <span className="badge badge--outline">
            {huerfanos.length} renglones de la versión anterior no apuntan a ningún nodo del
            árbol y no se dibujan; guardar los deja fuera.
          </span>
        </div>
      )}

      <div className="panel-prog">
        <div className={`canvas-prog${borrador === null ? ' canvas-prog--vacio' : ''}`}>
          {borrador === null ? (
            <div className="text-mute text-sm">Cargando el árbol del prototipo…</div>
          ) : nodosCanvas.length === 0 ? (
            <div className="empty">
              <div className="empty-title">
                {vista.modo === 'etapas'
                  ? 'Este prototipo no tiene etapas en su árbol'
                  : 'Esta vista no tiene conceptos'}
              </div>
              <div className="empty-sub">
                El programa base se arma sobre el árbol WBS del prototipo (§7.4). Sin
                ingeniería cargada no hay nodos que programar.
              </div>
            </div>
          ) : (
            <ReactFlow<CajaCanvas, Edge>
              nodes={nodosCanvas}
              edges={cablesCanvas as unknown as Edge[]}
              nodeTypes={TIPOS_NODO}
              edgeTypes={TIPOS_CABLE}
              onNodesChange={alCambiarNodos}
              onConnect={alConectar}
              onConnectStart={(_evento, parametros: OnConnectStartParams) => {
                anclajeSalida.current = parametros.handleId ?? null;
                gesto();
              }}
              onNodeDragStart={gesto}
              onNodeClick={(_evento, nodo: Node) => setSeleccionada(nodo.id)}
              onNodeDoubleClick={(_evento, nodo: Node) => {
                if (vista.modo === 'etapas') setVista({ modo: 'conceptos-de', etapaNodoId: nodo.id });
              }}
              onEdgeClick={(_evento, cable: Edge) => setSeleccionada(cable.target)}
              onPaneClick={() => setSeleccionada(null)}
              connectionMode={ConnectionMode.Loose}
              nodesDraggable={modo === 'seleccionar'}
              proOptions={{ hideAttribution: true }}
              minZoom={0.15}
              fitView
            >
              <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
              <Controls showInteractive={false} />
              <MiniMap pannable zoomable />
            </ReactFlow>
          )}
        </div>

        {borrador !== null && (
          <PanelCaja
            borrador={borrador}
            caja={cajaSeleccionada}
            frentes={frentes}
            colocado={colocado}
            duracionPrograma={duracionDelPrograma(colocado)}
            cicloDetectado={ciclo}
            onDuracion={(cajaId, duracionDias) =>
              despacha({ tipo: 'duracion', cajaId, duracionDias })
            }
            onFrente={(cajaId, frenteId) => despacha({ tipo: 'frente', cajaId, frenteId })}
            onTramos={(cajaId, tramos) => despacha({ tipo: 'tramos', cajaId, tramos })}
            onTipoLiga={(desde, hasta, tipoLiga) =>
              despacha({ tipo: 'ligar', desde, hasta, tipoLiga })
            }
            onLag={(desde, hasta, lagDias) => despacha({ tipo: 'lag', desde, hasta, lagDias })}
            onDesconectar={(desde, hasta) => despacha({ tipo: 'desconectar', desde, hasta })}
            onSeleccionar={setSeleccionada}
            onGesto={gesto}
          />
        )}
      </div>

      {borrador !== null && (
        <div className="text-xs text-mute mt-8">
          {borrador.cajas.filter(esRenglon).length} de {borrador.cajas.length} nodos del árbol
          tienen duración. Arrastra del anclaje derecho (fin) al izquierdo (inicio) para una
          liga fin → inicio; los otros tres tipos salen de los otros pares de anclajes.
        </div>
      )}
    </div>
  );
}
