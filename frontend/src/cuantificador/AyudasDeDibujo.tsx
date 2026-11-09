/**
 * Las ayudas de dibujo, junto a la herramienta activa: el **ortogonal** (los tramos salen a 90° y
 * 180° y, si se quiere, a otros ángulos de trabajo) y la **referencia a objetos** (el cursor se
 * pega a extremos, medios, centros y cruces de lo que ya hay).
 *
 * Mayús invierte el ortogonal mientras se mantiene apretada: con él encendido, dibuja libre; con él
 * apagado, dibuja recto. F8 y F3 los encienden y apagan.
 */

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

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

interface PropsBoton extends Props {
  readonly abiertas: boolean;
  readonly onAbiertas: (abiertas: boolean) => void;
}

/**
 * El botón AYUDAS de la barra de estado con su ventana: al pulsarlo la ventana **sube** desde el botón (sobre el
 * plano, no tapa la barra) para elegir los campos; al mover el puntero fuera de ella se oculta, igual que con Esc o un
 * clic fuera. No se oculta mientras se teclea en uno de sus campos. Encender o apagar el ortogonal y la referencia se
 * hace con un clic en sus botones (también ORTO y REF de la barra).
 */
export function BotonDeAyudas({ abiertas, onAbiertas, ...ayudas }: PropsBoton) {
  const boton = useRef<HTMLButtonElement>(null);
  const ventana = useRef<HTMLDivElement>(null);
  const espera = useRef<number | null>(null);
  const [lugar, setLugar] = useState<{ left: number; bottom: number } | null>(null);
  const cancelar = () => {
    if (espera.current !== null) window.clearTimeout(espera.current);
    espera.current = null;
  };
  const alejarse = () => {
    if (!abiertas) return;
    cancelar();
    // Un respiro para cruzar el hueco entre el botón y la ventana sin que se cierre.
    espera.current = window.setTimeout(() => {
      const activo = document.activeElement;
      const tecleando = ventana.current?.contains(activo) && activo instanceof HTMLInputElement;
      if (!tecleando) onAbiertas(false);
    }, 350);
  };
  // La ventana flota fija sobre el botón (la barra de estado se desplaza y la recortaría).
  useEffect(() => {
    if (!abiertas) return;
    const poner = () => {
      const caja = boton.current?.getBoundingClientRect();
      if (!caja) return;
      setLugar({ left: Math.max(8, Math.min(caja.left, window.innerWidth - 340)), bottom: window.innerHeight - caja.top + 8 });
    };
    poner();
    window.addEventListener('resize', poner);
    const fuera = (e: PointerEvent) => {
      const el = e.target as Node;
      if (!ventana.current?.contains(el) && !boton.current?.contains(el)) onAbiertas(false);
    };
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onAbiertas(false);
    };
    document.addEventListener('pointerdown', fuera);
    document.addEventListener('keydown', tecla);
    return () => {
      window.removeEventListener('resize', poner);
      document.removeEventListener('pointerdown', fuera);
      document.removeEventListener('keydown', tecla);
      cancelar();
    };
  }, [abiertas, onAbiertas]);
  return (
    <>
      {abiertas &&
        lugar &&
        createPortal(
          <div
            ref={ventana}
            className="ayudas-flotante"
            style={{ left: lugar.left, bottom: lugar.bottom }}
            onPointerEnter={cancelar}
            onPointerLeave={alejarse}
          >
            <AyudasDeDibujo {...ayudas} />
          </div>,
          document.body,
        )}
      <button
        ref={boton}
        type="button"
        className={abiertas ? 'estado-pastilla is-activa' : 'estado-pastilla'}
        aria-pressed={abiertas}
        aria-label="Ayudas de dibujo"
        title="Ajustar el ortogonal (ángulo de trabajo) y la referencia a objetos"
        onPointerEnter={cancelar}
        onPointerLeave={alejarse}
        onClick={() => onAbiertas(!abiertas)}
      >
        AYUDAS
      </button>
    </>
  );
}
