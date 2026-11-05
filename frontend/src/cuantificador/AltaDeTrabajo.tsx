/**
 * «+ Destajo» y «+ Cuadrilla» de la pestaña Trabajos (cerebro D-631).
 *
 * Un **destajo** nace en la receta de un concepto de la obra, con cuántas unidades lleva por cada unidad del concepto;
 * es del catálogo, así que vale para todas las obras que usen el concepto. Una **cuadrilla** es capacidad: se da de alta
 * con su nombre. **Los costos no se definen aquí**: el precio del destajo y el costo de la cuadrilla son de Presupuesto;
 * el Cuantificador solo maneja cantidades.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getListarCuadrillasApiV1CuadrillasGetQueryKey,
  useAgregarDestajoAlConceptoApiV1ConceptosConceptoIdDestajosPost,
  useCrearCuadrillaApiV1CuadrillasPost,
} from '@/api/generado/catalogos/catalogos';
import { queryClient } from '@/app/queryClient';
import { numeroTecleado } from './volumen';

export interface ConceptoDeLaObra {
  readonly conceptoId: string;
  readonly actividadId: string;
  readonly clave: string;
  readonly descripcion: string;
}

interface Props {
  readonly conceptos: readonly ConceptoDeLaObra[];
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
  /** Se creó un destajo (su actividad e insumo) o una cuadrilla: que se elija. */
  readonly onDestajo: (actividadId: string, insumoId: string) => void;
  readonly onCuadrilla: (id: string) => void;
  /** Refrescar los trabajos de la obra. */
  readonly onRecargar: () => void;
}

export function AltaDeTrabajo({ conceptos, onCambio, onError, onDestajo, onCuadrilla, onRecargar }: Props) {
  const crearDestajo = useAgregarDestajoAlConceptoApiV1ConceptosConceptoIdDestajosPost<ErrorApi>();
  const crearCuadrilla = useCrearCuadrillaApiV1CuadrillasPost<ErrorApi>();
  const [abierto, setAbierto] = useState<'destajo' | 'cuadrilla' | null>(null);
  const [concepto, setConcepto] = useState('');
  const [nombre, setNombre] = useState('');
  const [factor, setFactor] = useState('1');

  const elegido = conceptos.find((c) => c.conceptoId === concepto);
  const f = numeroTecleado(factor);
  const destajoValido = elegido !== undefined && nombre.trim() !== '' && f > 0;

  async function nuevoDestajo() {
    if (!destajoValido || !elegido) return;
    try {
      const r = await crearDestajo.mutateAsync({
        conceptoId: elegido.conceptoId,
        data: { descripcion: nombre.trim(), precio: '0', factor: String(f) },
      });
      onRecargar();
      onDestajo(elegido.actividadId, r.insumo_id);
      onCambio(`Destajo ${r.clave} en ${elegido.clave}: su precio se define en Presupuesto; aquí solo su cantidad y su cuadrilla.`);
      setNombre('');
      setFactor('1');
      setAbierto(null);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo agregar el destajo.');
    }
  }

  async function nuevaCuadrilla() {
    if (nombre.trim() === '') return;
    try {
      const r = await crearCuadrilla.mutateAsync({
        data: { clave: `CUA-${Date.now().toString(36).toUpperCase()}`, nombre: nombre.trim() },
      });
      void queryClient.invalidateQueries({ queryKey: getListarCuadrillasApiV1CuadrillasGetQueryKey() });
      onRecargar();
      onCuadrilla(r.id);
      onCambio(`Cuadrilla ${r.nombre} creada: su costo se define en Presupuesto.`);
      setNombre('');
      setAbierto(null);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo dar de alta la cuadrilla.');
    }
  }

  return (
    <div role="group" aria-label="Agregar trabajo" style={{ display: 'grid', gap: 4, margin: '0 8px 8px' }}>
      <div className="row" style={{ gap: 6 }}>
        <button type="button" className="btn btn--sm" aria-pressed={abierto === 'destajo'} onClick={() => { setAbierto(abierto === 'destajo' ? null : 'destajo'); setNombre(''); }}>
          + Destajo
        </button>
        <button type="button" className="btn btn--sm" aria-pressed={abierto === 'cuadrilla'} onClick={() => { setAbierto(abierto === 'cuadrilla' ? null : 'cuadrilla'); setNombre(''); }}>
          + Cuadrilla
        </button>
      </div>
      {abierto === 'destajo' && (
        <div className="arbol-edicion__alta" role="group" aria-label="Destajo nuevo">
          <select aria-label="Concepto del destajo" value={concepto} onChange={(e) => setConcepto(e.target.value)}>
            <option value="">Del concepto…</option>
            {conceptos.map((c) => (
              <option key={c.conceptoId} value={c.conceptoId}>
                {c.clave} · {c.descripcion}
              </option>
            ))}
          </select>
          <input aria-label="Nombre del destajo" placeholder="Nombre del destajo" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          <input aria-label="Unidades del destajo por unidad del concepto" title="Unidades del destajo por cada unidad del concepto" inputMode="decimal" style={{ width: 48 }} value={factor} onChange={(e) => setFactor(e.target.value)} />
          <button type="button" className="btn btn--sm" disabled={!destajoValido || crearDestajo.isPending} onClick={() => void nuevoDestajo()}>
            Agregar
          </button>
        </div>
      )}
      {abierto === 'cuadrilla' && (
        <div className="arbol-edicion__alta" role="group" aria-label="Cuadrilla nueva">
          <input
            aria-label="Nombre de la cuadrilla"
            placeholder="Nombre · Intro crea"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void nuevaCuadrilla();
            }}
          />
          <button type="button" className="btn btn--sm" disabled={nombre.trim() === '' || crearCuadrilla.isPending} onClick={() => void nuevaCuadrilla()}>
            Crear
          </button>
        </div>
      )}
    </div>
  );
}
