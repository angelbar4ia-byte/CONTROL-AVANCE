/**
 * Planeación por obra: cuántas cuadrillas hacen falta, y quién las pone (§8.3).
 *
 * Contesta la pregunta con la que se contrata —*"¿cuántas cuadrillas necesito
 * para alcanzar la meta programada por frente?"*— y guarda al lado la
 * decisión. La cuenta la hace el backend
 * (`domain/planeacion/cuadrillas.py`); esta pantalla elige la obra y el rango,
 * muestra lo que vuelve y persiste el trato.
 *
 * ## Quién planifica
 *
 * El residente. El programa base es una guía y quien decide con qué gente se
 * cumple es quien está en la obra; el supervisor y Control entran porque ven
 * las mismas obras y a veces contratan ellos. **RLS acota** a las de cada uno
 * (§12.4), así que la guarda de rol solo evita ofrecérselo a quien no
 * planifica.
 *
 * ## Sugerencia y decisión, las dos
 *
 * El pico sale de un rendimiento del catálogo; las cuadrillas planeadas las
 * pone quien conoce al contratista. Enseñar solo la sugerencia haría que el
 * sistema pareciera decidir, y enseñar solo la decisión escondería contra qué
 * se está decidiendo.
 *
 * ## El renglón "sin frente asignado"
 *
 * Es trabajo real cuyas etapas todavía no se mapearon (§8.3, migración 0045).
 * No se esconde: si se descartara, el total de la obra no cuadraría con la suma
 * de sus frentes y nadie sabría que falta capturar algo.
 */

import { useMemo, useState } from 'react';

import { useListarContratistasApiV1ContratistasGet } from '@/api/generado/catalogos/catalogos';
import {
  useAsignarFrenteApiV1ObrasObraIdPlaneacionFrentesFrenteIdPut,
  usePlaneacionPorFrenteApiV1ObrasObraIdPlaneacionFrentesGet,
} from '@/api/generado/planeacion/planeacion';
import type {
  ContratistaRespuesta,
  FrenteDeObraRespuesta,
  PlaneacionRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtEntero, fmtNum } from '@/lib/formato';
import { Modal } from '@/lib/Modal';
import { SelectorObra } from '@/lib/SelectorObra';
import { TablaFrentes } from './TablaFrentes';
import {
  listoParaConsultar,
  parametrosDeConsulta,
  puedePlanear,
  rangoPorDefecto,
  rangoValido,
  SIN_FRENTE,
  totalDeJornadas,
  type FiltroPlaneacion,
  type Granularidad,
} from './reglas';

