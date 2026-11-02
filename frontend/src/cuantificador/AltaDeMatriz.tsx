/**
 * Poner una matriz bajo un concepto del catálogo (entrega 5b): una que ya existe o una que nace aquí.
 * Cambia la composición del **catálogo**, no solo de esta obra; por eso avisa antes de abrirse.
 *
 * Sin botón de guardar: se escribe la clave de la matriz y, si es una que ya existe, queda puesta al
 * elegirla de la lista o dar Intro; si no existe, piden descripción y unidad y se crea al elegir la unidad.
 * La cantidad es lo que lleva **por unidad del concepto padre**.
 */

import { Plus, X } from 'lucide-react';
import { useMemo, useState, type KeyboardEvent } from 'react';

import { cantidadPorPiezas, numeroDeTexto } from './cantidad';
import { useQueryClient } from '@tanstack/react-query';

import type { ErrorApi } from '@/api/cliente';
import {
  useListarConceptosApiV1ConceptosGet,
  useListarUnidadesApiV1UnidadesGet,
  usePonerMatrizAlConceptoApiV1ConceptosConceptoIdMatricesPost,
} from '@/api/generado/catalogos/catalogos';

interface Props {
  /** El concepto que recibe la matriz. */
  readonly padreId: string;
  readonly padreClave: string;
  /** Después de poner: se vuelven a leer las matrices del árbol. */
  readonly onPuesta: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function AltaDeMatriz({ padreId, padreClave, onPuesta, onError }: Props) {
  const [abierto, setAbierto] = useState(false);
  const [clave, setClave] = useState('');
  const [cantidad, setCantidad] = useState('1');
  // La cantidad se captura a mano o se forma: piezas ÷ largo de la pieza comercial × desperdicio.
  const [modo, setModo] = useState<'mano' | 'piezas'>('mano');
  const [piezas, setPiezas] = useState('4');
  const [largo, setLargo] = useState('12');
  const [desperdicio, setDesperdicio] = useState('0.5');
  const [descripcion, setDescripcion] = useState('');
  const [unidadId, setUnidadId] = useState('');
  const queryClient = useQueryClient();
  const conceptos = useListarConceptosApiV1ConceptosGet(undefined, { query: { enabled: abierto, staleTime: 60_000 } });
  const unidades = useListarUnidadesApiV1UnidadesGet(undefined, { query: { enabled: abierto, staleTime: 60_000 } });
  const poner = usePonerMatrizAlConceptoApiV1ConceptosConceptoIdMatricesPost<ErrorApi>();

  const existente = useMemo(
    () => (conceptos.data ?? []).find((c) => c.clave.toLowerCase() === clave.trim().toLowerCase()),
    [conceptos.data, clave],
  );
  const esNueva = clave.trim() !== '' && !existente && conceptos.data !== undefined;
  const porPiezas = cantidadPorPiezas({
    piezas: numeroDeTexto(piezas),
    largo: numeroDeTexto(largo),
    desperdicioPct: numeroDeTexto(desperdicio || '0'),
  });
  const cantidadValida = modo === 'piezas' ? porPiezas !== null : Number(cantidad) > 0;
  // Lo que se manda: la cantidad a mano, o la fórmula (el servidor la calcula y la guarda).
  const lleva = modo === 'piezas'
    ? { formula: { piezas: String(numeroDeTexto(piezas)), largo: String(numeroDeTexto(largo)), desperdicio_pct: String(numeroDeTexto(desperdicio || '0')) } }
    : { cantidad };

  const reiniciar = () => {
    setClave('');
    setCantidad('1');
    setDescripcion('');
    setUnidadId('');
  };

  async function ponerYa(unidad?: string) {
    if (!cantidadValida || poner.isPending || clave.trim() === '') return;
    if (existente === undefined && (unidad === undefined || unidad === '' || descripcion.trim() === '')) return;
    try {
      await poner.mutateAsync({
        conceptoId: padreId,
        data:
          existente !== undefined
            ? { ...lleva, matriz_id: existente.id }
            : {
                ...lleva,
                nueva: { clave: clave.trim(), descripcion: descripcion.trim(), unidad_id: unidad as string },
              },
      });
      void queryClient.invalidateQueries({
        predicate: (q) => /\/matrices|\/cpu/.test(JSON.stringify(q.queryKey)),
      });
      onPuesta(`Matriz ${clave.trim().toUpperCase()} puesta en ${padreClave} (catálogo).`);
      reiniciar();
      setAbierto(false);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo poner la matriz.');
      setUnidadId('');
    }
  }

  const alIntro = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      void ponerYa(unidadId);
    }
  };

  if (!abierto) {
    return (
      <button
        type="button"
        className="btn btn--ghost btn--sm"
        aria-label={`Agregar matriz a ${padreClave}`}
        title="Agregar una matriz a este concepto (cambia el catálogo)"
        onClick={() => setAbierto(true)}
      >
        <Plus size={12} aria-hidden /> Matriz
      </button>
    );
  }

  return (
    <form className="alta-concepto" aria-label={`Nueva matriz de ${padreClave}`} onSubmit={(e) => e.preventDefault()}>
      <div className="alta-concepto__titulo">
        <span>Matriz de {padreClave}</span>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          aria-label="Cerrar nueva matriz"
          onClick={() => {
            reiniciar();
            setAbierto(false);
          }}
        >
          <X size={13} aria-hidden />
        </button>
      </div>
      <label>
        Matriz (clave)
        <input
          list={`matrices-${padreId}`}
          value={clave}
          maxLength={60}
          onChange={(e) => setClave(e.target.value)}
          onKeyDown={alIntro}
        />
        <datalist id={`matrices-${padreId}`}>
          {(conceptos.data ?? []).slice(0, 1500).map((c) => (
            <option key={c.id} value={c.clave}>
              {c.descripcion}
            </option>
          ))}
        </datalist>
      </label>
      <div className="opciones__fila" role="group" aria-label="Cómo se forma la cantidad">
        <button type="button" className={modo === 'mano' ? 'chip is-active' : 'chip'} aria-pressed={modo === 'mano'} onClick={() => setModo('mano')}>
          A mano
        </button>
        <button type="button" className={modo === 'piezas' ? 'chip is-active' : 'chip'} aria-pressed={modo === 'piezas'} onClick={() => setModo('piezas')}>
          Por piezas comerciales
        </button>
      </div>
      {modo === 'mano' ? (
        <label>
          Cantidad por unidad
          <input inputMode="decimal" value={cantidad} onChange={(e) => setCantidad(e.target.value)} onKeyDown={alIntro} />
        </label>
      ) : (
        <>
          <label>
            Piezas por unidad del concepto
            <input inputMode="decimal" value={piezas} onChange={(e) => setPiezas(e.target.value)} onKeyDown={alIntro} />
          </label>
          <label>
            Lo que mide una pieza completa
            <input inputMode="decimal" value={largo} onChange={(e) => setLargo(e.target.value)} onKeyDown={alIntro} />
          </label>
          <label>
            Desperdicio (%)
            <input inputMode="decimal" value={desperdicio} onChange={(e) => setDesperdicio(e.target.value)} onKeyDown={alIntro} />
          </label>
          <p className="text-sm" data-testid="cantidad-formada" style={{ margin: 0 }}>
            {porPiezas === null
              ? 'Completa piezas, largo y desperdicio (0 a 100).'
              : `${piezas} ÷ ${largo} × ${(1 + numeroDeTexto(desperdicio || '0') / 100).toFixed(4).replace(/0+$/, '').replace(/\.$/, '')} = ${porPiezas.toFixed(6)} por unidad`}
          </p>
        </>
      )}
      {existente && (
        <p className="text-mute text-sm" style={{ margin: 0 }}>
          {existente.descripcion} — Intro la pone.
        </p>
      )}
      {esNueva && (
        <>
          <label>
            Descripción
            <input value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
          </label>
          <label>
            Unidad
            <select
              value={unidadId}
              disabled={poner.isPending}
              onChange={(e) => {
                setUnidadId(e.target.value);
                void ponerYa(e.target.value);
              }}
            >
              <option value="">Elige para crearla…</option>
              {(unidades.data ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.clave} · {u.nombre}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      <p className="text-mute text-sm" style={{ margin: 0 }}>
        Cambia el catálogo: vale para todas las obras que usen {padreClave}.
      </p>
    </form>
  );
}
