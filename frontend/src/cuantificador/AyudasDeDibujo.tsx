/**
 * Las ayudas de dibujo, junto a la herramienta activa: el **ortogonal** (los tramos salen a 90° y
 * 180° y, si se quiere, a otros ángulos de trabajo) y la **referencia a objetos** (el cursor se
 * pega a extremos, medios, centros y cruces de lo que ya hay).
 *
 * Mayús invierte el ortogonal mientras se mantiene apretada: con él encendido, dibuja libre; con él
 * apagado, dibuja recto. F8 y F3 los encienden y apagan.
 */

import { useState } from 'react';

import {
  NOMBRE_DE_REFERENCIA,
  type ReferenciasActivas,
  type TipoDeReferencia,
} from './referencias';

const PASOS = [90, 45, 30, 15] as const;
const TIPOS: readonly TipoDeReferencia[] = ['extremo', 'medio', 'centro', 'interseccion', 'perpendicular', 'cercano'];

interface Props {
  readonly ortogonal: boolean;
  readonly onOrtogonal: (on: boolean) => void;
  readonly pasoGrados: number;
  readonly onPaso: (grados: number) => void;
  readonly baseGrados: number;
  readonly onBase: (grados: number) => void;
  readonly referenciasOn: boolean;
  readonly onReferenciasOn: (on: boolean) => void;
  readonly referencias: ReferenciasActivas;
  readonly onReferencia: (tipo: TipoDeReferencia, on: boolean) => void;
}

const aNumero = (t: string) => Number(t.replace(',', '.'));

export function AyudasDeDibujo({
  ortogonal,
  onOrtogonal,
  pasoGrados,
  onPaso,
  baseGrados,
  onBase,
  referenciasOn,
  onReferenciasOn,
  referencias,
  onReferencia,
}: Props) {
  const [otroPaso, setOtroPaso] = useState('');
  return (
    <section className="opciones" aria-label="Ayudas de dibujo">
      <div className="opciones__titulo">Ortogonal</div>
      <div className="opciones__fila">
        <button
          type="button"
          className={ortogonal ? 'chip is-active' : 'chip'}
          aria-pressed={ortogonal}
          title="Tramos rectos al ángulo de trabajo (F8). Mantén Mayús para invertirlo un momento."
          onClick={() => onOrtogonal(!ortogonal)}
        >
          {ortogonal ? 'Ortogonal activo' : 'Ortogonal apagado'}
        </button>
      </div>
      <div className="opciones__titulo">Ángulo de trabajo</div>
      <div className="opciones__fila" role="group" aria-label="Ángulo de trabajo">
        {PASOS.map((g) => (
          <button
            key={g}
            type="button"
            className={pasoGrados === g ? 'chip is-active' : 'chip'}
            aria-pressed={pasoGrados === g}
            title={g === 90 ? 'Horizontal y vertical (0°, 90°, 180°, 270°)' : `Cada ${g}°`}
            onClick={() => onPaso(g)}
          >
            {g}°
          </button>
        ))}
      </div>
      <label className="opciones__campo" htmlFor="ay-paso">
        <span>Otro ángulo (°)</span>
        <input
          id="ay-paso"
          className="input"
          inputMode="decimal"
          placeholder="22.5"
          value={otroPaso}
          onChange={(e) => {
            setOtroPaso(e.target.value);
            const n = aNumero(e.target.value);
            if (n > 0 && n <= 180) onPaso(n);
          }}
        />
      </label>
      <label className="opciones__campo" htmlFor="ay-base">
        <span>Girar desde (°)</span>
        <input
          id="ay-base"
          className="input"
          inputMode="decimal"
          value={String(baseGrados)}
          onChange={(e) => {
            const n = aNumero(e.target.value);
            if (Number.isFinite(n)) onBase(Math.max(-180, Math.min(180, n)));
          }}
        />
      </label>

      <div className="opciones__titulo">Referencia a objetos</div>
      <div className="opciones__fila">
        <button
          type="button"
          className={referenciasOn ? 'chip is-active' : 'chip'}
          aria-pressed={referenciasOn}
          title="El cursor se pega a los puntos notables de lo que ya hay (F3)"
          onClick={() => onReferenciasOn(!referenciasOn)}
        >
          {referenciasOn ? 'Referencia activa' : 'Referencia apagada'}
        </button>
      </div>
      <div className="opciones__fila" role="group" aria-label="Referencias">
        {TIPOS.map((t) => (
          <button
            key={t}
            type="button"
            className={referencias[t] ? 'chip is-active' : 'chip'}
            aria-pressed={referencias[t]}
            disabled={!referenciasOn}
            onClick={() => onReferencia(t, !referencias[t])}
          >
            {NOMBRE_DE_REFERENCIA[t]}
          </button>
        ))}
      </div>
    </section>
  );
}