export default function PlaneacionObra() {
  const { sesion } = useSesion();
  const rol = sesion?.rol ?? 'residente';

  const [filtro, setFiltro] = useState<FiltroPlaneacion>(() => ({
    obraId: '',
    granularidad: 'semana',
    rango: rangoPorDefecto(new Date(), 'semana'),
  }));
  const [enEdicion, setEnEdicion] = useState<FrenteDeObraRespuesta | null>(null);

  const listo = listoParaConsultar(filtro);
  const parametros = useMemo(() => parametrosDeConsulta(filtro), [filtro]);

  const consulta = usePlaneacionPorFrenteApiV1ObrasObraIdPlaneacionFrentesGet<
    PlaneacionRespuesta,
    ErrorApi
  >(filtro.obraId, parametros as never, { query: { enabled: listo } });

  // El catálogo entero: quién *sabe* hacer un frente es capacidad
  // (`contratista_frente`), y quién lo lleva en esta obra es el trato. Filtrar
  // el selector por capacidad dejaría fuera al que se contrata por primera vez
  // para algo nuevo, que es un caso normal.
  const contratistasQ = useListarContratistasApiV1ContratistasGet<
    ContratistaRespuesta[],
    ErrorApi
  >(undefined, { query: { enabled: listo } });

  const asignar = useAsignarFrenteApiV1ObrasObraIdPlaneacionFrentesFrenteIdPut<ErrorApi>(
    {
      mutation: {
        onSuccess: () => {
          setEnEdicion(null);
          void consulta.refetch();
        },
      },
    },
  );

  if (!sesion) return null;

  const datos = consulta.data;
  const periodos = datos?.periodos ?? [];
  const frentes = datos?.frentes ?? [];
  const puedeAsignar = puedePlanear(rol);

  const jornadasTotales = totalDeJornadas(frentes);
  const sinFrente = frentes.find((f) => f.frente_id === SIN_FRENTE);

  function cambiar(cambios: Partial<FiltroPlaneacion>): void {
    setFiltro((previo) => ({ ...previo, ...cambios }));
  }

  function cambiarGranularidad(granularidad: Granularidad): void {
    // El rango se re-estira: doce semanas de columnas mensuales serían tres.
    cambiar({ granularidad, rango: rangoPorDefecto(new Date(), granularidad) });
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Planeación</div>
          <h1 className="page__title">Cuadrillas por frente</h1>
          <div className="page__subtitle">
            Cuántas cuadrillas pide cada frente para alcanzar la meta del
            programa, y quién lo lleva (§8.3). Las jornadas salen del cronograma
            por el APU; las cuadrillas, de dividirlas entre los días hábiles del
            periodo. El programa base es una guía: quien planifica es el
            residente.
          </div>
        </div>
      </div>

      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}
      {asignar.error && <ErrorBanner mensaje={asignar.error.message} />}

      <div className="filterbar">
        <div style={{ minWidth: 260 }}>
          <SelectorObra
            id="obra"
            etiqueta="Obra"
            valor={filtro.obraId}
            onCambio={(obraId) => cambiar({ obraId })}
          />
        </div>

        <div className="field" style={{ maxWidth: 150 }}>
          <label className="field__label" htmlFor="granularidad">
            Periodo
          </label>
          <select
            id="granularidad"
            className="select"
            value={filtro.granularidad}
            onChange={(e) => cambiarGranularidad(e.target.value as Granularidad)}
          >
            <option value="semana">Por semana</option>
            <option value="mes">Por mes</option>
          </select>
        </div>

        <div className="field" style={{ maxWidth: 160 }}>
          <label className="field__label" htmlFor="desde">
            Desde
          </label>
          <input
            id="desde"
            className="input"
            type="date"
            value={filtro.rango.desde}
            onChange={(e) =>
              cambiar({ rango: { ...filtro.rango, desde: e.target.value } })
            }
          />
        </div>
        <div className="field" style={{ maxWidth: 160 }}>
          <label className="field__label" htmlFor="hasta">
            Hasta
          </label>
          <input
            id="hasta"
            className="input"
            type="date"
            value={filtro.rango.hasta}
            onChange={(e) =>
              cambiar({ rango: { ...filtro.rango, hasta: e.target.value } })
            }
          />
        </div>
      </div>

      {!rangoValido(filtro.rango) ? (
        <div className="empty">
          <div className="empty-title">El rango está al revés</div>
          <div className="empty-sub">La fecha de inicio va antes que la de fin.</div>
        </div>
      ) : !listo ? (
        <div className="empty">
          <div className="empty-title">Elige una obra</div>
          <div className="empty-sub">
            La planeación es siempre de una obra: el contratista de un frente
            puede ser otro en la obra de al lado, así que no hay una respuesta
            agregada.
          </div>
        </div>
      ) : consulta.isLoading ? (
        <div className="text-mute text-sm" style={{ padding: 24 }}>
          Calculando…
        </div>
      ) : frentes.length === 0 ? (
        <div className="empty">
          <div className="empty-title">Nada programado en este rango</div>
          <div className="empty-sub">
            La obra no tiene actividades con mano de obra calendarizada en estas
            fechas. Si acaba de generarse, falta aplicarle el programa base.
          </div>
        </div>
      ) : (
        <>
          <TablaFrentes
            periodos={periodos}
            frentes={frentes}
            puedeAsignar={puedeAsignar}
            onAsignar={setEnEdicion}
          />
          <div className="field__hint mt-8">
            {fmtEntero(frentes.length)} frente(s) en {fmtEntero(periodos.length)}{' '}
            periodo(s), {fmtNum(jornadasTotales)} jornada(s) de mano de obra. Las
            cuadrillas <strong>no se redondean</strong>: 2.3 dice que dos
            aprietan y tres sobran.
            {sinFrente !== undefined &&
              ` ${fmtNum(sinFrente.total_jornadas)} jornada(s) están en etapas sin frente: se mapean en Frentes de obra.`}
          </div>
        </>
      )}

      {enEdicion !== null && (
        <DialogoDeAsignacion
          frente={enEdicion}
          contratistas={contratistasQ.data ?? []}
          guardando={asignar.isPending}
          onCerrar={() => setEnEdicion(null)}
          onGuardar={(datos) =>
            asignar.mutate({
              obraId: filtro.obraId,
              frenteId: enEdicion.frente_id,
              data: datos,
            })
          }
        />
      )}
    </div>
  );
}

