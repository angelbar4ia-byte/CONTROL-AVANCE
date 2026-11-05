/**
 * Las opciones de la herramienta activa, junto a la barra: el grosor y la alineación de una
 * línea (un muro de 0.15 o de 0.30 m, con el cuerpo al centro, a la izquierda o a la derecha del
 * eje), y la forma de un punto (círculo, cuadrado, rectángulo, triángulo, hexágono o una forma
 * dibujada), con su tamaño. Un punto con forma se estampa con un clic: queda un polígono del
 * tamaño pedido, centrado donde se hizo clic.
 *
 * Los tamaños son **metros**. En un plano sin calibrar se asume 1 unidad = 1 m, igual que el resto
 * de las cantidades (el visor ya lo avisa).
 */

import { useState } from 'react';

import {
  ELEMENTOS,
  NOMBRE_DE_FORMA,
  normalizarContorno,
  type Alineacion,
  type Forma,
  type TipoDeForma,
} from './formas';
import type { Punto } from './geometria';
import { PanelDeOpciones } from './PanelDeOpciones';
import { numeroTecleado } from './volumen';

const GROSORES_USUALES = [0.1, 0.15, 0.2, 0.3] as const;
/** Pendientes de uso común en techumbres, drenajes y rampas (en %). */
const PENDIENTES_USUALES = [2, 5, 10, 33] as const;
const TIPOS: readonly TipoDeForma[] = ['circulo', 'cuadrado', 'rectangulo', 'triangulo', 'hexagono', 'libre'];

const ALINEACIONES: readonly { clave: Alineacion; etiqueta: string }[] = [
  { clave: 'izquierda', etiqueta: 'Izquierda' },
  { clave: 'centro', etiqueta: 'Centro' },
  { clave: 'derecha', etiqueta: 'Derecha' },
];

const LADO_DE_HOJA = 150;

/** La hoja donde se dibuja una forma propia: clic para cada vértice, y se normaliza al cerrar. */
function HojaDeForma({ onForma }: { readonly onForma: (vertices: readonly Punto[]) => void }) {
  const [puntos, setPuntos] = useState<readonly Punto[]>([]);
  const cerrable = puntos.length >= 3;
  return (
    <div className="opciones__hoja">
      <svg
        viewBox={`0 0 ${LADO_DE_HOJA} ${LADO_DE_HOJA}`}
        role="img"
        aria-label="Hoja para dibujar la forma"
        onClick={(e) => {
          const caja = e.currentTarget.getBoundingClientRect();
          const x = ((e.clientX - caja.left) / caja.width) * LADO_DE_HOJA;
          const y = ((e.clientY - caja.top) / caja.height) * LADO_DE_HOJA;
          setPuntos((p) => [...p, [x, y]]);
        }}
      >
        {puntos.length > 1 && (
          <polyline points={puntos.map((p) => `${p[0]},${p[1]}`).join(' ')} className="opciones__trazo" />
        )}
        {puntos.map((p, i) => (
          <circle key={i} cx={p[0]} cy={p[1]} r={3} />
        ))}
      </svg>
      <div className="row" style={{ gap: 4 }}>
        <button
          type="button"
          className="btn btn--sm btn--accent"
          disabled={!cerrable}
          onClick={() => {
            const n = normalizarContorno(puntos);
            if (n) onForma(n);
            setPuntos([]);
          }}
        >
          Usar esta forma
        </button>
        <button type="button" className="btn btn--sm btn--ghost" onClick={() => setPuntos([])}>
          Borrar
        </button>
      </div>
    </div>
  );
}

interface Props {
  readonly herramienta: 'linea' | 'punto';
  readonly grosorM: number | null;
  readonly onGrosor: (m: number | null) => void;
  /** Pendiente en % de un tramo inclinado, o `null` si es horizontal. */
  readonly pendientePct: number | null;
  readonly onPendiente: (p: number | null) => void;
  readonly alineacion: Alineacion;
  readonly onAlineacion: (a: Alineacion) => void;
  /** `null` = punto simple, sin forma. */
  readonly forma: Forma | null;
  readonly onForma: (f: Forma | null) => void;
  /** El contorno normalizado del trazo elegido, para «usar la forma del trazo elegido». */
  readonly contornoElegido: readonly Punto[] | null;
}

