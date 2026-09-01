/**
 * Replicar un programa base a las obras de su prototipo (§7.5, §11.2
 * `POST /programas-base/{id}/replicar`).
 *
 * Es la pantalla que pidió el jefe de obra: se arma el programa del prototipo
 * una vez y de ahí se reparte a las casas que lo usan. Antes solo existía la
 * instanciación de una en una (`InstanciarPrograma.tsx`), que con un cluster de
 * 40 casas del mismo modelo son 40 vueltas a mano.
 *
 * Tres cosas que la pantalla tiene que dejar claras, y por qué:
 *
 * 1. **Cuáles ya tienen cronograma y en qué versión.** Replicar sobre una obra
 *    ya programada le crea una versión **nueva** (§7.5) —no corrige la que
 *    tiene—, así que eso se ve antes de elegir, no después de enterarse.
 * 2. **El avance mientras corre.** El lote se manda en tandas
 *    (`replica.ts::lotesDe`) precisamente para poder moverlo: con 40 casas, una
 *    sola petición larga deja la pantalla indistinguible de una colgada.
 * 3. **El parte obra por obra al terminar**, con las que fallaron arriba. El
 *    backend es de mejor esfuerzo: una casa mala no cancela el lote, así que
 *    el resultado no es un sí o un no sino una lista, y lo que hay que atender
 *    va primero.
 *
 * La lógica sin render —selección, troceo, avance, recuento y orden del
 * reporte— vive en `replica.ts` y se prueba sin montar nada (§12.11).
 */

import { useMemo, useState, type FormEvent } from 'react';

import {
  replicarProgramaBaseApiV1ProgramasBaseProgramaBaseIdReplicarPost,
  useListarObrasCandidatasApiV1ProgramasBaseProgramaBaseIdObrasGet,
} from '@/api/generado/programacion/programacion';
import type {
  ObraCandidataRespuesta,
  ProgramaBaseRespuesta,
} from '@/api/generado/modelo';
import { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoFechaCorte, HuecosDeLaPlantilla } from './instanciacion';
import {
  alternarObra,
  avisoDeSeleccion,
  lotesDe,
  obrasElegidas,
  partesParaReporte,
  progresoDe,
  recuentoDe,
  todasLasObras,
  type ParteDeObra,
} from './replica';

interface Props {
  readonly base: ProgramaBaseRespuesta;
  /** "CAS-1 · Casa tipo", si el prototipo se pudo resolver en la tabla. */
  readonly nombrePrototipo: string | null;
  readonly onCerrar: () => void;
}

