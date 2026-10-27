/**
 * Rediseñar una parte a paramétrico o mixto (cerebro WORKFLOWS.md §8.9, escenario 1 paso 5; D-571).
 *
 * En presupuesto se autoriza, o se rediseña: la parte se valúa **por ensamble** —o parte por PU y
 * parte por ensamble—. Los renglones cuyo concepto está en el ensamble pasan a la cantidad
 * estimada; el resto se queda por PU. **Mixto no se guarda, se reporta en porcentaje.** Primero
 * se propone; aplicar es otro clic.
 */

import { useRef, useState } from 'react';

import { claveDeIdempotencia, type ErrorApi } from '@/api/cliente';
import { useListarEnsamblesApiV1EnsamblesGet } from '@/api/generado/ensambles/ensambles';
import {
  getModificacionesDeLaObraApiV1ObrasObraIdModificacionesGetQueryKey,
  getPartesDeLaObraApiV1ObrasObraIdPartesGetQueryKey,
  getValuacionDePartesApiV1ObrasObraIdPartesValuacionGetQueryKey,
  useRedisenarParteApiV1ObrasObraIdPartesRedisenoPost,
} from '@/api/generado/partes/partes';
import type { RedisenoRespuesta } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { fmtMXN, fmtNum } from '@/lib/formato';
import { etiquetaDeValuacion } from './reglas';

interface Props {
  readonly obraId: string;
  readonly clave: string;
  readonly nombre: string;
  readonly onCerrar: () => void;
}

export default function Rediseno({ obraId, clave, nombre, onCerrar }: Props) {
  const [ensambleId, setEnsambleId] = useState('');
  const [factor, setFactor] = useState('1');
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<RedisenoRespuesta | null>(null);
  const idem = useRef(claveDeIdempotencia());
  const ensambles = useListarEnsamblesApiV1EnsamblesGet();

  const redisenar = useRedisenarParteApiV1ObrasObraIdPartesRedisenoPost<ErrorApi>({
    mutation: {
      onSuccess: (r) => {
        setError(null);
        setResultado(r);
        if (r.aplicado) {
          for (const queryKey of [
            getPartesDeLaObraApiV1ObrasObraIdPartesGetQueryKey(obraId),
            getValuacionDePartesApiV1ObrasObraIdPartesValuacionGetQueryKey(obraId),
            getModificacionesDeLaObraApiV1ObrasObraIdModificacionesGetQueryKey(obraId),
          ]) {
            void queryClient.invalidateQueries({ queryKey });
          }
        }
      },
      onError: (e) => setError(e.message),
    },
    request: { headers: () => ({ 'Idempotency-Key': idem.current }) },
  });

  const pedir = (aplicar: boolean) => {
    idem.current = claveDeIdempotencia();
    redisenar.mutate({ obraId, data: { clave, ensamble_id: ensambleId, factor, aplicar } });
  };
  const factorValido = Number(factor) > 0;

  return (
    <Modal titulo={`Rediseñar a paramétrico · ${nombre}`} onCerrar={onCerrar}>
      <div className="sheet__body col gap-12">
        <p className="text-mute text-sm">
          Los renglones de la parte cuyo concepto está en el ensamble pasan a la cantidad estimada; el resto
          se queda por PU. Si la parte ya estaba validada vuelve a cuantificarse.
        </p>
        {error && <ErrorBanner mensaje={error} />}
        <div className="field">
          <label className="field__label" htmlFor="rediseno-ensamble">
            Ensamble
          </label>
          <select
            id="rediseno-ensamble"
            className="select"
            value={ensambleId}
            onChange={(e) => {
              setEnsambleId(e.target.value);
              setResultado(null);
            }}
          >
            <option value="">Elige un ensamble…</option>
            {(ensambles.data ?? []).map((e) => (
              <option key={e.id} value={e.id}>
                {e.clave} · {e.nombre}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field__label" htmlFor="rediseno-factor">
            Factor (cuántas veces entra)
          </label>
          <input
            id="rediseno-factor"
            className="input"
            type="number"
            min="0"
            step="any"
            value={factor}
            onChange={(e) => {
              setFactor(e.target.value);
              setResultado(null);
            }}
          />
        </div>

        {resultado && (
          <div className="col gap-8" role="region" aria-label="Propuesta del rediseño">
            <div className="text-sm">
              {resultado.aplicado ? 'Aplicado' : 'Propuesta'}:{' '}
              <strong>{etiquetaDeValuacion(resultado.forma_despues, resultado.porcentaje_parametrico_despues)}</strong>
              {' · '}
              {resultado.propuestas.length} {resultado.propuestas.length === 1 ? 'renglón pasa' : 'renglones pasan'} al
              ensamble, {resultado.conservan_pu} se {resultado.conservan_pu === 1 ? 'queda' : 'quedan'} por PU.
            </div>
            {resultado.propuestas.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Concepto</th>
                    <th className="is-num">Ahora</th>
                    <th className="is-num">Estimada</th>
                    <th className="is-num">Importe</th>
                  </tr>
                </thead>
                <tbody>
                  {resultado.propuestas.map((p) => (
                    <tr key={p.actividad_id}>
                      <td>
                        {p.concepto_clave} · {p.descripcion}
                      </td>
                      <td className="is-num">{fmtNum(p.cantidad_actual)}</td>
                      <td className="is-num">{fmtNum(p.cantidad_estimada)}</td>
                      <td className="is-num">
                        {fmtMXN(Number(p.importe_actual))} → {fmtMXN(Number(p.importe_estimado))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {resultado.sin_renglon_en_la_parte.length > 0 && (
              <div className="text-xs text-mute">
                El ensamble trae conceptos que la parte no tiene y no se agregan:{' '}
                {resultado.sin_renglon_en_la_parte.join(', ')}.
              </div>
            )}
          </div>
        )}
      </div>
      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cerrar
        </button>
        <button
          type="button"
          className="btn"
          disabled={ensambleId === '' || !factorValido || redisenar.isPending}
          onClick={() => pedir(false)}
        >
          Proponer
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={
            ensambleId === '' ||
            !factorValido ||
            redisenar.isPending ||
            resultado === null ||
            resultado.aplicado ||
            resultado.propuestas.length === 0
          }
          onClick={() => pedir(true)}
        >
          Aplicar rediseño
        </button>
      </div>
    </Modal>
  );
}
