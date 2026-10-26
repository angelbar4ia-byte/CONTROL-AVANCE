/**
 * La herramienta puntual del cuantificador: una ventana flotante sobre la
 * actividad (cerebro WORKFLOWS.md, «Cómo se abre la herramienta», D-532).
 *
 * Es el **mismo motor** que el módulo (`EspacioDeTrazo`), con otra entrada:
 *
 *  - conserva el contexto: la actividad y su cantidad siguen a la vista y se
 *    actualizan al guardar cada trazo — lo habitual es medir un concepto y volver;
 *  - se mueve y se minimiza para ver la pantalla de abajo; en un teléfono es una
 *    hoja a pantalla completa (CSS);
 *  - «Abrir en el módulo» lleva el mismo plano y la misma actividad cuando la
 *    tarea se vuelve un nivel entero, sin perder lo trazado;
 *  - **una sola ventana a la vez**: abrir otra sustituye a la actual.
 *
 * Vive en el shell (`AppShell`) para sobrevivir a la navegación entre pantallas
 * y estar disponible desde cualquiera que ofrezca un botón «Medir».
 *
 * Se minimiza ocultando, no desmontando: un trazo a medias y el plano elegido
 * no se pierden por asomarse al presupuesto de abajo.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as EventoPuntero,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';

import { EspacioDeTrazo } from './Cuantificador';
import { rutaDelModulo } from './ruta';

export interface DestinoDeVentana {
  readonly obraId: string;
  readonly actividadId?: string;
}

interface Contexto {
  readonly abrir: (destino: DestinoDeVentana) => void;
}

const ContextoVentana = createContext<Contexto | null>(null);

/** Abre la ventana del cuantificador sobre una actividad. */
export function useAbrirCuantificador(): (destino: DestinoDeVentana) => void {
  const contexto = useContext(ContextoVentana);
  if (!contexto) {
    throw new Error('useAbrirCuantificador necesita <ProveedorDeVentanaCuantificador>.');
  }
  return contexto.abrir;
}

export function ProveedorDeVentanaCuantificador({ children }: { readonly children: ReactNode }) {
  const [destino, setDestino] = useState<DestinoDeVentana | null>(null);
  const abrir = useCallback((nuevo: DestinoDeVentana) => setDestino(nuevo), []);
  const valor = useMemo(() => ({ abrir }), [abrir]);

  return (
    <ContextoVentana.Provider value={valor}>
      {children}
      {destino && (
        // `key`: otra actividad es otra sesión de trazo, no la misma con datos nuevos.
        <Ventana
          key={`${destino.obraId}|${destino.actividadId ?? ''}`}
          destino={destino}
          onCerrar={() => setDestino(null)}
        />
      )}
    </ContextoVentana.Provider>
  );
}

const ANCHO_VENTANA = 580;
const MARGEN = 16;

interface Posicion {
  readonly x: number;
  readonly y: number;
}

function posicionInicial(): Posicion {
  const ancho = Math.min(ANCHO_VENTANA, window.innerWidth - 2 * MARGEN);
  return { x: Math.max(MARGEN, window.innerWidth - ancho - MARGEN), y: 72 };
}

function Ventana({
  destino,
  onCerrar,
}: {
  readonly destino: DestinoDeVentana;
  readonly onCerrar: () => void;
}) {
  const navegar = useNavigate();
  const [posicion, setPosicion] = useState<Posicion>(posicionInicial);
  const [minimizada, setMinimizada] = useState(false);
  const [planoActual, setPlanoActual] = useState<string | undefined>(undefined);
  const arrastre = useRef<{ dx: number; dy: number } | null>(null);
  const ventana = useRef<HTMLDivElement>(null);

  // Esc cierra solo si el foco está en la ventana: es la tecla que también
  // descarta un trazo a medias y los cajones, y no debe cerrar todo de golpe.
  useEffect(() => {
    function alTeclear(e: KeyboardEvent) {
      if (e.key === 'Escape' && e.target === ventana.current) onCerrar();
    }
    window.addEventListener('keydown', alTeclear);
    return () => window.removeEventListener('keydown', alTeclear);
  }, [onCerrar]);

  function alPresionar(e: EventoPuntero<HTMLDivElement>) {
    // Los botones del encabezado no inician arrastre.
    if ((e.target as HTMLElement).closest('button')) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    arrastre.current = { dx: e.clientX - posicion.x, dy: e.clientY - posicion.y };
  }

  function alMover(e: EventoPuntero<HTMLDivElement>) {
    const a = arrastre.current;
    if (!a) return;
    const ancho = ventana.current?.offsetWidth ?? ANCHO_VENTANA;
    // Dentro de la pantalla: una ventana arrastrada fuera de ella ya no se puede recuperar.
    setPosicion({
      x: Math.min(Math.max(0, e.clientX - a.dx), Math.max(0, window.innerWidth - ancho)),
      y: Math.min(Math.max(0, e.clientY - a.dy), Math.max(0, window.innerHeight - 40)),
    });
  }

  return (
    <div
      ref={ventana}
      className={minimizada ? 'ventana-cuant is-minimizada' : 'ventana-cuant'}
      role="dialog"
      aria-modal="false"
      aria-label="Cuantificador"
      tabIndex={-1}
      style={{ left: posicion.x, top: posicion.y, width: ANCHO_VENTANA }}
    >
      <div
        className="ventana-cuant__encabezado"
        onPointerDown={alPresionar}
        onPointerMove={alMover}
        onPointerUp={() => (arrastre.current = null)}
      >
        <span className="ventana-cuant__titulo">Cuantificador</span>
        <div className="row">
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => {
              void navegar(
                rutaDelModulo({
                  obraId: destino.obraId,
                  planoId: planoActual,
                  actividadId: destino.actividadId,
                }),
              );
              onCerrar();
            }}
          >
            Abrir en el módulo
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--icon btn--sm"
            aria-label={minimizada ? 'Restaurar ventana' : 'Minimizar ventana'}
            aria-expanded={!minimizada}
            onClick={() => setMinimizada((m) => !m)}
          >
            {minimizada ? '▢' : '–'}
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--icon btn--sm"
            aria-label="Cerrar ventana"
            onClick={onCerrar}
          >
            ✕
          </button>
        </div>
      </div>
      <div className="ventana-cuant__cuerpo" hidden={minimizada}>
        <EspacioDeTrazo
          obraId={destino.obraId}
          actividadFocoId={destino.actividadId}
          compacto
          onPlanoCambiado={setPlanoActual}
        />
      </div>
    </div>
  );
}