export function OpcionesDeHerramienta({
  herramienta,
  grosorM,
  onGrosor,
  pendientePct,
  onPendiente,
  alineacion,
  onAlineacion,
  forma,
  onForma,
  contornoElegido,
}: Props) {
  const [grosorTecleado, setGrosorTecleado] = useState('');
  const [pendienteTecleada, setPendienteTecleada] = useState('');

  if (herramienta === 'linea') {
    return (
      <PanelDeOpciones etiqueta="Opciones de la línea" titulo="Línea">
        <div className="opciones__titulo">Grosor</div>
        <div className="opciones__fila">
          <button
            type="button"
            className={grosorM === null ? 'chip is-active' : 'chip'}
            aria-pressed={grosorM === null}
            onClick={() => onGrosor(null)}
          >
            Sin grosor
          </button>
          {GROSORES_USUALES.map((g) => (
            <button
              key={g}
              type="button"
              className={grosorM === g ? 'chip is-active' : 'chip'}
              aria-pressed={grosorM === g}
              onClick={() => onGrosor(g)}
            >
              {g.toFixed(2)} m
            </button>
          ))}
        </div>
        <label className="opciones__campo" htmlFor="opc-grosor">
          <span>Otro grosor (m)</span>
          <input
            id="opc-grosor"
            className="input"
            inputMode="decimal"
            placeholder="0.25"
            value={grosorTecleado}
            onChange={(e) => {
              setGrosorTecleado(e.target.value);
              const n = numeroTecleado(e.target.value);
              if (n > 0) onGrosor(n);
            }}
          />
        </label>
        <div className="opciones__titulo">Alineación del cuerpo</div>
        <div className="opciones__fila" role="group" aria-label="Alineación">
          {ALINEACIONES.map((a) => (
            <button
              key={a.clave}
              type="button"
              className={alineacion === a.clave ? 'chip is-active' : 'chip'}
              aria-pressed={alineacion === a.clave}
              disabled={grosorM === null}
              title="Mirando en el sentido en que dibujas la línea"
              onClick={() => onAlineacion(a.clave)}
            >
              {a.etiqueta}
            </button>
          ))}
        </div>
        <div className="opciones__titulo">Pendiente</div>
        <div className="opciones__fila" role="group" aria-label="Pendiente">
          <button
            type="button"
            className={pendientePct === null ? 'chip is-active' : 'chip'}
            aria-pressed={pendientePct === null}
            onClick={() => {
              onPendiente(null);
              setPendienteTecleada('');
            }}
          >
            Horizontal
          </button>
          {PENDIENTES_USUALES.map((p) => (
            <button
              key={p}
              type="button"
              className={pendientePct === p ? 'chip is-active' : 'chip'}
              aria-pressed={pendientePct === p}
              onClick={() => onPendiente(p)}
            >
              {p} %
            </button>
          ))}
        </div>
        <label className="opciones__campo" htmlFor="opc-pendiente">
          <span>Otra pendiente (%)</span>
          <input
            id="opc-pendiente"
            className="input"
            inputMode="decimal"
            placeholder="12"
            value={pendienteTecleada}
            onChange={(e) => {
              setPendienteTecleada(e.target.value);
              const n = numeroTecleado(e.target.value);
              onPendiente(n > 0 ? n : null);
            }}
          />
        </label>
        <p className="text-mute text-xs">
          {pendientePct === null
            ? 'La línea es horizontal: mide lo que se ve en planta.'
            : 'Un tramo inclinado mide más que su proyección en planta: largo × √(1 + pendiente²).'}
        </p>
        <p className="text-mute text-xs">
          {grosorM === null
            ? 'La línea mide su largo. Sobre un concepto en m² lo vuelve área: largo × altura × caras (se afina en el detalle).'
            : 'El eje es la línea que dibujas; el cuerpo del muro queda del lado que elijas.'}
        </p>
      </PanelDeOpciones>
    );
  }

  const cambiar = (cambios: Partial<Forma>) => forma && onForma({ ...forma, ...cambios });
  return (
    <PanelDeOpciones etiqueta="Opciones del punto" titulo="Punto">
      <div className="opciones__titulo">Forma</div>
      <div className="opciones__fila">
        <button
          type="button"
          className={forma === null ? 'chip is-active' : 'chip'}
          aria-pressed={forma === null}
          onClick={() => onForma(null)}
        >
          Punto
        </button>
        {TIPOS.map((t) => (
          <button
            key={t}
            type="button"
            className={forma?.tipo === t ? 'chip is-active' : 'chip'}
            aria-pressed={forma?.tipo === t}
            onClick={() =>
              onForma({
                tipo: t,
                anchoM: forma?.anchoM ?? 0.3,
                altoM: forma?.altoM ?? 0.3,
                rotacionGrados: forma?.rotacionGrados ?? 0,
                nombre: undefined,
                vertices: t === 'libre' ? forma?.vertices : undefined,
              })
            }
          >
            {NOMBRE_DE_FORMA[t]}
          </button>
        ))}
      </div>

      <div className="opciones__titulo">Elementos</div>
      <div className="opciones__fila">
        {ELEMENTOS.map((e) => (
          <button
            key={e.nombre}
            type="button"
            className={forma?.nombre === e.nombre ? 'chip is-active' : 'chip'}
            aria-pressed={forma?.nombre === e.nombre}
            title={`${e.anchoM} × ${e.altoM} m`}
            onClick={() => onForma(e)}
          >
            {e.nombre}
          </button>
        ))}
        <button
          type="button"
          className="chip"
          disabled={contornoElegido === null}
          title={
            contornoElegido === null
              ? 'Elige antes un trazo cerrado con la herramienta Seleccionar'
              : 'Estampa la forma del trazo elegido, a otro tamaño si quieres'
          }
          onClick={() =>
            contornoElegido &&
            onForma({
              tipo: 'libre',
              anchoM: forma?.anchoM ?? 0.3,
              altoM: forma?.altoM ?? 0.3,
              rotacionGrados: 0,
              nombre: 'Forma del trazo',
              vertices: contornoElegido,
            })
          }
        >
          Forma del trazo elegido
        </button>
      </div>

      {forma?.tipo === 'libre' && (
        <HojaDeForma onForma={(vertices) => cambiar({ vertices, nombre: 'Forma propia' })} />
      )}

      {forma !== null && (
        <div className="opciones__medidas">
          <label className="opciones__campo" htmlFor="opc-ancho">
            <span>Ancho (m)</span>
            <input
              id="opc-ancho"
              className="input"
              inputMode="decimal"
              value={String(forma.anchoM)}
              onChange={(e) => {
                const n = numeroTecleado(e.target.value);
                if (n > 0) cambiar({ anchoM: n, ...(forma.tipo === 'cuadrado' || forma.tipo === 'circulo' ? { altoM: n } : {}) });
              }}
            />
          </label>
          <label className="opciones__campo" htmlFor="opc-alto">
            <span>Alto (m)</span>
            <input
              id="opc-alto"
              className="input"
              inputMode="decimal"
              value={String(forma.altoM)}
              onChange={(e) => {
                const n = numeroTecleado(e.target.value);
                if (n > 0) cambiar({ altoM: n, ...(forma.tipo === 'cuadrado' || forma.tipo === 'circulo' ? { anchoM: n } : {}) });
              }}
            />
          </label>
          <label className="opciones__campo" htmlFor="opc-rot">
            <span>Giro (°)</span>
            <input
              id="opc-rot"
              className="input"
              inputMode="decimal"
              value={String(forma.rotacionGrados)}
              onChange={(e) => {
                const n = Number(e.target.value.replace(',', '.'));
                if (Number.isFinite(n)) cambiar({ rotacionGrados: Math.max(-360, Math.min(360, n)) });
              }}
            />
          </label>
        </div>
      )}
      <p className="text-mute text-xs">
        {forma === null
          ? 'Un punto cuenta una instancia.'
          : 'Haz clic en el plano para estampar la forma, centrada donde hagas clic.'}
      </p>
    </PanelDeOpciones>
  );
}
