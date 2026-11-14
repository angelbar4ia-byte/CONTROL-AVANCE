/**
 * Los conceptos con que se paga un elemento paramétrico según el contexto (plan de elementos de muro, fase C): el mismo
 * elemento paga un concepto en los niveles 1 y 2 y otro desde el nivel 3, y el acero de un castillo se paga por escalón de
 * altura. Cada fila dice qué parte paga (acero, colado, completo), su unidad, su contexto, su «hasta» y su estado: un
 * concepto nuevo queda «Pendiente de autorizar» (sin precio) hasta que Control de obra lo autorice. Solo lectura; con un
 * nivel elegido marca el concepto que paga cada parte y muestra los avisos (alto sin escalón, parte sin concepto).
 */

import { useState } from 'react';

import { useConceptosPorContextoApiV1ElementosParametricosElementoIdConceptosPorContextoGet } from '@/api/generado/elementos-parametricos/elementos-parametricos';

interface Props {
  readonly elementoId: string;
  readonly clave: string;
}

const NIVELES = [1, 2, 3, 4] as const;
const RANURA: Record<string, string> = { acero: 'Acero', colado: 'Colado y cimbra', completo: 'Completo' };

export function ConceptosPorContexto({ elementoId, clave }: Props) {
  const [nivel, setNivel] = useState<number | null>(null);
  const lista = useConceptosPorContextoApiV1ElementosParametricosElementoIdConceptosPorContextoGet(
    elementoId,
    nivel === null ? undefined : { nivel },
  );
  const filas = lista.data?.conceptos ?? [];
  const avisos = lista.data?.avisos ?? [];
  if (lista.isSuccess && filas.length === 0) return null;

  return (
    <div role="group" aria-label={`Conceptos por contexto de ${clave}`} data-conceptos-por-contexto={clave} style={{ display: 'grid', gap: 4 }}>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span className="text-xs text-mute">Conceptos por contexto</span>
        <select aria-label={`Nivel del muro para ${clave}`} value={nivel ?? ''} onChange={(e) => setNivel(e.target.value ? Number(e.target.value) : null)}>
          <option value="">Todos los contextos</option>
          {NIVELES.map((n) => (
            <option key={n} value={n}>
              Nivel {n}
            </option>
          ))}
        </select>
      </div>
      {filas.map((c) => (
        <div
          key={c.id}
          className="row"
          data-concepto-por-contexto={c.clave}
          data-estado={c.estado}
          data-elegido={c.elegido === null ? undefined : String(c.elegido)}
          style={{ gap: 6, flexWrap: 'wrap', opacity: c.elegido === false ? 0.55 : 1 }}
        >
          <span className="mono text-xs">{c.clave}</span>
          <span className="text-xs">{c.descripcion}</span>
          <span className="text-xs text-mute">
            {RANURA[c.ranura ?? ''] ?? '—'} · por {c.unidad} · {c.contexto}
            {c.alto_hasta_m !== null && ` · hasta ${c.alto_hasta_m.toFixed(2)} m`}
          </span>
          <span className={c.estado === 'propuesto' ? 'badge badge--warn' : 'badge badge--ok'} data-estado-del-concepto={c.clave}>
            {c.estado === 'propuesto' ? 'Nuevo, pendiente de autorizar' : 'Autorizado'}
          </span>
          {c.elegido === true && <span className="badge">Paga en este nivel</span>}
        </div>
      ))}
      {avisos.map((a) => (
        <div key={a} role="note" className="text-xs" data-aviso-de-concepto>
          {a}
        </div>
      ))}
    </div>
  );
}
