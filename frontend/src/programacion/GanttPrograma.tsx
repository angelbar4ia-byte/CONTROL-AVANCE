/**
 * Mitad derecha del editor de programa base: el Gantt arrastrable (§7.5, §7.6).
 *
 * ## Por qué no es `Gantt.tsx`
 *
 * `Gantt.tsx` dibuja el cronograma de una **obra**: barras posicionadas en
 * porcentaje de un lienzo de fechas que el motor CPM ya resolvió, y de lectura
 * —lo que se edita ahí es una actividad, con su panel—. Aquí el lienzo es de
 * **días relativos** (`ejePrograma.ts`), la barra se arrastra, y una parte de
 * los renglones son resúmenes derivados que ni siquiera son actividades. No
 * comparten ni la escala, ni el modelo de fila, ni la interacción; lo que sí se
 * copia de él —porque es lo que funciona— es la técnica: pista relativa, barras
 * absolutas, CSS y nada de librería de Gantt.
 *
 * ## El arrastre despacha una sola vez
 *
 * Mientras se arrastra no se toca el borrador. Cada acción apila su propio paso
 * de deshacer (`borrador.ts`), así que correr una barra cuatro días dejaría
 * cuatro pasos atrás, y recolocar el grafo en cada `pointermove` redibujaría
 * 155 renglones sesenta veces por segundo. Lo que se ve mientras tanto es
 * `previsualizar` (`arrastre.ts`) sobre la ventana de la propia barra; al
 * soltar sale una acción, una sola, y el modelo recoloca todo lo que colgaba de
 * ella.
 *
 * ## Todo lo que el menú de herramientas decide llega resuelto
 *
 * El encabezado son dos bandas (`bandasPrograma.ts`), el color y la etiqueta de
 * cada barra los arma `barras.ts`, la cadena crítica llega como un conjunto de
 * ids (`rutaCritica.ts`) y qué se dibuja y qué no lo dice `vista`. Ninguna de
 * esas decisiones se toma aquí: este componente pinta (§12.11). Es lo que hace
 * que se puedan fijar con pruebas sin montar nada, que es lo que un Gantt
 * virtualizado hace muy incómodo de otra forma.
 */

