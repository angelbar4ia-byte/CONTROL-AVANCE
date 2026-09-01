/**
 * Programar un nodo del árbol WBS y repartir sus días hacia abajo
 * (§11.2 `POST /obras/{id}/programa/nodos/{prototipo_nodo_id}`, §7.4).
 *
 * El gesto que pidió el jefe de obra: se capturan 20 días en la etapa
 * `ESTRUCTURA PB` y sus conceptos quedan acomodados **uno tras otro** dentro de
 * esa ventana, repartidos en proporción a su importe. Todo el reparto ocurre en
 * el servidor (`domain/programacion/jerarquia`); aquí sólo se captura la
 * ventana y se presenta lo que respondió.
 *
 * ## El conflicto padre-hijo es la mitad de este componente
 *
 * Si los conceptos de abajo ya venían programados con otra cifra, el backend
 * responde **409 sin escribir nada** (§7.5). Eso no es un error que reportar y
 * seguir: es la pregunta que hay que hacerle al usuario, y este componente la
 * presenta como lo que es, dos opciones excluyentes:
 *
 *   - *conservar la cifra del nodo* → repite la llamada con `forzar`, que
 *     reparte los días capturados y pisa el detalle;
 *   - *conservar el detalle de los conceptos* → no llama a nada. Es un cierre,
 *     no un "cancelar": no hacer nada **es** la decisión, porque el detalle ya
 *     está escrito.
 *
 * Nunca se manda `forzar` en el primer intento. Que la pantalla decidiera por
 * el usuario —aunque fuera "el padre gana"— vaciaría de sentido el 409, que
 * existe justo para que nadie decida en silencio.
 */

import { useState, type FormEvent } from 'react';

