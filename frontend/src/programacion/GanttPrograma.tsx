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
 * Componente de presentación (§12.11): la aritmética del arrastre, la del eje y
 * la de las flechas están fuera, en módulos que se prueban sin render.
 */

import { useMemo, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

import { fmtNum } from '@/lib/formato';
import {
  ASA_PX,
  diasDeDesplazamiento,
  previsualizar,
  type ClaseArrastre,
} from './arrastre';
import {
  comoPolilinea,
  trazarConectores,
  type AnclaBarra,
  type EntradaConector,
} from './conectores';
import {
  ALTO_ENCABEZADO,
  ALTO_FILA,
  anchoDeDias,
  etiquetaDeDia,
  xDeDia,
  type EjePrograma,
} from './ejePrograma';
import type { FilaPrograma } from './filasPrograma';
import { tramosVisibles } from './tramos';
import type { Colocacion } from './planificacion';

/** Alto de la barra de una actividad; el corchete del resumen es más fino. */
const ALTO_BARRA = 14;
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
  /** Precedencias entre renglones dibujados; ver `conectores.ts`. */
  readonly ligas: readonly EntradaConector[];
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
  ligas,
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
    const primero = montados[0]?.index ?? 0;
    const ultimo = montados[montados.length - 1]?.index ?? 0;
    return trazarConectores(ligas, anclas, {
      altoFila: ALTO_FILA,
      desdeFila: primero,
      hastaFila: ultimo,
    });
  }, [ligas, anclas, montados]);

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
        <div className="prog-gantt__head" style={{ height: ALTO_ENCABEZADO }}>
          {eje.bloques.map((bloque) => (
            <div
              key={bloque.dia}
              className={`prog-gantt__bloque${bloque.esHoy ? ' is-now' : ''}`}
              style={{ width: anchoDeDias(eje, 7) }}
            >
              {bloque.etiqueta}
            </div>
          ))}
        </div>

        <div
          className="prog-gantt__lienzo"
          style={{ height: alto, ['--paso-dia' as string]: `${eje.pxPorDia}px` }}
          onPointerMove={arrastrando === null ? undefined : alMover}
          onPointerUp={arrastrando === null ? undefined : alSoltar}
          onPointerCancel={arrastrando === null ? undefined : alSoltar}
        >
          <div className="prog-gantt__rejilla" aria-hidden />
          {xHoy !== null && (
            <div className="prog-gantt__hoy" style={{ left: xHoy }} aria-hidden title="Hoy" />
          )}

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
  editable,
  seleccionado,
  arrastre,
  onSeleccionar,
  onEmpezar,
}: {
  readonly fila: FilaPrograma;
  readonly eje: EjePrograma;
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

  const puesto: Colocacion = { inicioDias: fila.inicioDias, finDias: fila.finDias };
  const ventana =
    arrastre === null ? puesto : previsualizar(puesto, arrastre.clase, arrastre.deltaDias);

  const izquierda = xDeDia(eje, ventana.inicioDias);
  const ancho = Math.max(2, anchoDeDias(eje, ventana.finDias - ventana.inicioDias));
  const arriba = (ALTO_FILA - (fila.esResumen ? ALTO_CORCHETE : ALTO_BARRA)) / 2;

  if (fila.esResumen) {
    return (
      <>
        <div
          className="prog-gantt__corchete"
          style={{ left: izquierda, width: ancho, top: arriba, height: ALTO_CORCHETE }}
          title={`${fila.descripcion} · ${fmtNum(fila.diasLaborables)} d laborables en ${fmtNum(
            fila.diasCalendario,
          )} d de calendario · ${fila.nHojas} concepto${fila.nHojas === 1 ? '' : 's'}`}
        />
        <span className="prog-gantt__pata" style={{ left: izquierda, top: arriba + ALTO_CORCHETE }} />
        <span
          className="prog-gantt__pata"
          style={{ left: izquierda + ancho - 8, top: arriba + ALTO_CORCHETE }}
        />
      </>
    );
  }

  if (!fila.capturado) {
    return (
      <div
        className="prog-gantt__barra prog-gantt__barra--propuesta"
        style={{ left: izquierda, width: anchoDeDias(eje, 1), top: arriba, height: ALTO_BARRA }}
        title="Sin duración capturada: este renglón no entra al programa (§7.5)"
      />
    );
  }

  // Los tramos se dibujan relativos al arranque de la barra; sin interrupción
  // `tramosVisibles` devuelve un solo bloque y el bucle es el mismo (§7.6).
  const bloques = tramosVisibles(fila.diasLaborables ?? 0, fila.tramos);
  const clases = [
    'prog-gantt__barra',
    fila.enCiclo ? 'prog-gantt__barra--alerta' : '',
    seleccionado ? 'is-selected' : '',
  ]
    .filter((clase) => clase !== '')
    .join(' ');

  return (
    <>
      {/* La pausa entre dos tramos se dibuja como línea, no como hueco: un
          hueco a secas se lee como dos actividades distintas. */}
      {bloques.slice(0, -1).map((tramo, i) => {
        const siguiente = bloques[i + 1];
        if (!siguiente) return null;
        const desde = tramo.offsetDias + tramo.duracionDias;
        return (
          <div
            key={`pausa-${tramo.offsetDias}`}
            className="prog-gantt__pausa"
            style={{
              left: izquierda + anchoDeDias(eje, desde),
              width: anchoDeDias(eje, siguiente.offsetDias - desde),
              top: arriba + ALTO_BARRA / 2,
            }}
            aria-hidden
          />
        );
      })}

      {bloques.map((tramo, i) => {
        const esUltimo = i === bloques.length - 1;
        const x = izquierda + anchoDeDias(eje, tramo.offsetDias);
        const w = Math.max(2, anchoDeDias(eje, tramo.duracionDias));
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
            style={{ left: x, width: w, top: arriba, height: ALTO_BARRA }}
            title={`${fila.descripcion} · ${fmtNum(fila.diasLaborables)} d laborables · ${fmtNum(
              fila.diasCalendario,
            )} d de calendario · arranca ${etiquetaDeDia(eje, fila.inicioDias)}`}
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
      {fila.holguraDias !== null && fila.holguraDias > 0 && (
        <div
          className="prog-gantt__holgura"
          style={{
            left: izquierda + ancho,
            width: anchoDeDias(eje, fila.holguraDias),
            top: arriba + ALTO_BARRA / 2,
          }}
          aria-hidden
          title={`Holgura ${fmtNum(fila.holguraDias)} d`}
        />
      )}
    </>
  );
}
