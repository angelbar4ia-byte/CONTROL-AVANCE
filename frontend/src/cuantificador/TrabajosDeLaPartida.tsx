/**
 * «TRABAJOS» bajo cada partida del árbol (mockup): los destajos de su receta, cada uno con su cuadrilla, su rendimiento
 * por día, sus días y su importe, y el botón «+ Trabajo». Un destajo nace en la receta del concepto, así que vale para
 * todas las obras que lo usen; su precio se define en Presupuesto (aquí solo su cantidad y su cuadrilla).
 */

import { useMemo, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useAgregarDestajoAlConceptoApiV1ConceptosConceptoIdDestajosPost } from '@/api/generado/catalogos/catalogos';
import type { TrabajoDeObraRespuesta } from '@/api/generado/modelo';
import { fmtMXN, fmtNum } from '@/lib/formato';

import { cantidadDelConcepto, calcularTrabajo } from './trabajos';
import { numeroTecleado } from './volumen';

interface Props {
  readonly actividadId: string;
  readonly conceptoId: string;
  readonly clave: string;
  /** Todos los trabajos de la obra: aquí se toman los de esta partida. */
  readonly trabajos: readonly TrabajoDeObraRespuesta[];
  /** Lo medido de la partida en el plano, si hay. */
  readonly medida: string | number | null | undefined;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
  readonly onRecargar: () => void;
}

export function TrabajosDeLaPartida({ actividadId, conceptoId, clave, trabajos, medida, onCambio, onError, onRecargar }: Props) {
  const crear = useAgregarDestajoAlConceptoApiV1ConceptosConceptoIdDestajosPost<ErrorApi>();
  const [abierto, setAbierto] = useState(false);
  const [nombre, setNombre] = useState('');
  const [factor, setFactor] = useState('1');
  const propios = useMemo(() => trabajos.filter((t) => t.actividad_id === actividadId), [trabajos, actividadId]);
  const f = numeroTecleado(factor);
  const valido = nombre.trim() !== '' && f > 0;

  async function agregar() {
    if (!valido) return;
    try {
      const r = await crear.mutateAsync({ conceptoId, data: { descripcion: nombre.trim(), precio: '0', factor: String(f) } });
      onRecargar();
      onCambio(`Trabajo ${r.clave} en ${clave}: su precio se define en Presupuesto; aquí solo su cantidad y su cuadrilla.`);
      setNombre('');
      setFactor('1');
      setAbierto(false);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo agregar el trabajo.');
    }
  }

  return (
    <div className="arbol-trabajos" role="group" aria-label={`Trabajos de ${clave}`}>
      <div className="arbol-trabajos__cabeza">
        <span className="arbol-trabajos__titulo">Trabajos</span>
        <button type="button" className="btn btn--ghost btn--sm" aria-expanded={abierto} aria-label={`Agregar trabajo a ${clave}`} onClick={() => setAbierto(!abierto)}>
          + Trabajo
        </button>
      </div>
      {abierto && (
        <div className="arbol-edicion__alta" role="group" aria-label={`Trabajo nuevo en ${clave}`}>
          <input
            aria-label={`Nombre del trabajo de ${clave}`}
            placeholder="Nombre del trabajo · Intro agrega"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void agregar();
            }}
          />
          <input aria-label={`Unidades del trabajo por unidad de ${clave}`} title="Unidades del trabajo por cada unidad del concepto" inputMode="decimal" style={{ width: 48 }} value={factor} onChange={(e) => setFactor(e.target.value)} />
          <button type="button" className="btn btn--sm" disabled={!valido || crear.isPending} onClick={() => void agregar()}>
            Agregar
          </button>
        </div>
      )}
      {propios.length === 0 ? (
        <div className="text-mute text-xs">Sin trabajos en la receta.</div>
      ) : (
        <ul className="arbol-trabajos__lista">
          {propios.map((t) => {
            const c = calcularTrabajo(t, cantidadDelConcepto(medida, t.cantidad_presupuestada));
            const partes = [
              t.cuadrilla_id ? (t.cuadrilla_nombre ?? t.cuadrilla_clave ?? 'Cuadrilla') : 'sin cuadrilla',
              c.capacidadPorDia !== null ? `${fmtNum(c.capacidadPorDia)} ${t.unidad ?? ''}/día` : null,
              c.dias !== null ? `${fmtNum(c.dias)} d` : null,
              fmtMXN(c.importe),
            ].filter(Boolean);
            return (
              <li key={`${t.actividad_id}:${t.insumo_id}`} data-trabajo={t.clave}>
                <span>
                  <span className="mono">{t.clave}</span> {t.descripcion}
                </span>
                <small className="text-mute">{partes.join(' · ')}</small>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