import { useProgramarNodoDelArbolApiV1ObrasObraIdProgramaNodosPrototipoNodoIdPost } from '@/api/generado/programacion/programacion';
import type { NodoProgramadoRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { fmtFecha, fmtNum } from '@/lib/formato';
import type { FilaJerarquia } from './jerarquia';

/** El backend marca el choque padre-hijo con este `type` del problem+json. */
const TIPO_CONFLICTO = 'conflicto-de-programacion-jerarquica';

interface Props {
  readonly obraId: string;
  readonly nodo: FilaJerarquia;
  readonly onCerrar: () => void;
  /** El padre revalida el árbol y la ruta con lo que quedó escrito. */
  readonly onProgramado: () => void;
}

export function ProgramarNodo({ obraId, nodo, onCerrar, onProgramado }: Props) {
  const [dias, setDias] = useState(
    nodo.duracionDias > 0 ? String(nodo.duracionDias) : '',
  );
  const [fechaInicio, setFechaInicio] = useState(nodo.inicio ?? '');
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);
  const [conflicto, setConflicto] = useState<string | null>(null);
  const [resultado, setResultado] = useState<NodoProgramadoRespuesta | null>(null);

  const programar =
    useProgramarNodoDelArbolApiV1ObrasObraIdProgramaNodosPrototipoNodoIdPost<ErrorApi>({
      mutation: {
        onSuccess: (respuesta) => {
          setError(null);
          setConflicto(null);
          setResultado(respuesta);
          onProgramado();
        },
        onError: (err) => {
          setResultado(null);
          if (err.tipo?.endsWith(TIPO_CONFLICTO) === true) {
            // No es un error que mostrar y ya: es la elección del §7.5. Se
            // guarda aparte del banner de error para que la pantalla ofrezca
            // las dos salidas en vez de sólo "cerrar".
            setConflicto(err.message);
            setError(null);
            return;
          }
          setConflicto(null);
          setError({ mensaje: err.message, campo: err.campo });
        },
      },
    });

  function enviar(forzar: boolean) {
    programar.mutate({
      obraId,
      prototipoNodoId: nodo.nodoId,
      data: {
        duracion_dias: Number(dias),
        fecha_inicio: fechaInicio.trim() === '' ? null : fechaInicio,
        forzar,
      },
    });
  }

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (programar.isPending || dias.trim() === '') return;
    enviar(false);
  }

  return (
    <Modal titulo={`Programar · ${nodo.nombre}`} onCerrar={onCerrar}>
      <form onSubmit={alEnviar} className="sheet__body col gap-12">
        <div className="text-sm text-mute">
          Los <span className="mono tnum">{nodo.nActividades}</span> concepto
          {nodo.nActividades === 1 ? '' : 's'} que cuelgan de este {nodo.tipo} se acomodan
          uno tras otro dentro de la ventana, repartidos en proporción a su importe (§7.4).
          La barra de {nodo.tipo} no es una actividad: se deriva de ellos.
        </div>

        <div className="field">
          <label className="field__label" htmlFor="nodo-dias">
            Días de la ventana *
          </label>
          <input
            id="nodo-dias"
            className="input input--mono"
            type="number"
            step="any"
            min="0"
            value={dias}
            onChange={(e) => {
              setDias(e.target.value);
              setConflicto(null);
            }}
            required
          />
          <div className="field__hint">
            Hoy sus conceptos suman {fmtNum(nodo.duracionHojasDias)} d de trabajo y ocupan{' '}
            {fmtNum(nodo.duracionDias)} d de calendario.
          </div>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="nodo-inicio">
            Inicio de la ventana
          </label>
          <input
            id="nodo-inicio"
            className="input"
            type="date"
            value={fechaInicio}
            onChange={(e) => setFechaInicio(e.target.value)}
          />
          <div className="field__hint">
            Sin fecha se conserva donde el {nodo.tipo} ya está colocado; cambiar la duración
            no debería moverlo de lugar.
          </div>
        </div>

        {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}

        {conflicto !== null && (
          <div className="col gap-8" role="alert">
            <div className="text-sm">
              <span className="badge badge--warn">Decide tú</span>{' '}
              {conflicto}
            </div>
            <div className="row gap-8" style={{ flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn btn--accent btn--sm"
                disabled={programar.isPending}
                onClick={() => enviar(true)}
              >
                Conservar los {fmtNum(Number(dias))} d de este {nodo.tipo}
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={onCerrar}
              >
                Conservar el detalle de los conceptos
              </button>
            </div>
            <div className="field__hint">
              No se ha escrito nada todavía. Conservar el detalle es cerrar sin cambios: lo
              que los conceptos traen ya está guardado.
            </div>
          </div>
        )}

        {resultado && (
          <div className="col gap-4" role="status">
            <div className="text-sm">
              <span className="badge badge--ok">Repartido</span>{' '}
              <span className="mono tnum">{resultado.actividades.length}</span> concepto
              {resultado.actividades.length === 1 ? '' : 's'} entre{' '}
              {fmtFecha(resultado.fecha_inicio)} y {fmtFecha(resultado.fecha_termino)}.
            </div>
            {resultado.omitidas.length > 0 && (
              <div className="field__hint" style={{ color: 'var(--c-warn)' }}>
                <span className="mono tnum">{resultado.omitidas.length}</span> concepto(s)
                quedaron fuera del reparto por estar interrumpidos en tramos (§7.6): una
                ventana gruesa no sabe cómo volver a partirlos. Prográmalos uno por uno.
              </div>
            )}
          </div>
        )}

        <div className="sheet__footer">
          <button type="button" className="btn btn--ghost" onClick={onCerrar}>
            {resultado ? 'Cerrar' : 'Cancelar'}
          </button>
          {!resultado && conflicto === null && (
            <button
              type="submit"
              className="btn btn--accent"
              disabled={programar.isPending || dias.trim() === ''}
            >
              {programar.isPending ? 'Repartiendo…' : 'Repartir hacia los conceptos'}
            </button>
          )}
        </div>
      </form>
    </Modal>
  );
}
