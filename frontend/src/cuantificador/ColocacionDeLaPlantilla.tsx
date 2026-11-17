/**
 * Lo que la plantilla del muro coloca en el plano y a qué conceptos alimenta (Ola 4C; M-4).
 *
 * Los castillos ubicados de la plantilla se colocan como instancias del elemento: suben la altura del muro (la del driver de la obra) menos su
 * arranque y restan de sus m². El concepto que paga cada parte lo eligen el nivel y el alto del castillo (2A) y la ranura enlazada en el
 * Paramétrico (4B). Si la partida no está en el árbol de la obra, avisa y no cuenta. Todo lo calcula y valida el servidor: aquí solo se pinta.
 */

import type { ErrorApi } from '@/api/cliente';
import {
  getColocacionDelMuroApiV1TrazosTrazoIdMuroPlantillaColocacionGetQueryKey,
  useColocacionDelMuroApiV1TrazosTrazoIdMuroPlantillaColocacionGet,
  useColocarPlantillaEnElMuroApiV1TrazosTrazoIdMuroPlantillaColocarPost,
  useRetirarPlantillaDelMuroApiV1TrazosTrazoIdMuroPlantillaColocarDelete,
} from '@/api/generado/artefacto-de-muros/artefacto-de-muros';
import { queryClient } from '@/app/queryClient';
import { fmtNum } from '@/lib/formato';

interface Props {
  readonly trazoId: string;
  /** Cambió lo colocado: la pantalla recarga lo que depende de ello. */
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

const NOMBRE_DE_REGLA = {
  separacion: 'cada separación y extremos',
  extremos: 'solo extremos',
  por_ml: 'por ml de muro',
  total: 'total del prototipo (por m² de muro)',
} as const;

/** Recarga lo que cambia al colocar o retirar: los vanos del muro, el plano, las cantidades y lo que toman los elementos. */
function recargar(trazoId: string) {
  void queryClient.invalidateQueries({ queryKey: getColocacionDelMuroApiV1TrazosTrazoIdMuroPlantillaColocacionGetQueryKey(trazoId) });
  void queryClient.invalidateQueries({
    predicate: (q) => /vanos|trazos|cuantificacion|elementos-parametricos|muro/.test(JSON.stringify(q.queryKey)),
  });
}

export function ColocacionDeLaPlantilla({ trazoId, onCambio, onError }: Props) {
  const consulta = useColocacionDelMuroApiV1TrazosTrazoIdMuroPlantillaColocacionGet<unknown>(trazoId, { query: { retry: false } });
  const colocar = useColocarPlantillaEnElMuroApiV1TrazosTrazoIdMuroPlantillaColocarPost<ErrorApi>();
  const retirar = useRetirarPlantillaDelMuroApiV1TrazosTrazoIdMuroPlantillaColocarDelete<ErrorApi>();
  const d = consulta.data as import('@/api/generado/modelo').ColocacionDelMuroRespuesta | undefined;
  if (consulta.isLoading) return <p className="text-mute text-xs">Leyendo lo que coloca la plantilla…</p>;
  if (!d) return null;

  const ocupado = colocar.isPending || retirar.isPending;
  const hayQueColocar = d.elementos.some((e) => e.se_coloca);
  const hayColocados = d.elementos.some((e) => e.colocados > 0);

  async function ponerEnElPlano() {
    try {
      const r = await colocar.mutateAsync({ trazoId });
      recargar(trazoId);
      onCambio(`Plantilla colocada: ${r.colocados} castillo${r.colocados === 1 ? '' : 's'} en el plano.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo colocar la plantilla.');
    }
  }

  async function quitarDelPlano() {
    try {
      const r = await retirar.mutateAsync({ trazoId });
      recargar(trazoId);
      onCambio(`Se retiró lo que colocó la plantilla (${r.retirados}).`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo retirar lo colocado.');
    }
  }

  return (
    <div className="colocacion-plantilla" role="region" aria-label="Elementos de la plantilla">
      <div className="opciones__titulo">Elementos de la plantilla</div>
      <p className="text-mute text-xs" data-testid="contexto-de-colocacion">
        {fmtNum(d.largo_m)} m de largo · {fmtNum(d.altura_m)} m de alto
        {d.nivel !== null && d.nivel !== undefined ? ` · nivel ${d.nivel}` : ''}
      </p>
      <ul className="colocacion-plantilla__lista">
        {d.elementos.map((e) => (
          <li key={e.uid} data-elemento={e.uid}>
            <div>
              <b className="mono">{e.ref}</b>{' '}
              {e.clase === 'castillo'
                ? `· ${e.modo === 'ubicado' ? e.piezas : fmtNum(e.piezas_estimadas)} pza × ${fmtNum(e.alto_m)} m · ${e.modo === 'ubicado' ? `colocados ${e.colocados} de ${e.piezas}` : 'estimados (no se colocan)'}`
                : `· ${fmtNum(e.metros)} ml (el largo del muro)`}
              {e.regla && e.modo !== 'ubicado' && <span className="text-mute text-xs" data-testid={`regla-de-${e.uid}`}> · {NOMBRE_DE_REGLA[e.regla]}</span>}
            </div>
            {e.origen && <div className="text-mute text-xs mono">{e.origen}</div>}
            {e.conceptos.length > 0 && (
              <ul className="colocacion-plantilla__conceptos">
                {e.conceptos.map((c) => (
                  <li key={`${c.ranura}-${c.clave}`} data-concepto={c.clave} data-cuenta={c.cuenta ? 'si' : 'no'}>
                    <span className="mono">{c.clave}</span> · {fmtNum(c.cantidad)} {c.unidad}
                    {c.cuenta ? ' · cuenta' : ` · no cuenta: ${c.aviso ?? c.estado}`}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      {d.avisos.map((a) => (
        <p key={a} className="text-xs mct__aviso" role="status">
          {a}
        </p>
      ))}
      <div className="opciones__fila">
        <button type="button" className="btn btn--sm" disabled={ocupado || !hayQueColocar} onClick={() => void ponerEnElPlano()}>
          Colocar los elementos de la plantilla
        </button>
        {hayColocados && (
          <button type="button" className="btn btn--ghost btn--sm" disabled={ocupado} onClick={() => void quitarDelPlano()}>
            Retirar lo colocado
          </button>
        )}
      </div>
    </div>
  );
}
