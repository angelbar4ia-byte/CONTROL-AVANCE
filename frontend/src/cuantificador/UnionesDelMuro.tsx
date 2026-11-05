/**
 * Qué pasa en cada extremo de un muro cuando llega a otro (cerebro D-629): **conexión** (el muro continúa, esquina
 * cerrada, no cambia el largo), **unión a tope** (llega a la cara del otro y se detiene: pierde medio grosor del otro),
 * **empalme** (el tramo que se solapa se cuenta una sola vez) y **fusión** (los dos trazos pasan a ser uno). Se
 * ofrecen los muros que realmente se encuentran con el extremo; el servidor recalcula las cantidades.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getVerUnionesApiV1TrazosTrazoIdUnionesGetQueryKey,
  useFijarUnionApiV1TrazosTrazoIdUnionesExtremoPut,
  useFusionarMurosApiV1TrazosTrazoIdFusionPost,
  useQuitarUnionApiV1TrazosTrazoIdUnionesExtremoDelete,
  useVerUnionesApiV1TrazosTrazoIdUnionesGet,
} from '@/api/generado/cuantificacion/cuantificacion';
import { queryClient } from '@/app/queryClient';

type Extremo = 'ini' | 'fin';
type Operacion = 'conexion' | 'union' | 'empalme' | 'fusion';

const OPERACIONES: readonly { clave: Operacion; nombre: string; ayuda: string }[] = [
  { clave: 'conexion', nombre: 'Conexión', ayuda: 'El muro continúa: un solo cuerpo con la esquina cerrada; los trazos siguen separados.' },
  { clave: 'union', nombre: 'Unión', ayuda: 'Unión a tope: llega a la cara del otro muro y se detiene.' },
  { clave: 'empalme', nombre: 'Empalme', ayuda: 'El tramo que se solapa se cuenta una sola vez.' },
  { clave: 'fusion', nombre: 'Fusión', ayuda: 'Los dos trazos pasan a ser uno solo.' },
];

const NOMBRE_EXTREMO: Record<Extremo, string> = { ini: 'Inicio', fin: 'Final' };

interface Props {
  readonly trazoId: string;
  readonly puedeEditar: boolean;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function UnionesDelMuro({ trazoId, puedeEditar, onCambio, onError }: Props) {
  const info = useVerUnionesApiV1TrazosTrazoIdUnionesGet(trazoId);
  const fijar = useFijarUnionApiV1TrazosTrazoIdUnionesExtremoPut<ErrorApi>();
  const quitar = useQuitarUnionApiV1TrazosTrazoIdUnionesExtremoDelete<ErrorApi>();
  const fusionar = useFusionarMurosApiV1TrazosTrazoIdFusionPost<ErrorApi>();
  const [elegido, setElegido] = useState<Record<Extremo, string>>({ ini: '', fin: '' });

  const candidatos = info.data?.candidatos ?? [];
  const hay = (e: Extremo) => candidatos.some((c) => c.extremo === e);
  if (!info.data || (!hay('ini') && !hay('fin') && info.data.extremos.length === 0)) return null;

  const recargar = () => {
    void queryClient.invalidateQueries({ queryKey: getVerUnionesApiV1TrazosTrazoIdUnionesGetQueryKey(trazoId) });
  };
  const fallo = (err: unknown) => onError(err instanceof Error ? err.message : 'No se pudo cambiar la unión.');

  async function poner(extremo: Extremo, op: Operacion) {
    const con = elegido[extremo] || candidatos.find((c) => c.extremo === extremo)?.trazo_id;
    if (!con) return;
    try {
      if (op === 'fusion') {
        await fusionar.mutateAsync({ trazoId, data: { con_trazo_id: con } });
        onCambio('Muros fusionados: ahora son un solo trazo.');
      } else {
        await fijar.mutateAsync({ trazoId, extremo, data: { op, con_trazo_id: con } });
        onCambio(`${NOMBRE_EXTREMO[extremo]}: ${OPERACIONES.find((o) => o.clave === op)!.nombre.toLowerCase()}.`);
      }
      recargar();
    } catch (err) {
      fallo(err);
    }
  }

  async function sinUnion(extremo: Extremo) {
    try {
      await quitar.mutateAsync({ trazoId, extremo });
      recargar();
      onCambio(`${NOMBRE_EXTREMO[extremo]}: sin unión.`);
    } catch (err) {
      fallo(err);
    }
  }

  return (
    <div role="group" aria-label="Uniones del muro" style={{ display: 'grid', gap: 4 }}>
      <div className="text-xs text-mute">Uniones · al encontrarse con otro muro</div>
      {(['ini', 'fin'] as const).map((extremo) => {
        const aqui = candidatos.filter((c) => c.extremo === extremo);
        const actual = info.data!.extremos.find((u) => u.extremo === extremo);
        if (aqui.length === 0 && !actual) return null;
        return (
          <div key={extremo} className="row" style={{ gap: 4, flexWrap: 'wrap' }} data-extremo={extremo}>
            <span className="text-xs" style={{ width: 44 }}>
              {NOMBRE_EXTREMO[extremo]}
            </span>
            {aqui.length > 1 && (
              <select
                aria-label={`Muro con el que se encuentra el ${NOMBRE_EXTREMO[extremo].toLowerCase()}`}
                value={elegido[extremo] || aqui[0]!.trazo_id}
                onChange={(e) => setElegido({ ...elegido, [extremo]: e.target.value })}
              >
                {aqui.map((c, i) => (
                  <option key={c.trazo_id} value={c.trazo_id}>
                    Muro {i + 1} · a {Number(c.distancia_m).toFixed(2)} m
                  </option>
                ))}
              </select>
            )}
            {OPERACIONES.map((o) => (
              <button
                key={o.clave}
                type="button"
                className={actual?.op === o.clave ? 'btn btn--sm btn--primary' : 'btn btn--sm'}
                aria-pressed={actual?.op === o.clave}
                title={o.ayuda}
                disabled={!puedeEditar || aqui.length === 0 || fijar.isPending || fusionar.isPending}
                onClick={() => void poner(extremo, o.clave)}
              >
                {o.nombre}
              </button>
            ))}
            {actual && puedeEditar && (
              <button type="button" className="btn btn--ghost btn--sm" aria-label={`Quitar la unión del ${NOMBRE_EXTREMO[extremo].toLowerCase()}`} onClick={() => void sinUnion(extremo)}>
                Quitar
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
