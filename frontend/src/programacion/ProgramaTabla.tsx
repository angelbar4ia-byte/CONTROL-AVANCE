/**
 * Editor de programa base en **tabla + Gantt** (§7.4, §7.5, §11.2
 * `POST /programas-base`).
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
 * ## Lo que se adelanta al backend
 *
 * Los ciclos de precedencias (`ciclos.ts`). El backend responde 422 **sin
 * escribir nada** del programa completo si hay uno, así que descubrirlo al
 * guardar cuesta la sesión entera; aquí se señala el renglón que participa y no
 * se deja guardar. La ruta crítica y las fechas reales siguen siendo del motor
 * (§6): esta pantalla no las calcula ni pretende hacerlo.
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
import { ChevronsDownUp, ChevronsUpDown, Redo2, Undo2 } from 'lucide-react';

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
import { resolverArrastre, empezarArrastre, type ClaseArrastre } from './arrastre';
import {
  deshacer as deshacerHistorial,
  despachar,
  historialInicial,
  puedeDeshacer,
  puedeRehacer,
  rehacer as rehacerHistorial,
  type Accion,
  type Historial,
} from './borrador';
import { SEMANA_NATURAL, descripcionDeSemana, normalizarDias } from './calendario';
import { buscarCiclo } from './ciclos';
import type { EntradaConector } from './conectores';
import {
  ZOOM_EJE,
  ZOOM_POR_DEFECTO,
  construirEje,
  type ModoEje,
} from './ejePrograma';
import {
  aplanarPrograma,
  colapsadosDeEntrada,
  filtrarPorTexto,
  resumirFilas,
  todosLosPadres,
} from './filasPrograma';
import { GanttPrograma } from './GanttPrograma';
import { armarBorrador, aristas, itemsDelBorrador } from './grafo';
import { alternarColapso, visiblesEnJerarquia } from './jerarquia';
import { colocar, duracionDelPrograma } from './planificacion';
import { puedeAdministrarProgramasBase } from './reglas';
import { SINCRONIA_INICIAL, alDesplazar, reiniciarSincronia } from './sincronia';
import { TablaPrograma } from './TablaPrograma';

/**
 * Reparto inicial y topes del panel dividido, en px.
 *
 * El mínimo deja ver número, tipo, clave y descripción —lo que hace falta para
 * saber en qué renglón se está—; el máximo impide dejar el Gantt en una franja
 * donde una barra ya no dice nada.
 */
const ANCHO_TABLA_POR_DEFECTO = 620;
const ANCHO_TABLA_MINIMO = 240;
const ANCHO_TABLA_MAXIMO = 1100;

