/**
 * El Creador de obra: la única entrada para crear una obra (cerebro D-626, WORKFLOWS.md §8.10).
 *
 * Pregunta de dónde parte la obra y la deja siempre igual: en diseño, con sus partidas generadas y
 * la forma de arranque guardada. El prototipo se puede cambiar después, mientras siga en diseño
 * (Presupuesto y Cuantificador).
 *   - **Un prototipo** existente (lo de siempre).
 *   - **Catálogo base / desde cero**: obra nueva que se forma midiendo.
 * La ingeniería (Excel) se carga después, en Presupuesto → Cargar ingeniería.
 */

import { useState } from 'react';

import type { ClusterRespuesta, ProyectoRespuesta, PrototipoRespuesta } from '@/api/generado/modelo';
import { NuevaObra } from '@/cuantificador/NuevaObra';
import { AltaObra } from './AltaObra';

interface Props {
  readonly proyectos: readonly ProyectoRespuesta[];
  readonly clusters: readonly ClusterRespuesta[];
  readonly prototipos: readonly PrototipoRespuesta[];
  readonly clusterInicial?: string;
  readonly onCerrar: () => void;
  readonly onCreada: (obraId?: string) => void;
}

export function CreadorDeObra({ proyectos, clusters, prototipos, clusterInicial, onCerrar, onCreada }: Props) {
  const [parte, setParte] = useState<'prototipo' | 'nueva'>('prototipo');
  const origen = (
    <div className="field">
      <label className="field__label" htmlFor="creador-parte">
        Parte de
      </label>
      <select
        id="creador-parte"
        className="select"
        value={parte}
        onChange={(e) => setParte(e.target.value as 'prototipo' | 'nueva')}
      >
        <option value="prototipo">Un prototipo existente</option>
        <option value="nueva">Obra nueva: catálogo base o desde cero</option>
      </select>
    </div>
  );

  return parte === 'prototipo' ? (
    <AltaObra
      proyectos={proyectos}
      clusters={clusters}
      prototipos={prototipos}
      clusterInicial={clusterInicial}
      onCerrar={onCerrar}
      onCreada={() => onCreada()}
      origen={origen}
    />
  ) : (
    <NuevaObra onCerrar={onCerrar} onCreada={(id) => onCreada(id)} origen={origen} />
  );
}