interface Trato {
  readonly contratista_id: string | null;
  readonly cuadrillas_plan: number | null;
  readonly notas: string | null;
}

function DialogoDeAsignacion({
  frente,
  contratistas,
  guardando,
  onCerrar,
  onGuardar,
}: {
  readonly frente: FrenteDeObraRespuesta;
  readonly contratistas: readonly ContratistaRespuesta[];
  readonly guardando: boolean;
  readonly onCerrar: () => void;
  readonly onGuardar: (datos: Trato) => void;
}) {
  const [contratistaId, setContratistaId] = useState(frente.contratista_id ?? '');
  // El pico sugerido es el punto de partida, no la respuesta: se propone
  // redondeado hacia arriba —una cuadrilla y media no se contrata— y quien
  // conoce al contratista lo corrige.
  const [cuadrillas, setCuadrillas] = useState(
    String(frente.cuadrillas_plan ?? Math.ceil(frente.pico_cuadrillas)),
  );
  const [notas, setNotas] = useState(frente.notas ?? '');

  return (
    <Modal titulo={`${frente.frente_clave} · ${frente.frente_nombre}`} onCerrar={onCerrar}>
      <div className="sheet__body">
        <p className="text-mute text-sm">
          El cálculo pide <strong>{fmtNum(frente.pico_cuadrillas)}</strong>{' '}
          cuadrilla(s) en su semana más cargada, sobre{' '}
          {fmtNum(frente.total_jornadas)} jornada(s). Es una sugerencia a partir
          del rendimiento del catálogo; la decisión es tuya.
        </p>

        <div className="field">
          <label className="field__label" htmlFor="contratista">
            Contratista
          </label>
          <select
            id="contratista"
            className="select"
            value={contratistaId}
            onChange={(e) => setContratistaId(e.target.value)}
          >
            <option value="">Todavía sin definir</option>
            {contratistas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.clave} · {c.razon_social}
              </option>
            ))}
          </select>
          <span className="field__hint">
            Se puede planear antes de saber quién lo hace: es justo cuando se
            cotiza.
          </span>
        </div>

        <div className="field mt-8" style={{ maxWidth: 180 }}>
          <label className="field__label" htmlFor="cuadrillas">
            Cuadrillas planeadas
          </label>
          <input
            id="cuadrillas"
            className="input"
            type="number"
            min={0}
            value={cuadrillas}
            onChange={(e) => setCuadrillas(e.target.value)}
          />
        </div>

        <div className="field mt-8">
          <label className="field__label" htmlFor="notas">
            Notas
          </label>
          <textarea
            id="notas"
            className="input"
            rows={3}
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            placeholder="Lo acordado, el precio, el plazo…"
          />
        </div>
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={guardando}
          onClick={() =>
            onGuardar({
              // Los tres se mandan aunque vengan vacíos: quitar el contratista
              // —"ya no sé quién lo lleva"— es un cambio tan válido como
              // ponerlo, y omitirlos lo dejaría como estaba.
              contratista_id: contratistaId === '' ? null : contratistaId,
              cuadrillas_plan: cuadrillas === '' ? null : Number(cuadrillas),
              notas: notas.trim() === '' ? null : notas.trim(),
            })
          }
        >
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </Modal>
  );
}