function recortarAncho(px: number): number {
  return Math.round(Math.min(ANCHO_TABLA_MAXIMO, Math.max(ANCHO_TABLA_MINIMO, px)));
}

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
  // Unidad y cantidad son del **presupuesto vigente** del prototipo, unidas por
  // `prototipo_nodo_id`, igual que en `ArbolPrototipo`: el nodo del árbol no
  // las trae. Sin presupuesto cargado las dos columnas quedan vacías, que es
  // preferible a inventarlas.
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
  const [zoom, setZoom] = useState(ZOOM_POR_DEFECTO);
  const [modoEje, setModoEje] = useState<ModoEje>('relativo');
  const [inicioSimulado, setInicioSimulado] = useState(hoyIso());
  const [diasHabiles, setDiasHabiles] = useState<readonly number[]>(SEMANA_NATURAL);
  const [profundidad, setProfundidad] = useState<ClaseNodo>('concepto');
  const [aviso, setAviso] = useState<string | null>(null);
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [anchoTabla, setAnchoTabla] = useState(ANCHO_TABLA_POR_DEFECTO);
  const tirador = useRef<{ readonly x: number; readonly ancho: number } | null>(null);

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
        pxPorDia: zoom,
        modo: modoEje,
        inicio: inicioSimulado,
        diasHabiles,
        hoy: hoyIso(),
      }),
    [colocado, zoom, modoEje, inicioSimulado, diasHabiles],
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

  const alternar = useCallback((nodoId: string) => {
    setColapsados((previos) => alternarColapso(previos, nodoId));
  }, []);

  const cambiarDuracion = useCallback(
    (nodoId: string, dias: number | null) => {
      despacha({ tipo: 'duracion', cajaId: nodoId, duracionDias: dias });
    },
    [despacha],
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
  // la altura anterior bloquearía el primer scroll de la nueva.
  useEffect(() => {
    sincronia.current = reiniciarSincronia(refTabla.current?.scrollTop ?? 0);
  }, [visibles.length]);

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

  if (!sesion || rol === null) return null;

  if (!administra) {
    return (
      <Marco>
        <div className="text-mute text-sm" style={{ padding: '24px 12px' }}>
          Los programas base de duraciones los administra Control de obra (§11.2).
        </div>
      </Marco>
    );
  }

  if (prototipoId === '') {
    return (
      <Marco>
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
          rechazaría sin escribir nada (§6). Quítalo desde el canvas.
        </div>
      )}
      {huerfanos.length > 0 && (
        <div className="badge badge--warn">
          {huerfanos.length} renglón(es) de la versión abierta apuntan a nodos que ya no están
          en el árbol y no se dibujan.
        </div>
      )}

      <div className="filterbar">
        <input
          className="input search"
          placeholder="Buscar por clave o descripción"
          value={busqueda}
          onChange={(evento) => setBusqueda(evento.target.value)}
          aria-label="Buscar renglón"
        />

        <button
          type="button"
          className="btn btn--sm"
          onClick={() => setColapsados(todosLosPadres(todas))}
          title="Plegar todo el árbol"
        >
          <ChevronsDownUp size={14} /> Plegar
        </button>
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => setColapsados(new Set())}
          title="Desplegar todo el árbol"
        >
          <ChevronsUpDown size={14} /> Desplegar
        </button>

        <span className="divider-v" />

        {/* El eje: días relativos por defecto porque un programa base es una
            plantilla sin fechas propias; las fechas son una simulación contra
            un arranque concreto y se rotulan como tal (§7.5). */}
        <label className="field__label" htmlFor="modo-eje">
          Eje
        </label>
        <select
          id="modo-eje"
          className="input"
          style={{ width: 150 }}
          value={eje.modo}
          onChange={(evento) => setModoEje(evento.target.value as ModoEje)}
        >
          <option value="relativo">Días relativos</option>
          <option value="fechas">Fechas simuladas</option>
        </select>
        {eje.modo === 'fechas' && (
          <input
            className="input"
            style={{ width: 150 }}
            type="date"
            value={inicioSimulado}
            aria-label="Arranque de la simulación"
            onChange={(evento) => setInicioSimulado(evento.target.value)}
          />
        )}

        <label className="field__label" htmlFor="zoom-eje">
          Zoom
        </label>
        <select
          id="zoom-eje"
          className="input"
          style={{ width: 110 }}
          value={zoom}
          onChange={(evento) => setZoom(Number(evento.target.value))}
        >
          {ZOOM_EJE.map((px) => (
            <option key={px} value={px}>
              {px} px/día
            </option>
          ))}
        </select>

        <span className="divider-v" />

        <button
          type="button"
          className="btn btn--sm btn--icon"
          disabled={historial === null || !puedeDeshacer(historial)}
          title="Deshacer (Ctrl+Z)"
          aria-label="Deshacer"
          onClick={() =>
            setHistorial((previo) => (previo === null ? previo : deshacerHistorial(previo)))
          }
        >
          <Undo2 size={14} />
        </button>
        <button
          type="button"
          className="btn btn--sm btn--icon"
          disabled={historial === null || !puedeRehacer(historial)}
          title="Rehacer (Ctrl+Shift+Z)"
          aria-label="Rehacer"
          onClick={() =>
            setHistorial((previo) => (previo === null ? previo : rehacerHistorial(previo)))
          }
        >
          <Redo2 size={14} />
        </button>

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
        <div className="prog-split" style={{ ['--prog-tabla-w' as string]: `${anchoTabla}px` }}>
          <TablaPrograma
            filas={visibles}
            eje={eje}
            colapsados={colapsados}
            seleccionado={seleccionado}
            editable
            onAlternar={alternar}
            onSeleccionar={setSeleccionado}
            onDuracion={cambiarDuracion}
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
            aria-valuenow={anchoTabla}
            aria-valuemin={ANCHO_TABLA_MINIMO}
            aria-valuemax={ANCHO_TABLA_MAXIMO}
            tabIndex={0}
            onPointerDown={(evento) => {
              evento.currentTarget.setPointerCapture(evento.pointerId);
              tirador.current = { x: evento.clientX, ancho: anchoTabla };
            }}
            onPointerMove={(evento) => {
              const inicio = tirador.current;
              if (inicio === null) return;
              setAnchoTabla(recortarAncho(inicio.ancho + evento.clientX - inicio.x));
            }}
            onPointerUp={() => {
              tirador.current = null;
            }}
            onKeyDown={(evento) => {
              const paso = evento.key === 'ArrowLeft' ? -24 : evento.key === 'ArrowRight' ? 24 : 0;
              if (paso === 0) return;
              evento.preventDefault();
              setAnchoTabla((previo) => recortarAncho(previo + paso));
            }}
          />
          <GanttPrograma
            filas={visibles}
            eje={eje}
            ligas={ligas}
            seleccionado={seleccionado}
            editable
            onSeleccionar={setSeleccionado}
            onSoltar={alSoltar}
            contenedorRef={refGantt}
            onScroll={(top) => desplazar('gantt', top)}
          />
        </div>
      )}

      <p className="text-xs text-mute mt-8">
        Arrastrar el cuerpo de una barra corre la actividad cambiando el lag de la
        precedencia que la detiene; arrastrar su borde derecho cambia la duración. Las barras
        de nivel y etapa son el resumen derivado de sus hijos y no se arrastran (§7.4). Las
        precedencias se tienden en el canvas.
      </p>
    </Marco>
  );
}

/** Encabezado de la pantalla, igual en los tres estados (sin rol, sin prototipo, editor). */
function Marco({
  titulo = 'Programa base · tabla y Gantt',
  acciones,
  children,
}: {
  readonly titulo?: string;
  readonly acciones?: React.ReactNode;
  readonly children: React.ReactNode;
}) {
  return (
    <div className="page">
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
