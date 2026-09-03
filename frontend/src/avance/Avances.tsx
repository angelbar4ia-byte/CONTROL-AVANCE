/**
 * Avances del día — la obra del residente, agrupada como la recorre (§11.2, §7.4).
 *
 * Rol: Residente. Ruta `/avances`.
 *
 * ## Lo que cambió
 *
 * Esta pantalla pedía **pegar un UUID a mano** para capturar avance: el
 * contrato no exponía de dónde sacar la lista. Ahora
 * `GET /obras/{id}/actividades` trae la jerarquía resuelta y la captura se
 * hace sobre el renglón, que es lo que el residente tiene delante.
 *
 * ## Frente y sub-frente
 *
 * El **frente** es el nivel —cimentación, planta baja, azotea— y el
 * **sub-frente** la etapa. Es el orden en que se recorre la obra, no el de la
 * base: se abre planta baja, se abre albañilería, y ahí están las actividades.
 *
 * Se captura por renglón pero se **agrupa por sub-frente** porque es donde
 * pasan las cosas juntas: si se atrasó la albañilería de planta baja, se
 * atrasaron sus tres actividades, no una.
 *
 * ## Las vistas no son estatus
 *
 * "Activas", "listas p/ cierre", "retrasadas" son **preguntas** del día. Un
 * estatus suelto no contesta ninguna —`casi` está en activas y en listas— y
 * traducir de estatus a pregunta es el trabajo que esta pantalla le quita.
 */

import { useMemo, useState } from 'react';

