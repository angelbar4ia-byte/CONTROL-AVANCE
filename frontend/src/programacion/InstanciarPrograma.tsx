/**
 * Instanciar / versionar el cronograma de una obra desde el programa base
 * (§11.2 `POST /obras/{id}/programa`, §7.5).
 *
 * El endpoint baja la plantilla de duraciones del prototipo a las actividades
 * de la obra, resuelve las dependencias a ids de actividad y recalcula la
 * ruta, todo del lado del servidor. Este componente solo pide la fecha de
 * corte y presenta lo que el backend reporta: la versión creada, cuántas
 * actividades quedaron programadas, cuáles no traían renglón en el programa
 * base y qué dependencias quedaron sin resolver.
 *
 * Cada llamada crea una **versión nueva** (§7.5), así que el botón lo dice.
 */

import { useState, type FormEvent } from 'react';

import {
  useInstanciarProgramaDeObraApiV1ObrasObraIdProgramaPost,
  useListarProgramasBaseApiV1ProgramasBaseGet,
} from '@/api/generado/programacion/programacion';
import type { ObraRespuesta, ProgramaBaseRespuesta, ProgramaInstanciadoRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import type { Rol } from '@/shell/navegacion';
import { puedeAdministrarProgramasBase } from './reglas';

interface Props {
  readonly obra: ObraRespuesta;
  readonly rol: Rol;
  readonly onCerrar: () => void;
  /** El padre revalida el cronograma con la versión nueva. */
  readonly onInstanciado: () => void;
}

export function InstanciarPrograma({ obra, rol, onCerrar, onInstanciado }: Props) {
  const [fechaCorte, setFechaCorte] = useState('');
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);
  const [resultado, setResultado] = useState<ProgramaInstanciadoRespuesta | null>(null);

  // El programa base vigente es contexto, no un dato que se envíe: el backend
  // resuelve solo cuál le toca al prototipo de la obra. `GET /programas-base`
  // es (C) —§11.2—, así que al Supervisor no se le pide.
  const basesQ = useListarProgramasBaseApiV1ProgramasBaseGet<ProgramaBaseRespuesta[], ErrorApi>(
    { prototipo_id: obra.prototipo_id ?? undefined, solo_vigentes: true },
    {
      query: {
        enabled: puedeAdministrarProgramasBase(rol) && obra.prototipo_id !== null,
      },
    },
  );

  const instanciar = useInstanciarProgramaDeObraApiV1ObrasObraIdProgramaPost<ErrorApi>({
    mutation: {
      onSuccess: (respuesta) => {
        setError(null);
        setResultado(respuesta);
        onInstanciado();
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const vigente = basesQ.data?.[0] ?? null;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (instanciar.isPending) return;
    instanciar.mutate({
      obraId: obra.id,
      data: { fecha_corte: fechaCorte.trim() === '' ? null : fechaCorte },
    });
  }

  return (
    <Modal titulo={`Instanciar programa · ${obra.clave}`} onCerrar={onCerrar}>
      <form onSubmit={alEnviar} className="sheet__body col gap-12">
        <div className="text-sm text-mute">
          Baja la plantilla de duraciones del prototipo a las actividades de la obra y
          recalcula la ruta crítica. Cada alta crea una <strong>versión nueva</strong> del
          cronograma (§7.5).
        </div>

        {obra.prototipo_id === null && (
          <div className="field__hint" style={{ color: 'var(--c-warn)' }}>
            La obra no tiene prototipo, así que no hay programa base del cual bajar
            duraciones (§7.2).
          </div>
        )}

        {vigente !== null && (
          <div className="text-sm">
            Programa base vigente:{' '}
            <span className="mono">
              {vigente.nombre ?? vigente.id.slice(0, 8)} · v{vigente.version}
            </span>
          </div>
        )}

        <div className="field">
          <label className="field__label" htmlFor="instanciar-corte">
            Fecha de corte (opcional)
          </label>
          <input
            id="instanciar-corte"
            className="input"
            type="date"
            value={fechaCorte}
            onChange={(e) => setFechaCorte(e.target.value)}
          />
          <div className="field__hint">
            Fecha contra la que se mide el desfase; vacío = hoy (§6).
          </div>
        </div>

        {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}

        {resultado && (
          <div className="col gap-4" role="status">
            <div className="text-sm">
              <span className="badge badge--ok">Versión {resultado.version}</span>{' '}
              <span className="mono tnum">{resultado.n_actividades}</span> actividades
              programadas.
            </div>
            {resultado.sin_item.length > 0 && (
              <div className="field__hint">
                <span className="mono tnum">{resultado.sin_item.length}</span> actividades sin
                renglón en el programa base: conservaron su programación anterior (§7.5).
              </div>
            )}
            {resultado.refs_no_resueltas.length > 0 && (
              <div className="field__hint" style={{ color: 'var(--c-warn)' }}>
                <span className="mono tnum">{resultado.refs_no_resueltas.length}</span>{' '}
                dependencias del programa base no corresponden a ninguna actividad de la obra;
                el motor las ignoró (§6).
              </div>
            )}
          </div>
        )}

        <div className="sheet__footer">
          <button type="button" className="btn btn--ghost" onClick={onCerrar}>
            {resultado ? 'Cerrar' : 'Cancelar'}
          </button>
          <button type="submit" className="btn btn--primary" disabled={instanciar.isPending}>
            {instanciar.isPending ? 'Instanciando…' : 'Instanciar versión nueva'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
