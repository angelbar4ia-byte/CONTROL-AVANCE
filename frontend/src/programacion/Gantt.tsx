/**
 * Gantt del cronograma de una obra (§11.2 "Web: Gantt con ruta crítica
 * resaltada"; DESIGN_SYSTEM.md §4 `.gantt`).
 *
 * Componente **de presentación pura**: recibe filas ya normalizadas
 * (`filas.ts`) y una escala ya construida (`escala.ts`), y las dibuja con las
 * clases y tokens del sistema de diseño. No calcula fechas, no propaga
 * dependencias y no decide qué es crítico: todo eso llega resuelto del motor
 * CPM del backend (§6, §12.11).
 *
 * Se dibuja con CSS: la pista es un contenedor relativo y cada barra un
 * bloque absoluto posicionado en porcentaje del lienzo. No hay librería de
 * Gantt ni `<canvas>`.
 *
 * ## Virtualización (§12.9)
 *
 * Un cronograma de obra son decenas de renglones y montarlos todos no pesa;
 * pasado un umbral se virtualiza con `@tanstack/react-virtual`, que ya es
 * dependencia del proyecto, para que el árbol del DOM no crezca con la obra.
 */

import { useMemo, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

import { fmtFecha, fmtNum, fmtPct } from '@/lib/formato';
import type { Escala } from './escala';
import { posicionDeFecha, tramoDeBarra, tramoDeHolgura } from './escala';
import type { FilaGantt, GrupoGantt } from './filas';
import type { FilaJerarquia } from './jerarquia';
import { claseBarra, etiquetaTono, tonoBarra } from './reglas';

/** Alturas de `.gantt__row` y `.gantt__group` en el sistema de diseño. */
const ALTO_FILA = 36;
const ALTO_GRUPO = 33;

/** A partir de aquí se virtualiza; por debajo el DOM completo es más simple. */
const UMBRAL_VIRTUAL = 80;

/** Alto máximo del lienzo cuando se virtualiza (necesita un viewport fijo). */
const ALTO_VISIBLE = 560;

type Renglon =
  | { readonly tipo: 'grupo'; readonly grupo: GrupoGantt }
  | { readonly tipo: 'fila'; readonly fila: FilaGantt }
  | { readonly tipo: 'nodo'; readonly nodo: FilaJerarquia };

interface Props {
  /** Vista plana: actividades agrupadas por frente (§8.3). */
  readonly grupos?: readonly GrupoGantt[];
  /**
   * Vista jerárquica: el árbol WBS con sus barras resumen (§7.4). Cuando llega,
   * sustituye a `grupos` como fuente de renglones — son dos lecturas del mismo
   * cronograma y mezclarlas dibujaría cada actividad dos veces.
   */
  readonly jerarquia?: readonly FilaJerarquia[];
  readonly escala: Escala;
  /** Fecha contra la que el motor midió el desfase (§6); se marca en la pista. */
  readonly fechaCorte: string | null;
  readonly seleccionada: string | null;
  readonly onSeleccionar: (fila: FilaGantt) => void;
  /** Colapsar/expandir un nodo resumen. Sin él, el árbol se dibuja fijo. */
  readonly colapsados?: ReadonlySet<string>;
  readonly onAlternar?: (nodoId: string) => void;
  /**
   * Programar un nodo resumen: repartir su ventana entre los conceptos que
   * cuelgan de él (§11.2). Sólo se ofrece si el rol edita el cronograma; la
   * barra resumen sigue siendo de lectura para todo lo demás.
   */
  readonly onProgramarNodo?: (nodo: FilaJerarquia) => void;
}

export function Gantt({
  grupos,
  jerarquia,
  escala,
  fechaCorte,
  seleccionada,
  onSeleccionar,
  colapsados,
  onAlternar,
  onProgramarNodo,
}: Props) {
  const renglones = useMemo<readonly Renglon[]>(() => {
    if (jerarquia !== undefined) {
      return jerarquia.map((nodo) => ({ tipo: 'nodo', nodo }) as const);
    }
    const lista: Renglon[] = [];
    for (const grupo of grupos ?? []) {
      lista.push({ tipo: 'grupo', grupo });
      for (const fila of grupo.filas) lista.push({ tipo: 'fila', fila });
    }
    return lista;
  }, [grupos, jerarquia]);

  const contenedor = useRef<HTMLDivElement>(null);
  const virtualiza = renglones.length > UMBRAL_VIRTUAL;

  const virtualizador = useVirtualizer({
    count: virtualiza ? renglones.length : 0,
    getScrollElement: () => contenedor.current,
    estimateSize: (indice) => (renglones[indice]?.tipo === 'grupo' ? ALTO_GRUPO : ALTO_FILA),
    overscan: 8,
  });

  const corte = posicionDeFecha(escala, fechaCorte);

  return (
    <div
      className="gantt"
      ref={contenedor}
      style={virtualiza ? { maxHeight: ALTO_VISIBLE, overflowY: 'auto' } : undefined}
    >
      <div
        className="gantt__head"
        style={{ minWidth: escala.anchoMinimo, position: 'sticky', top: 0, zIndex: 2 }}
      >
        <div className="gantt__head-left">Actividad</div>
        <div className="gantt__timeline">
          {escala.semanas.map((semana) => (
            <div
              key={semana.inicio}
              className={`gantt__week${semana.esCorte ? ' is-now' : ''}`}
              title={`Semana del ${fmtFecha(semana.inicio)}`}
            >
              {semana.etiqueta}
            </div>
          ))}
        </div>
      </div>

      {virtualiza ? (
        <div
          style={{
            minWidth: escala.anchoMinimo,
            height: virtualizador.getTotalSize(),
            position: 'relative',
          }}
        >
          {virtualizador.getVirtualItems().map((item) => {
            const renglon = renglones[item.index];
            if (!renglon) return null;
            return (
              <div
                key={item.key}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  transform: `translateY(${item.start}px)`,
                }}
              >
                <PintarRenglon
                  renglon={renglon}
                  escala={escala}
                  corte={corte}
                  seleccionada={seleccionada}
                  onSeleccionar={onSeleccionar}
                  colapsados={colapsados}
                  onAlternar={onAlternar}
                  onProgramarNodo={onProgramarNodo}
                />
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{ minWidth: escala.anchoMinimo }}>
          {renglones.map((renglon) => (
            <PintarRenglon
              key={claveDeRenglon(renglon)}
              renglon={renglon}
              escala={escala}
              corte={corte}
              seleccionada={seleccionada}
              onSeleccionar={onSeleccionar}
              colapsados={colapsados}
              onAlternar={onAlternar}
              onProgramarNodo={onProgramarNodo}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function claveDeRenglon(renglon: Renglon): string {
  if (renglon.tipo === 'grupo') return `g:${renglon.grupo.clave}`;
  if (renglon.tipo === 'nodo') return `n:${renglon.nodo.nodoId}`;
  return renglon.fila.actividadId;
}

function PintarRenglon({
  renglon,
  escala,
  corte,
  seleccionada,
  onSeleccionar,
  colapsados,
  onAlternar,
  onProgramarNodo,
}: {
  readonly renglon: Renglon;
  readonly escala: Escala;
  readonly corte: number | null;
  readonly seleccionada: string | null;
  readonly onSeleccionar: (fila: FilaGantt) => void;
  readonly colapsados?: ReadonlySet<string>;
  readonly onAlternar?: (nodoId: string) => void;
  readonly onProgramarNodo?: (nodo: FilaJerarquia) => void;
}) {
  if (renglon.tipo === 'grupo') {
    return <EncabezadoGrupo grupo={renglon.grupo} />;
  }
  if (renglon.tipo === 'nodo') {
    return (
      <RenglonDelArbol
        nodo={renglon.nodo}
        escala={escala}
        corte={corte}
        seleccionada={seleccionada === renglon.nodo.nodoId}
        colapsado={colapsados?.has(renglon.nodo.nodoId) ?? false}
        onSeleccionar={onSeleccionar}
        onAlternar={onAlternar}
        onProgramarNodo={onProgramarNodo}
      />
    );
  }
  return (
    <Renglon
      fila={renglon.fila}
      escala={escala}
      corte={corte}
      seleccionada={seleccionada === renglon.fila.actividadId}
      onSeleccionar={onSeleccionar}
    />
  );
}

/**
 * Renglón del Gantt jerárquico (§7.4).
 *
 * Un `concepto` con su actividad delega en el renglón de siempre: es la misma
 * barra, con su criticidad y su holgura, sólo sangrada. Un `nivel` o una
 * `etapa` dibujan su **barra resumen derivada**, que no se selecciona para
 * editar —no es una fila de `actividad` (§11.3 A.2)— y sólo ofrece
 * "Programar", que reparte su ventana hacia abajo (§11.2).
 */
function RenglonDelArbol({
  nodo,
  escala,
  corte,
  seleccionada,
  colapsado,
  onSeleccionar,
  onAlternar,
  onProgramarNodo,
}: {
  readonly nodo: FilaJerarquia;
  readonly escala: Escala;
  readonly corte: number | null;
  readonly seleccionada: boolean;
  readonly colapsado: boolean;
  readonly onSeleccionar: (fila: FilaGantt) => void;
  readonly onAlternar?: (nodoId: string) => void;
  readonly onProgramarNodo?: (nodo: FilaJerarquia) => void;
}) {
  const sangria = nodo.profundidad * 14;

  if (!nodo.esResumen && nodo.fila) {
    return (
      <Renglon
        fila={nodo.fila}
        escala={escala}
        corte={corte}
        seleccionada={seleccionada}
        onSeleccionar={onSeleccionar}
        sangria={sangria}
      />
    );
  }

  const barra = tramoDeBarra(escala, nodo.inicio, nodo.fin);
  const avance = Math.min(100, Math.max(0, nodo.avancePct));

  return (
    <div className="gantt__row">
      <div className="gantt__label" style={{ paddingLeft: 8 + sangria }}>
        <span className="row gap-4" style={{ alignItems: 'center' }}>
          {nodo.tieneHijos && onAlternar !== undefined ? (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              style={{ padding: '0 4px', minWidth: 0 }}
              aria-expanded={!colapsado}
              aria-label={`${colapsado ? 'Expandir' : 'Colapsar'} ${nodo.nombre}`}
              onClick={() => onAlternar(nodo.nodoId)}
            >
              {colapsado ? '▸' : '▾'}
            </button>
          ) : (
            <span aria-hidden style={{ width: 14 }} />
          )}
          <strong
            style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            {nodo.nombre}
          </strong>
          {nodo.conflicto !== null && (
            <span
              className="badge badge--warn"
              title={
                `El nodo declara ${nodo.conflicto.dias_capturados} días y sus ` +
                `${nodo.conflicto.actividades.length} concepto(s) programados ocupan ` +
                `${nodo.conflicto.dias_derivados}. Decide cuál conservar (§7.5).`
              }
            >
              conflicto
            </span>
          )}
        </span>
        <small className="tnum">
          {nodo.tipo} · {fmtFecha(nodo.inicio)} → {fmtFecha(nodo.fin)} ·{' '}
          {fmtNum(nodo.duracionDias)} d · {nodo.nActividades} concepto
          {nodo.nActividades === 1 ? '' : 's'} · {fmtPct(nodo.avancePct)}
          {onProgramarNodo !== undefined && (
            <>
              {' · '}
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                style={{ padding: 0, minWidth: 0, font: 'inherit' }}
                onClick={() => onProgramarNodo(nodo)}
              >
                Programar
              </button>
            </>
          )}
        </small>
      </div>

      <div className="gantt__track">
        {corte !== null && (
          <div
            aria-hidden
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: `${corte}%`,
              width: 1,
              background: 'var(--c-accent-strong)',
              opacity: 0.45,
            }}
          />
        )}

        {barra ? (
          // La barra resumen se dibuja como el corchete de MS Project —fina y
          // sin relleno de avance en el cuerpo— para que se lea distinta de una
          // actividad: es derivada y no se captura sobre ella.
          <div
            aria-hidden
            title={`${nodo.nombre} · ${fmtNum(nodo.duracionDias)} d · avance ${fmtPct(
              nodo.avancePct,
            )} (ponderado por importe)`}
            style={{
              position: 'absolute',
              top: 13,
              height: 10,
              left: `${barra.izquierda}%`,
              width: `${barra.ancho}%`,
              background: 'var(--c-line-strong)',
              borderRadius: 2,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${avance}%`,
                background: 'var(--c-accent-strong)',
                opacity: 0.75,
              }}
            />
          </div>
        ) : (
          <span
            className="text-faint text-xs mono"
            style={{ position: 'absolute', left: 8, top: 10 }}
          >
            sin fechas
          </span>
        )}
      </div>
    </div>
  );
}

function EncabezadoGrupo({ grupo }: { readonly grupo: GrupoGantt }) {
  return (
    <div className="gantt__group" role="heading" aria-level={3}>
      {grupo.titulo}
      <span className="mono tnum text-faint" style={{ marginLeft: 8, textTransform: 'none' }}>
        {grupo.filas.length} act.
        {grupo.nCriticas > 0 && ` · ${grupo.nCriticas} en ruta crítica`}
      </span>
    </div>
  );
}

function Renglon({
  fila,
  escala,
  corte,
  seleccionada,
  onSeleccionar,
  sangria = 0,
}: {
  readonly fila: FilaGantt;
  readonly escala: Escala;
  readonly corte: number | null;
  readonly seleccionada: boolean;
  readonly onSeleccionar: (fila: FilaGantt) => void;
  /** Indentación en px del Gantt jerárquico; 0 en la vista plana. */
  readonly sangria?: number;
}) {
  const tono = tonoBarra(fila);
  const barra = tramoDeBarra(escala, fila.inicio, fila.fin);
  const holgura = tramoDeHolgura(escala, fila.fin, fila.holguraDias);

  return (
    <div
      className="gantt__row"
      style={seleccionada ? { background: 'var(--c-accent-soft)' } : undefined}
    >
      <button
        type="button"
        className="gantt__label"
        onClick={() => onSeleccionar(fila)}
        style={{
          textAlign: 'left',
          background: 'none',
          border: 0,
          font: 'inherit',
          color: 'inherit',
          cursor: 'pointer',
          paddingLeft: sangria === 0 ? undefined : 8 + sangria,
        }}
      >
        <span
          style={{
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {fila.descripcion}
        </span>
        <small className="tnum">
          {fmtFecha(fila.inicio)} → {fmtFecha(fila.fin)} · {fmtNum(fila.duracionDias)} d ·{' '}
          {etiquetaTono(tono)}
          {fila.holguraDias !== null && ` · holgura ${fmtNum(fila.holguraDias)} d`}
          {fila.desfaseDias !== null &&
            fila.desfaseDias > 0 &&
            ` · desfase ${fmtNum(fila.desfaseDias)} d`}
        </small>
      </button>

      <div className="gantt__track">
        {corte !== null && (
          <div
            aria-hidden
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: `${corte}%`,
              width: 1,
              background: 'var(--c-accent-strong)',
              opacity: 0.45,
            }}
          />
        )}

        {holgura && (
          <div
            aria-hidden
            title={`Holgura ${fmtNum(fila.holguraDias)} d`}
            style={{
              position: 'absolute',
              top: 16,
              height: 4,
              left: `${holgura.izquierda}%`,
              width: `${holgura.ancho}%`,
              background: 'var(--c-line-strong)',
              borderRadius: 2,
            }}
          />
        )}

        {barra ? (
          <div
            aria-hidden
            className={`gantt__bar ${claseBarra(tono)}`.trim()}
            style={{ left: `${barra.izquierda}%`, width: `${barra.ancho}%` }}
            onClick={() => onSeleccionar(fila)}
            title={`${fila.descripcion} · ${etiquetaTono(tono)} · avance ${fmtPct(fila.avancePct)}`}
          >
            <div
              className="gantt__bar-fill"
              style={{ width: `${Math.min(100, Math.max(0, fila.avancePct))}%` }}
            />
            <span style={{ position: 'relative' }}>{fmtNum(fila.duracionDias)} d</span>
          </div>
        ) : (
          <span
            className="text-faint text-xs mono"
            style={{ position: 'absolute', left: 8, top: 10 }}
          >
            sin fechas
          </span>
        )}
      </div>
    </div>
  );
}