import { useCapturarAvanceApiV1ActividadesActividadIdAvancePatch } from '@/api/generado/avance/avance';
import { useActividadesDeObraApiV1ObrasObraIdActividadesGet } from '@/api/generado/torre/torre';
import type { ActividadRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { colorAvance, fmtFecha, fmtNum, fmtPct } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { SelectorObra } from '@/lib/SelectorObra';
import {
  advertenciasAvance,
  contarPorVista,
  enVista,
  frentesDe,
  porSubFrente,
  tonoEstatusActividad,
  VISTAS,
  type Vista,
} from './reglas';

export default function Avances() {
  const [obraId, setObraId] = useState('');
  const [vista, setVista] = useState<Vista>('activas');
  const [frenteId, setFrenteId] = useState('');
  const [texto, setTexto] = useState('');
  const [capturando, setCapturando] = useState<ActividadRespuesta | null>(null);
  const [error, setError] = useState<string | null>(null);

  const consulta = useActividadesDeObraApiV1ObrasObraIdActividadesGet<
    ActividadRespuesta[],
    ErrorApi
  >(obraId, undefined, { query: { enabled: obraId !== '' } });

  const capturar = useCapturarAvanceApiV1ActividadesActividadIdAvancePatch<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setCapturando(null);
        setError(null);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
  });

  const actividades = useMemo(() => consulta.data ?? [], [consulta.data]);
  const cuenta = useMemo(() => contarPorVista(actividades), [actividades]);
  const frentes = useMemo(() => frentesDe(actividades), [actividades]);

  const visibles = useMemo(() => {
    const busqueda = texto.trim().toLowerCase();
    return actividades.filter(
      (a) =>
        enVista(a, vista) &&
        (frenteId === '' || a.nivel_id === frenteId) &&
        (busqueda === '' ||
          (a.concepto_clave ?? '').toLowerCase().includes(busqueda) ||
          (a.descripcion ?? '').toLowerCase().includes(busqueda)),
    );
  }, [actividades, vista, frenteId, texto]);

  const grupos = useMemo(() => porSubFrente(visibles), [visibles]);

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Mi trabajo</div>
          <h1 className="page__title">Avances del día</h1>
          <div className="page__subtitle">
            Tu obra agrupada como la recorres: el <strong>frente</strong> es el
            nivel y el <strong>sub-frente</strong> la etapa. Captura sobre el
            renglón; lo que se atrasa se atrasa por sub-frente, no de a una.
          </div>
        </div>
      </div>

      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}
      {error && <ErrorBanner mensaje={error} />}

      <div className="filterbar">
        <div style={{ minWidth: 260 }}>
          <SelectorObra
            id="obra"
            etiqueta="Obra"
            valor={obraId}
            onCambio={(id) => {
              setObraId(id);
              setFrenteId('');
            }}
          />
        </div>

        <div className="field" style={{ minWidth: 220 }}>
          <label className="field__label" htmlFor="frente">
            Frente
          </label>
          <select
            id="frente"
            className="select"
            value={frenteId}
            onChange={(e) => setFrenteId(e.target.value)}
          >
            <option value="">Todos los frentes</option>
            {frentes.map((frente) => (
              <option key={frente.clave} value={frente.clave}>
                {frente.etiqueta} ({frente.actividades})
              </option>
            ))}
          </select>
        </div>

        <div className="field" style={{ minWidth: 240 }}>
          <label className="field__label" htmlFor="buscar">
            Buscar
          </label>
          <input
            id="buscar"
            className="input"
            type="search"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Clave o descripción…"
          />
        </div>
      </div>

      {obraId !== '' && (
        <div className="tabs mb-8" role="tablist" aria-label="Vistas del día">
          {VISTAS.map((opcion) => (
            <button
              key={opcion.clave}
              type="button"
              role="tab"
              aria-selected={vista === opcion.clave}
              className={`tabs__tab${vista === opcion.clave ? ' is-active' : ''}`}
              onClick={() => setVista(opcion.clave)}
            >
              {opcion.etiqueta}{' '}
              <span className="text-mute tnum">{cuenta[opcion.clave]}</span>
            </button>
          ))}
        </div>
      )}

      {obraId === '' ? (
        <div className="empty">
          <div className="empty-title">Elige tu obra</div>
          <div className="empty-sub">
            La captura del día es de una obra: es donde estás parado.
          </div>
        </div>
      ) : consulta.isLoading ? (
        <div className="text-mute text-sm" style={{ padding: 24 }}>
          Cargando…
        </div>
      ) : visibles.length === 0 ? (
        <div className="empty">
          <div className="empty-title">Nada en esta vista</div>
          <div className="empty-sub">
            {actividades.length === 0
              ? 'La obra todavía no tiene actividades: falta generarla o aplicarle el programa base.'
              : 'Cambia de vista o quita el filtro de frente.'}
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <div className="table-scroll">
            <table className="table" style={{ minWidth: 'max-content' }}>
              <thead>
                <tr>
                  <th style={{ minWidth: 120 }}>Clave</th>
                  <th style={{ minWidth: 260 }}>Descripción</th>
                  <th style={{ minWidth: 64 }}>Unid.</th>
                  <th className="is-num" style={{ minWidth: 88 }}>
                    Base
                  </th>
                  <th className="is-num" style={{ minWidth: 100 }}>
                    Programada
                  </th>
                  <th className="is-num" style={{ minWidth: 100 }}>
                    Ejecutada
                  </th>
                  <th style={{ minWidth: 130 }}>Avance</th>
                  <th style={{ minWidth: 110 }}>Estatus</th>
                  <th style={{ minWidth: 100 }}>Inicio</th>
                  <th className="cell-actions" />
                </tr>
              </thead>
              <tbody>
                {grupos.map((grupo) => (
                  <FilasDelSubFrente
                    key={grupo.clave}
                    grupo={grupo}
                    onCapturar={setCapturando}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {visibles.length > 0 && (
        <div className="field__hint mt-8">
          {visibles.length} de {actividades.length} actividad(es), en{' '}
          {grupos.length} sub-frente(s).
        </div>
      )}

      {capturando !== null && (
        <FormularioDeCaptura
          actividad={capturando}
          guardando={capturar.isPending}
          onCerrar={() => setCapturando(null)}
          onGuardar={(datos) =>
            capturar.mutate({ actividadId: capturando.id, data: datos })
          }
        />
      )}
    </div>
  );
}

function FilasDelSubFrente({
  grupo,
  onCapturar,
}: {
  readonly grupo: { readonly etiqueta: string; readonly actividades: readonly ActividadRespuesta[] };
  readonly onCapturar: (actividad: ActividadRespuesta) => void;
}) {
  const primera = grupo.actividades[0];
  return (
    <>
      <tr style={{ background: 'var(--c-panel-2)' }}>
        <td colSpan={10}>
          <span className="text-xs text-mute mono">
            {primera?.nivel_descripcion ?? 'Sin frente'}
          </span>{' '}
          <strong>{grupo.etiqueta}</strong>{' '}
          <span className="text-mute text-xs">
            {grupo.actividades.length} actividad(es)
          </span>
        </td>
      </tr>
      {grupo.actividades.map((actividad) => (
        <FilaActividad
          key={actividad.id}
          actividad={actividad}
          onCapturar={onCapturar}
        />
      ))}
    </>
  );
}

function FilaActividad({
  actividad,
  onCapturar,
}: {
  readonly actividad: ActividadRespuesta;
  readonly onCapturar: (actividad: ActividadRespuesta) => void;
}) {
  const pct = Number(actividad.avance_pct);
  return (
    <tr>
      <td className="mono text-xs">
        {actividad.extra && <span className="badge badge--outline">EXT</span>}{' '}
        {actividad.concepto_clave ?? '—'}
      </td>
      <td>{actividad.descripcion}</td>
      <td className="mono text-xs">{actividad.unidad ?? '—'}</td>
      <td className="is-num tnum">{fmtNum(actividad.cant_base)}</td>
      <td className="is-num tnum">{fmtNum(actividad.cant_programada)}</td>
      <td className="is-num tnum">{fmtNum(actividad.cant_ejecutada)}</td>
      <td>
        <div className="row gap-4" style={{ alignItems: 'center' }}>
          <div
            className={`bar ${colorAvance(pct) !== 'accent' ? `bar--${colorAvance(pct)}` : ''}`}
            style={{ flex: 1, minWidth: 60 }}
          >
            <div
              className="bar__fill"
              style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
            />
          </div>
          <span className="text-xs tnum">{fmtPct(actividad.avance_pct)}</span>
        </div>
      </td>
      <td>
        <span className={`badge badge--${tonoEstatusActividad(actividad.estatus)}`}>
          {actividad.estatus.replace('_', ' ')}
        </span>
        {actividad.bloqueada && (
          <span className="badge badge--danger" title="Bloqueada por una incidencia">
            bloqueada
          </span>
        )}
      </td>
      <td className="text-xs">{fmtFecha(actividad.fecha_inicio)}</td>
      <td className="cell-actions">
        <button
          type="button"
          className="btn btn--sm"
          // Una actividad bloqueada por una incidencia que detiene no acepta
          // captura (§6): el backend responde 409 y ofrecerlo sería prometer
          // algo que va a fallar.
          disabled={actividad.bloqueada}
          title={
            actividad.bloqueada
              ? 'Bloqueada por una incidencia que detiene el programa'
              : 'Capturar avance'
          }
          onClick={() => onCapturar(actividad)}
        >
          Capturar
        </button>
      </td>
    </tr>
  );
}

/**
 * Capturar avance de una actividad concreta.
 *
 * Sobre el renglón y no en un formulario aparte: el residente ya tiene la
 * actividad delante y la cantidad base a la vista, así que las advertencias del
 * §6 se pueden mostrar **mientras escribe** en vez de descubrirse cuando el
 * backend rechaza. Antes esa comprobación era imposible: la pantalla no conocía
 * la cantidad base hasta después de la primera captura.
 */
function FormularioDeCaptura({
  actividad,
  guardando,
  onCerrar,
  onGuardar,
}: {
  readonly actividad: ActividadRespuesta;
  readonly guardando: boolean;
  readonly onCerrar: () => void;
  readonly onGuardar: (datos: {
    cant_ejecutada: number;
    cant_programada?: number;
    fecha?: string;
  }) => void;
}) {
  const [ejecutada, setEjecutada] = useState(String(actividad.cant_ejecutada));
  const [programada, setProgramada] = useState(String(actividad.cant_programada));
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10));

  const advertencias = advertenciasAvance({
    cantBase: Number(actividad.cant_base),
    cantProgramada: programada.trim() === '' ? null : Number(programada),
    cantEjecutada: ejecutada.trim() === '' ? null : Number(ejecutada),
  });

  const valido =
    ejecutada.trim() !== '' &&
    !Number.isNaN(Number(ejecutada)) &&
    !advertencias.cantEjecutadaExcedeProgramada &&
    !advertencias.cantProgramadaExcedeBase;

  return (
    <Modal
      titulo={`${actividad.concepto_clave ?? 'EXT'} · ${actividad.descripcion ?? ''}`}
      onCerrar={onCerrar}
    >
      <div className="sheet__body">
        <p className="text-mute text-sm">
          {actividad.nivel_descripcion} · {actividad.etapa_descripcion} ·{' '}
          base {fmtNum(actividad.cant_base)} {actividad.unidad ?? ''}
        </p>

        <div className="row gap-8">
          <div className="field" style={{ maxWidth: 160 }}>
            <label className="field__label" htmlFor="programada">
              Programada
            </label>
            <input
              id="programada"
              className="input"
              type="number"
              min={0}
              step="any"
              value={programada}
              onChange={(e) => setProgramada(e.target.value)}
            />
          </div>
          <div className="field" style={{ maxWidth: 160 }}>
            <label className="field__label" htmlFor="ejecutada">
              Ejecutada
            </label>
            <input
              id="ejecutada"
              className="input"
              type="number"
              min={0}
              step="any"
              value={ejecutada}
              onChange={(e) => setEjecutada(e.target.value)}
            />
          </div>
          <div className="field" style={{ maxWidth: 170 }}>
            <label className="field__label" htmlFor="fecha">
              Fecha
            </label>
            <input
              id="fecha"
              className="input"
              type="date"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </div>
        </div>

        {advertencias.cantProgramadaExcedeBase && (
          <div className="mt-8" role="status">
            <span className="badge badge--warn">Ojo</span> La programada pasa el
            tope de 20% sobre la base ({fmtNum(actividad.cant_base)}). Eso es un
            control de cambio: pídelo a Control de obra.
          </div>
        )}
        {advertencias.cantEjecutadaExcedeProgramada && (
          <div className="mt-8" role="status">
            <span className="badge badge--danger">No</span> No puedes ejecutar
            más de lo programado. Sube primero la programada.
          </div>
        )}
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!valido || guardando}
          onClick={() =>
            onGuardar({
              cant_ejecutada: Number(ejecutada),
              cant_programada:
                programada.trim() === '' ? undefined : Number(programada),
              fecha,
            })
          }
        >
          {guardando ? 'Guardando…' : 'Guardar avance'}
        </button>
      </div>
    </Modal>
  );
}