export function ReplicarPrograma({ base, nombrePrototipo, onCerrar }: Props) {
  const [fechaCorte, setFechaCorte] = useState('');
  const [seleccion, setSeleccion] = useState<ReadonlySet<string>>(new Set());
  const [corriendo, setCorriendo] = useState(false);
  const [hechas, setHechas] = useState(0);
  const [partes, setPartes] = useState<ParteDeObra[] | null>(null);
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const candidatasQ = useListarObrasCandidatasApiV1ProgramasBaseProgramaBaseIdObrasGet<
    ObraCandidataRespuesta[],
    ErrorApi
  >(base.id);

  const candidatas = useMemo(() => candidatasQ.data ?? [], [candidatasQ.data]);
  const aviso = useMemo(
    () => avisoDeSeleccion(candidatas, seleccion),
    [candidatas, seleccion],
  );
  const elegidas = useMemo(
    () => obrasElegidas(candidatas, seleccion),
    [candidatas, seleccion],
  );
  const progreso = progresoDe(hechas, elegidas.length);
  const recuento = partes === null ? null : recuentoDe(partes);

  async function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (corriendo || elegidas.length === 0) return;

    setCorriendo(true);
    setError(null);
    setPartes(null);
    setHechas(0);

    // Acumulador local y no el estado: `setPartes` es asíncrono y las tandas se
    // encadenan dentro de la misma función, así que leer el estado entre una y
    // otra devolvería el valor anterior.
    const acumulado: ParteDeObra[] = [];

    try {
      for (const lote of lotesDe(elegidas)) {
        const respuesta = await replicarProgramaBaseApiV1ProgramasBaseProgramaBaseIdReplicarPost(
          base.id,
          { obras: lote, fecha_corte: fechaCorte.trim() === '' ? null : fechaCorte },
        );
        acumulado.push(...respuesta.obras);
        // Se publica tanda a tanda: el parte parcial ya es útil, y si la
        // siguiente revienta lo que sí quedó programado no se pierde de vista.
        setPartes([...acumulado]);
        setHechas(acumulado.length);
      }
    } catch (falla) {
      // Aquí solo caen los fallos del **lote**: que el programa base no exista
      // o ya no sea el vigente, o que se caiga la red. Lo que le pasa a una
      // obra concreta viaja como `motivo` dentro de una respuesta exitosa.
      const api = falla instanceof ErrorApi ? falla : null;
      setError({
        mensaje: api?.message ?? 'No se pudo completar la replicación.',
        campo: api?.campo,
      });
    } finally {
      setCorriendo(false);
      void candidatasQ.refetch();
    }
  }

  const todasMarcadas =
    candidatas.length > 0 && seleccion.size === candidatas.length;

  return (
    <Modal
      titulo={`Replicar a las obras · ${base.nombre ?? base.id.slice(0, 8)}`}
      onCerrar={onCerrar}
    >
      <form onSubmit={alEnviar} className="sheet__body col gap-12">
        <div className="text-sm text-mute">
          Baja la plantilla de duraciones de este programa base a las obras del
          prototipo{nombrePrototipo ? ` ${nombrePrototipo}` : ''} y recalcula la ruta
          crítica de cada una.
        </div>

        {!base.vigente && (
          <div className="field__hint" style={{ color: 'var(--c-warn)' }}>
            Esta versión está retirada y no se puede replicar: la instanciación siempre
            baja el programa base <strong>vigente</strong> del prototipo (§7.5). Ábrela en
            el canvas y guárdala para volverla la vigente.
          </div>
        )}

        {/* §7.5: cada bajada versiona. Se advierte con el número exacto de
            casas afectadas, no en abstracto: "12 obras ya tienen cronograma"
            es lo que hace que alguien se detenga a revisar la selección. */}
        <div className="field__hint" style={{ color: 'var(--c-warn)' }}>
          Cada obra elegida queda con una <strong>versión nueva</strong> de cronograma
          (§7.5); la anterior se retira pero se conserva en su historial.
          {aviso.conCronograma > 0 && (
            <>
              {' '}
              <span className="mono tnum">{aviso.conCronograma}</span> de las{' '}
              <span className="mono tnum">{aviso.total}</span> elegidas ya tienen uno.
            </>
          )}
        </div>

        <div className="row gap-8">
          <button
            type="button"
            className="btn btn--sm"
            disabled={candidatas.length === 0 || corriendo}
            onClick={() =>
              setSeleccion(todasMarcadas ? new Set() : todasLasObras(candidatas))
            }
          >
            {todasMarcadas ? 'Ninguna' : 'Todas'}
          </button>
          <span className="text-sm text-mute">
            <span className="mono tnum">{seleccion.size}</span> de{' '}
            <span className="mono tnum">{candidatas.length}</span> obras del prototipo
          </span>
        </div>

        <div className="table-wrap">
          <div className="table-scroll" style={{ maxHeight: 280 }}>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: '1%' }}>Elegir</th>
                  <th>Obra</th>
                  <th>Estatus</th>
                  <th className="is-num">Cronograma</th>
                </tr>
              </thead>
              <tbody>
                {candidatasQ.isLoading ? (
                  <tr>
                    <td colSpan={4}>
                      <div className="text-mute text-sm" style={{ padding: '16px 0' }}>
                        Cargando obras…
                      </div>
                    </td>
                  </tr>
                ) : candidatas.length === 0 ? (
                  <tr>
                    <td colSpan={4}>
                      <div className="text-mute text-sm" style={{ padding: '16px 0' }}>
                        Este prototipo todavía no tiene obras: no hay a dónde replicar
                        (§7.2).
                      </div>
                    </td>
                  </tr>
                ) : (
                  candidatas.map((obra) => (
                    <tr
                      key={obra.obra_id}
                      className={seleccion.has(obra.obra_id) ? 'is-selected' : undefined}
                    >
                      <td>
                        <input
                          type="checkbox"
                          checked={seleccion.has(obra.obra_id)}
                          disabled={corriendo}
                          aria-label={`Replicar a ${obra.clave}`}
                          onChange={() =>
                            setSeleccion(alternarObra(seleccion, obra.obra_id))
                          }
                        />
                      </td>
                      <td className="is-key">{obra.clave}</td>
                      <td className="text-sm">{obra.estatus}</td>
                      <td className="is-num">
                        {obra.version_cronograma === null ? (
                          <span className="badge badge--outline">Sin cronograma</span>
                        ) : (
                          <span
                            className="badge badge--info"
                            title="Replicar aquí crea la versión siguiente (§7.5)"
                          >
                            v{obra.version_cronograma} → v{obra.version_cronograma + 1}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <CampoFechaCorte id="replicar-corte" valor={fechaCorte} onCambio={setFechaCorte} />

        {corriendo && (
          <div role="status" aria-live="polite">
            <div className="bar__label">
              <span>Replicando…</span>
              <span className="mono tnum">
                {progreso.hechas} / {progreso.total}
              </span>
            </div>
            <div className="bar">
              <div className="bar__fill" style={{ width: `${progreso.pct}%` }} />
            </div>
          </div>
        )}

        {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}

        {recuento !== null && partes !== null && (
          <div className="col gap-8" role="status">
            <div className="text-sm row gap-8">
              <span className="badge badge--ok">
                {recuento.programadas} programadas
              </span>
              {recuento.fallidas > 0 && (
                <span className="badge badge--danger">
                  {recuento.fallidas} sin replicar
                </span>
              )}
              {recuento.conHuecos > 0 && (
                <span className="badge badge--warn">
                  {recuento.conHuecos} con huecos de plantilla
                </span>
              )}
            </div>

            {/* Las que fallaron van arriba: con 40 renglones lo primero que se
                necesita ver es lo que hay que atender, no lo que salió bien. */}
            <div className="table-wrap">
              <div className="table-scroll" style={{ maxHeight: 240 }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Obra</th>
                      <th>Resultado</th>
                      <th>Detalle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {partesParaReporte(partes).map((parte) => (
                      <tr key={parte.obra_id}>
                        <td className="is-key">
                          {parte.clave ?? parte.obra_id.slice(0, 8)}
                        </td>
                        <td>
                          {parte.programada ? (
                            <span className="badge badge--ok">v{parte.version}</span>
                          ) : (
                            <span className="badge badge--danger">Sin replicar</span>
                          )}
                        </td>
                        <td className="text-sm">
                          {parte.programada ? (
                            <>
                              <span className="mono tnum">{parte.n_actividades}</span>{' '}
                              actividades programadas.
                              <HuecosDeLaPlantilla
                                sinItem={parte.sin_item}
                                refsNoResueltas={parte.refs_no_resueltas}
                              />
                            </>
                          ) : (
                            parte.motivo
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        <div className="sheet__footer">
          <button type="button" className="btn btn--ghost" onClick={onCerrar}>
            {partes !== null && !corriendo ? 'Cerrar' : 'Cancelar'}
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={corriendo || elegidas.length === 0 || !base.vigente}
          >
            {corriendo
              ? `Replicando ${progreso.hechas}/${progreso.total}…`
              : `Replicar a ${elegidas.length} obra${elegidas.length === 1 ? '' : 's'}`}
          </button>
        </div>
      </form>
    </Modal>
  );
}