import { useMemo, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

import {
  ASA_PX,
  diasDeDesplazamiento,
  previsualizar,
  type ClaseArrastre,
} from './arrastre';
import { LETRA_DIA, type BandasEje } from './bandasPrograma';
import { clasesDeBarra, etiquetaDeBarra, tituloDeBarra } from './barras';
import {
  comoPolilinea,
  trazarConectores,
  type AnclaBarra,
  type EntradaConector,
} from './conectores';
import {
  ALTO_ENCABEZADO,
  ALTO_FILA,
  anchoDeColumnas,
  anchoEntre,
  xDeDia,
  type EjePrograma,
} from './ejePrograma';
import type { FilaPrograma } from './filasPrograma';
import type { MagnitudesFila } from './reparto';
import { tramosVisibles } from './tramos';
import type { Colocacion } from './planificacion';
import type { VistaGantt } from './vistaGantt';

/** Alto de la barra de una actividad; el corchete del resumen es más fino. */
const ALTO_BARRA = 14;
const ALTO_BARRA_DELGADA = 6;
const ALTO_CORCHETE = 5;

interface Arrastrando {
  readonly cajaId: string;
  readonly clase: ClaseArrastre;
  readonly xInicial: number;
  readonly deltaDias: number;
}

interface Props {
  readonly filas: readonly FilaPrograma[];
  readonly eje: EjePrograma;
  /** Las dos bandas del encabezado y el paso de la rejilla. */
  readonly bandas: BandasEje;
  /** Costuras del calendario, para el fondo "bandas inhábiles". */
  /** Precedencias entre renglones dibujados; ver `conectores.ts`. */
  readonly ligas: readonly EntradaConector[];
  readonly vista: VistaGantt;
  /** Nodos de la cadena crítica del borrador (`rutaCritica.ts`). */
  readonly criticas: ReadonlySet<string>;
  /** Cantidad, importe y peso por renglón, para la etiqueta (`reparto.ts`). */
  readonly magnitudes: ReadonlyMap<string, MagnitudesFila>;
  /** Tono 1–6 del frente de cada renglón, cuando se colorea por frente. */
  readonly tonoPorNodo: ReadonlyMap<string, number>;
  readonly seleccionado: string | null;
  readonly editable: boolean;
  readonly onSeleccionar: (nodoId: string) => void;
  /** Se llama al soltar, una sola vez por arrastre. */
  readonly onSoltar: (cajaId: string, clase: ClaseArrastre, deltaDias: number) => void;
  readonly contenedorRef: React.RefObject<HTMLDivElement>;
  readonly onScroll: (scrollTop: number) => void;
}

export function GanttPrograma({
  filas,
  eje,
  bandas,
  ligas,
  vista,
  criticas,
  magnitudes,
  tonoPorNodo,
  seleccionado,
  editable,
  onSeleccionar,
  onSoltar,
  contenedorRef,
  onScroll,
}: Props) {
  const [arrastrando, setArrastrando] = useState<Arrastrando | null>(null);

  const virtualizador = useVirtualizer({
    count: filas.length,
    getScrollElement: () => contenedorRef.current,
    estimateSize: () => ALTO_FILA,
    overscan: 10,
    // El mismo margen que la tabla: los dos encabezados son pegajosos y miden
    // igual, que es lo que mantiene los dos lados renglón con renglón.
    scrollMargin: ALTO_ENCABEZADO,
  });

  const montados = virtualizador.getVirtualItems();
  const alto = virtualizador.getTotalSize();

  // Dónde cae cada barra, para las flechas. Se arma sobre las filas completas
  // —son ~155 entradas y cuesta nada— y `trazarConectores` recorta después a
  // la ventana montada, que es lo que evita dibujar doscientas polilíneas.
  const anclas = useMemo<ReadonlyMap<string, AnclaBarra>>(() => {
    const mapa = new Map<string, AnclaBarra>();
    filas.forEach((fila, indice) => {
      if (fila.inicioDias === null || fila.finDias === null) return;
      mapa.set(fila.nodoId, {
        fila: indice,
        x0: xDeDia(eje, fila.inicioDias),
        x1: xDeDia(eje, fila.finDias),
      });
    });
    return mapa;
  }, [filas, eje]);

  const conectores = useMemo(() => {
    if (!vista.verVinculos) return [];
    const primero = montados[0]?.index ?? 0;
    const ultimo = montados[montados.length - 1]?.index ?? 0;
    return trazarConectores(ligas, anclas, {
      altoFila: ALTO_FILA,
      desdeFila: primero,
      hastaFila: ultimo,
    });
  }, [ligas, anclas, montados, vista.verVinculos]);

  const xHoy = eje.diaDeHoy === null ? null : xDeDia(eje, eje.diaDeHoy);

  function alMover(evento: React.PointerEvent): void {
    setArrastrando((previo) =>
      previo === null
        ? previo
        : {
            ...previo,
            deltaDias: diasDeDesplazamiento(evento.clientX - previo.xInicial, eje.pxPorDia),
          },
    );
  }

  function alSoltar(): void {
    if (arrastrando !== null) {
      onSoltar(arrastrando.cajaId, arrastrando.clase, arrastrando.deltaDias);
    }
    setArrastrando(null);
  }

  return (
    <div
      className="prog-split__lado"
      ref={contenedorRef}
      onScroll={(evento) => onScroll(evento.currentTarget.scrollTop)}
    >
      <div className="prog-gantt" style={{ width: eje.ancho }}>
        {/* Dos alturas: el periodo grande arriba, el chico abajo. Con una sola
            fila, o se ve el detalle y se pierde en qué mes se está, o al revés
            (`bandasPrograma.ts`). */}
        <div className="prog-gantt__head" style={{ height: ALTO_ENCABEZADO }}>
          <div className="prog-gantt__banda">
            {bandas.superior.map((banda) => (
              <div
                key={`sup-${banda.dia}`}
                className={`prog-gantt__bloque${banda.esHoy ? ' is-now' : ''}${banda.laborable === false ? ' is-descanso' : ''}`}
                style={{ width: anchoDeColumnas(eje, banda.dias) }}
                title={banda.titulo}
              >
                {banda.etiqueta}
              </div>
            ))}
          </div>
          <div className="prog-gantt__banda prog-gantt__banda--fina">
            {bandas.inferior.map((banda) => (
              <div
                key={`inf-${banda.dia}`}
                className={`prog-gantt__bloque${banda.esHoy ? ' is-now' : ''}${banda.laborable === false ? ' is-descanso' : ''}`}
                style={{ width: anchoDeColumnas(eje, banda.dias) }}
                title={banda.titulo}
              >
                {/* A poco zoom no cabe ni un número de dos cifras: se deja la
                    celda muda antes que dibujar medio dígito recortado. */}
                {anchoDeColumnas(eje, banda.dias) >= 18 ? banda.etiqueta : ''}
              </div>
            ))}
          </div>
        </div>

        <div
          className="prog-gantt__lienzo"
          style={{
            height: alto,
            // El paso de la rejilla es el periodo de la banda inferior, no
            // siete días fijos: cambiar de escala tiene que mover las líneas
            // del fondo con el encabezado, o dejan de decir lo mismo.
            ['--paso-rejilla' as string]: `${bandas.diasPorPeriodo * eje.pxPorDia}px`,
          }}
          onPointerMove={arrastrando === null ? undefined : alMover}
          onPointerUp={arrastrando === null ? undefined : alSoltar}
          onPointerCancel={arrastrando === null ? undefined : alSoltar}
        >
          {vista.fondoGantt === 'cuadricula' && (
            <div className="prog-gantt__rejilla" aria-hidden />
          )}
          {/* Las columnas que no se trabajan se tiñen enteras. Antes se
              marcaba con una línea el punto del salto, porque el fin de semana
              no ocupaba lugar en el lienzo; ahora ocupa el suyo y lo que hace
              falta es distinguirlo, no señalarlo. */}
          {vista.fondoGantt === 'inhabiles' &&
            eje.columnas
              .filter((columna) => columna.diaHabil === null)
              .map((columna) => (
                <div
                  key={`descanso-${columna.columna}`}
                  className="prog-gantt__descanso"
                  style={{
                    left: columna.columna * eje.pxPorDia,
                    width: eje.pxPorDia,
                  }}
                  title={`${LETRA_DIA[columna.diaSemana - 1]} — no se trabaja`}
                />
              ))}
          {xHoy !== null && (
            <div className="prog-gantt__hoy" style={{ left: xHoy }} aria-hidden title="Hoy" />
          )}

          {vista.verVinculos && (
            <svg
              className="prog-gantt__flechas"
              width={eje.ancho}
              height={alto}
              aria-hidden
              focusable="false"
            >
              {conectores.map((conector) => (
                <polyline
                  key={conector.id}
                  className={`prog-gantt__flecha${
                    conector.alerta ? ' prog-gantt__flecha--alerta' : ''
                  }`}
                  points={comoPolilinea(conector)}
                />
              ))}
            </svg>
          )}

          {montados.map((item) => {
            const fila = filas[item.index];
            if (!fila) return null;
            return (
              <div
                key={fila.nodoId}
                className="prog-gantt__pista"
                style={{
                  height: ALTO_FILA,
                  transform: `translateY(${item.start - ALTO_ENCABEZADO}px)`,
                }}
              >
                <Barra
                  fila={fila}
                  eje={eje}
                  vista={vista}
                  esCritica={criticas.has(fila.nodoId)}
                  magnitudes={magnitudes.get(fila.nodoId)}
                  tonoFrente={tonoPorNodo.get(fila.nodoId) ?? null}
                  editable={editable}
                  seleccionado={seleccionado === fila.nodoId}
                  arrastre={arrastrando?.cajaId === fila.nodoId ? arrastrando : null}
                  onSeleccionar={onSeleccionar}
                  onEmpezar={(clase, x) =>
                    setArrastrando({ cajaId: fila.nodoId, clase, xInicial: x, deltaDias: 0 })
                  }
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/**
 * La barra de un renglón, en una de sus tres formas.
 *
 *  - **Resumen**: el corchete de MS Project —una línea fina con dos patas—, que
 *    abarca a sus hijos y no se arrastra: es derivado (§7.4).
 *  - **Actividad**: la barra azul, arrastrable de cuerpo (mover) y de borde
 *    (estirar). Con la actividad partida son varios bloques con la pausa
 *    dibujada entre ellos (§7.6).
 *  - **Propuesta**: el nodo del árbol al que todavía no se le capturó duración.
 *    Se dibuja punteada y del ancho de un día, para que exista en la lista sin
 *    fingir una ventana que nadie decidió.
 */
function Barra({
  fila,
  eje,
  vista,
  esCritica,
  magnitudes,
  tonoFrente,
  editable,
  seleccionado,
  arrastre,
  onSeleccionar,
  onEmpezar,
}: {
  readonly fila: FilaPrograma;
  readonly eje: EjePrograma;
  readonly vista: VistaGantt;
  readonly esCritica: boolean;
  readonly magnitudes: MagnitudesFila | undefined;
  readonly tonoFrente: number | null;
  readonly editable: boolean;
  readonly seleccionado: boolean;
  readonly arrastre: Arrastrando | null;
  readonly onSeleccionar: (nodoId: string) => void;
  readonly onEmpezar: (clase: ClaseArrastre, xInicial: number) => void;
}) {
  if (fila.inicioDias === null || fila.finDias === null) {
    return (
      <span
        className="prog-gantt__etq text-faint"
        style={{ left: 6, top: (ALTO_FILA - 12) / 2 }}
      >
        sin duración
      </span>
    );
  }

  // El resumen apagado no deja hueco: el renglón sigue ahí en la tabla, y su
  // pista en blanco es exactamente lo que el usuario pidió al apagarlo.
  if (fila.esResumen && !vista.verResumen) return null;

  const puesto: Colocacion = { inicioDias: fila.inicioDias, finDias: fila.finDias };
  const ventana =
    arrastre === null ? puesto : previsualizar(puesto, arrastre.clase, arrastre.deltaDias);

  const izquierda = xDeDia(eje, ventana.inicioDias);
  // El ancho va de extremo a extremo y no es la duración por el zoom: cinco
  // días de trabajo ocupan siete columnas si les cae un fin de semana en medio.
  const ancho = Math.max(2, anchoEntre(eje, ventana.inicioDias, ventana.finDias));
  const altoBarra = vista.estiloBarra === 'delgada' ? ALTO_BARRA_DELGADA : ALTO_BARRA;
  const arriba = (ALTO_FILA - (fila.esResumen ? ALTO_CORCHETE : altoBarra)) / 2;

  if (fila.esResumen) {
    return (
      <>
        {/* El corchete se arrastra y se lleva el bloque entero
            (`gestos.desplazarBloque`). No tiene asa de borde: estirar un
            resumen no es una operación —su ancho lo ponen sus hijos. */}
        <div
          className={`prog-gantt__corchete${esCritica && vista.rutaCritica ? ' is-critica' : ''}`}
          style={{
            left: izquierda,
            width: ancho,
            top: arriba,
            height: ALTO_CORCHETE,
            cursor: editable ? 'grab' : undefined,
          }}
          title={tituloDeBarra(fila, eje, esCritica)}
          onClick={() => onSeleccionar(fila.nodoId)}
          onPointerDown={(evento) => {
            if (!editable) return;
            evento.currentTarget.setPointerCapture(evento.pointerId);
            onEmpezar('mover', evento.clientX);
          }}
        />
        <span className="prog-gantt__pata" style={{ left: izquierda, top: arriba + ALTO_CORCHETE }} />
        <span
          className="prog-gantt__pata"
          style={{ left: izquierda + ancho - 8, top: arriba + ALTO_CORCHETE }}
        />
        <Etiqueta
          texto={etiquetaDeBarra(vista, fila, magnitudes)}
          posicion={vista.posicionEtiqueta}
          izquierda={izquierda}
          ancho={ancho}
        />
      </>
    );
  }

  if (!fila.capturado) {
    return (
      <div
        className="prog-gantt__barra prog-gantt__barra--propuesta"
        style={{ left: izquierda, width: anchoEntre(eje, ventana.inicioDias, ventana.inicioDias + 1), top: arriba, height: altoBarra }}
        title="Sin duración capturada: este renglón no entra al programa (§7.5)"
      />
    );
  }

  // Los tramos se dibujan relativos al arranque de la barra; sin interrupción
  // `tramosVisibles` devuelve un solo bloque y el bucle es el mismo (§7.6).
  const bloques = tramosVisibles(fila.diasLaborables ?? 0, fila.tramos);
  const clases = clasesDeBarra({ vista, fila, esCritica, tonoFrente, seleccionada: seleccionado });
  const titulo = tituloDeBarra(fila, eje, esCritica);

  return (
    <>
      {/* La pausa entre dos tramos se dibuja como línea, no como hueco: un
          hueco a secas se lee como dos actividades distintas. */}
      {vista.verPausas &&
        bloques.slice(0, -1).map((tramo, i) => {
          const siguiente = bloques[i + 1];
          if (!siguiente) return null;
          const desde = tramo.offsetDias + tramo.duracionDias;
          return (
            <div
              key={`pausa-${tramo.offsetDias}`}
              className="prog-gantt__pausa"
              style={{
                left: izquierda + anchoEntre(eje, ventana.inicioDias, ventana.inicioDias + desde),
                width: anchoEntre(
                  eje,
                  ventana.inicioDias + desde,
                  ventana.inicioDias + siguiente.offsetDias,
                ),
                top: arriba + altoBarra / 2,
              }}
              aria-hidden
            />
          );
        })}

      {bloques.map((tramo, i) => {
        const esUltimo = i === bloques.length - 1;
        const x =
          izquierda + anchoEntre(eje, ventana.inicioDias, ventana.inicioDias + tramo.offsetDias);
        const w = Math.max(
          2,
          anchoEntre(
            eje,
            ventana.inicioDias + tramo.offsetDias,
            ventana.inicioDias + tramo.offsetDias + tramo.duracionDias,
          ),
        );
        return (
          <div
            key={`tramo-${tramo.offsetDias}`}
            className={clases}
            // La barra es la representación **visual** de un renglón que la
            // tabla ya expone completo y accesible —descripción, fechas, días y
            // el campo donde se captura la duración—. Anunciarla otra vez aquí
            // haría que un lector de pantalla leyera cada actividad dos veces
            // sin añadir nada, así que el Gantt es la mitad que se mira y la
            // tabla la que se navega (§12.10).
            aria-hidden
            style={{ left: x, width: w, top: arriba, height: altoBarra }}
            title={titulo}
            onClick={() => onSeleccionar(fila.nodoId)}
            onPointerDown={(evento) => {
              if (!editable) return;
              evento.currentTarget.setPointerCapture(evento.pointerId);
              onEmpezar('mover', evento.clientX);
            }}
          >
            {esUltimo && editable && (
              <span
                className="prog-gantt__asa"
                // A poco zoom la barra mide menos que el asa: se recorta a un
                // tercio para que siempre quede cuerpo que agarrar.
                style={{ width: Math.max(3, Math.min(ASA_PX, w / 3)) }}
                onPointerDown={(evento) => {
                  evento.stopPropagation();
                  evento.currentTarget.setPointerCapture(evento.pointerId);
                  onEmpezar('estirar', evento.clientX);
                }}
              />
            )}
          </div>
        );
      })}

      {/* La holgura, en la representación clásica: la cola que sigue a la
          barra y dice cuánto puede correrse sin empujar el cierre. */}
      {vista.verHolgura && fila.holguraDias !== null && fila.holguraDias > 0 && (
        <div
          className="prog-gantt__holgura"
          style={{
            left: izquierda + ancho,
            width: anchoEntre(eje, ventana.finDias, ventana.finDias + fila.holguraDias),
            top: arriba + altoBarra / 2,
          }}
          aria-hidden
          title={`Holgura ${fila.holguraDias} d`}
        />
      )}

      <Etiqueta
        texto={etiquetaDeBarra(vista, fila, magnitudes)}
        posicion={vista.posicionEtiqueta}
        izquierda={izquierda}
        ancho={ancho}
      />
    </>
  );
}

/**
 * La etiqueta de una barra.
 *
 * `aria-hidden` por lo mismo que la barra: repite lo que la tabla ya dice en
 * columnas, y anunciarla haría que cada renglón se leyera dos veces (§12.10).
 * A la izquierda se ancla por el borde derecho —`right` sobre el arranque de la
 * barra— porque una etiqueta izquierda tiene que crecer hacia afuera y no
 * comerse la barra.
 */
function Etiqueta({
  texto,
  posicion,
  izquierda,
  ancho,
}: {
  readonly texto: string;
  readonly posicion: 'izquierda' | 'dentro' | 'derecha';
  readonly izquierda: number;
  readonly ancho: number;
}) {
  if (texto === '') return null;

  const arriba = (ALTO_FILA - 12) / 2;
  if (posicion === 'izquierda') {
    return (
      <span
        className="prog-gantt__etq prog-gantt__etq--izq"
        aria-hidden
        style={{ left: Math.max(0, izquierda - 6), top: arriba }}
      >
        {texto}
      </span>
    );
  }
  if (posicion === 'dentro') {
    return (
      <span
        className="prog-gantt__etq prog-gantt__etq--dentro"
        aria-hidden
        style={{ left: izquierda + 4, top: arriba, maxWidth: Math.max(0, ancho - 8) }}
      >
        {texto}
      </span>
    );
  }
  return (
    <span
      className="prog-gantt__etq"
      aria-hidden
      style={{ left: izquierda + ancho + 6, top: arriba }}
    >
      {texto}
    </span>
  );
}
