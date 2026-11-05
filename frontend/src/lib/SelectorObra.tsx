/**
 * Selector de obra sobre `GET /obras` (§11.2 "Proyecto · Obra").
 *
 * El endpoint lista **por alcance**: RLS ya devuelve solo las obras del
 * Residente, del cluster del Supervisor, del proyecto de Control de obra o
 * todas para el Super intendente (§4, §12.4). Por eso aquí no hay ningún
 * filtro por rol: lo que llega es, por definición, lo que este usuario puede
 * ver.
 *
 * Vive en `lib/` y no en un feature porque tres pantallas de la fase 4
 * —Consumo, Salidas y Alta de incidencia— piden lo mismo: elegir la obra
 * sobre la que trabajan. Consume el hook generado, no otro módulo (AGENTS.md
 * "el front programa contra el contrato").
 */

import type { ObraRespuesta } from '@/api/generado/modelo';
import { useListarObrasApiV1ObrasGet } from '@/api/generado/obras/obras';

interface Props {
  readonly id: string;
  readonly etiqueta: string;
  readonly valor: string;
  readonly onCambio: (obraId: string) => void;
  /** Texto de la opción vacía. */
  readonly vacio?: string;
  readonly requerido?: boolean;
  /** El texto de cada obra; sin él, su clave. Sirve para mostrar «CLAVE · Proyecto · Cluster». */
  readonly textoDe?: (obra: ObraRespuesta) => string;
}

export function SelectorObra({
  id,
  etiqueta,
  valor,
  onCambio,
  vacio = 'Elige una obra…',
  requerido = false,
  textoDe,
}: Props) {
  const consulta = useListarObrasApiV1ObrasGet();
  const obras = consulta.data ?? [];

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {etiqueta}
      </label>
      <select
        id={id}
        className="select"
        value={valor}
        required={requerido}
        disabled={consulta.isLoading}
        onChange={(e) => onCambio(e.target.value)}
      >
        <option value="">{consulta.isLoading ? 'Cargando obras…' : vacio}</option>
        {obras.map((obra) => (
          <option key={obra.id} value={obra.id}>
            {textoDe ? textoDe(obra) : obra.clave}
          </option>
        ))}
      </select>
      {!consulta.isLoading && obras.length === 0 && (
        <div className="field__hint">
          No hay obras en tu alcance (§4). RLS filtra la lista por rol.
        </div>
      )}
    </div>
  );
}
