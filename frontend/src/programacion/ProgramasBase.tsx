/**
 * Programas base de duraciones (§7.5, §11.2 `GET/POST /programas-base` y
 * `GET /programas-base/{id}/items`).
 *
 * Montada en `/config/programas-base`, la entrada "Programas base" del
 * sidebar de Control de obra (§5.1). Todo el bloque es (C) en el contrato, y
 * el backend lo exige con `exigir_rol(Rol.CONTROL_OBRA)`; a cualquier otro
 * rol se le explica en vez de dejarlo chocar contra un 403.
 *
 * Es la plantilla que se baja a las obras. Se puede hacer de dos maneras y las
 * dos existen a propósito: una obra suelta desde la pantalla de Programación
 * (`POST /obras/{id}/programa`, `InstanciarPrograma.tsx`), o el renglón
 * completo a las obras de su prototipo desde aquí
 * (`POST /programas-base/{id}/replicar`, `ReplicarPrograma.tsx`) — que es el
 * gesto normal en vivienda en serie, donde 40 casas comparten modelo.
 */

import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import {
  useListarItemsProgramaBaseApiV1ProgramasBaseProgramaBaseIdItemsGet,
  useListarProgramasBaseApiV1ProgramasBaseGet,
} from '@/api/generado/programacion/programacion';
import { usePresupuestoDePrototipoApiV1PrototiposPrototipoIdPresupuestoGet } from '@/api/generado/presupuesto/presupuesto';
import {
  useListarFrentesApiV1FrentesGet,
  useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet,
  useListarPrototiposApiV1PrototiposGet,
} from '@/api/generado/proyectos/proyectos';
import type {
  FrenteRespuesta,
  ItemProgramaBaseRespuesta,
  NodoPrototipoRespuesta,
  PresupuestoRespuesta,
  ProgramaBaseRespuesta,
  PrototipoRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtNum } from '@/lib/formato';
import { ArbolPrototipo } from '@/proyectos/ArbolPrototipo';
import { armarArbolPrototipo, type NodoArbolPrototipo } from '@/proyectos/nodosPrototipo';
import { AltaProgramaBase } from './AltaProgramaBase';
import { ReplicarPrograma } from './ReplicarPrograma';
import { etiquetaTipoDependencia, puedeAdministrarProgramasBase } from './reglas';

export default function ProgramasBase() {
  const { sesion } = useSesion();
  const rol = sesion?.rol ?? null;
  const administra = rol !== null && puedeAdministrarProgramasBase(rol);

  const [prototipoId, setPrototipoId] = useState('');
  const [soloVigentes, setSoloVigentes] = useState(false);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [alta, setAlta] = useState(false);
  const [replicando, setReplicando] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const prototiposQ = useListarPrototiposApiV1PrototiposGet<PrototipoRespuesta[], ErrorApi>(
    {},
    { query: { enabled: administra } },
  );

  const frentesQ = useListarFrentesApiV1FrentesGet<FrenteRespuesta[], ErrorApi>(
    {},
    { query: { enabled: administra } },
  );

  const basesQ = useListarProgramasBaseApiV1ProgramasBaseGet<ProgramaBaseRespuesta[], ErrorApi>(
    {
      prototipo_id: prototipoId === '' ? undefined : prototipoId,
      solo_vigentes: soloVigentes,
    },
    { query: { enabled: administra } },
  );

  const prototipos = useMemo(() => prototiposQ.data ?? [], [prototiposQ.data]);
  const bases = useMemo(() => basesQ.data ?? [], [basesQ.data]);
  const frentes = useMemo(() => frentesQ.data ?? [], [frentesQ.data]);

  const itemsQ = useListarItemsProgramaBaseApiV1ProgramasBaseProgramaBaseIdItemsGet<
    ItemProgramaBaseRespuesta[],
    ErrorApi
  >(abierto ?? '', { query: { enabled: abierto !== null } });

  const baseAbierta = useMemo(() => bases.find((base) => base.id === abierto) ?? null, [bases, abierto]);

  const baseAReplicar = useMemo(
    () => bases.find((base) => base.id === replicando) ?? null,
    [bases, replicando],
  );
  const prototipoAReplicar = useMemo(
    () => prototipos.find((p) => p.id === baseAReplicar?.prototipo_id) ?? null,
    [prototipos, baseAReplicar],
  );

  const nodosQ = useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet<
    NodoPrototipoRespuesta[],
    ErrorApi
  >(baseAbierta?.prototipo_id ?? '', { query: { enabled: baseAbierta !== null } });

  const presupuestoQ = usePresupuestoDePrototipoApiV1PrototiposPrototipoIdPresupuestoGet<
    PresupuestoRespuesta,
    ErrorApi
  >(baseAbierta?.prototipo_id ?? '', {
    query: { enabled: baseAbierta !== null, retry: false },
  });

  const items = useMemo(() => itemsQ.data ?? [], [itemsQ.data]);

  const prototipoAbierto = useMemo(
    () => prototipos.find((prototipo) => prototipo.id === baseAbierta?.prototipo_id) ?? null,
    [prototipos, baseAbierta],
  );
  const arbol = useMemo(
    () =>
      prototipoAbierto ? armarArbolPrototipo(prototipoAbierto, nodosQ.data ?? []) : null,
    [prototipoAbierto, nodosQ.data],
  );

  const itemPorNodo = useMemo(() => {
    const mapa = new Map<string, ItemProgramaBaseRespuesta>();
    for (const item of items) {
      if (item.prototipo_nodo_id) mapa.set(item.prototipo_nodo_id, item);
    }
    return mapa;
  }, [items]);

  // Renglones que no se pueden colgar del árbol —sin `prototipo_nodo_id`, o
  // apuntando a un nodo que ya no está en su prototipo— para no perderlos de
  // la vista en vez de dejarlos desaparecer en silencio.
  const itemsSinNodo = useMemo(() => {
    const idsDelArbol = new Set((nodosQ.data ?? []).map((nodo) => nodo.id));
    return items.filter(
      (item) => !item.prototipo_nodo_id || !idsDelArbol.has(item.prototipo_nodo_id),
    );
  }, [items, nodosQ.data]);

  function renglonDeNodo(nodo: NodoArbolPrototipo): ReactNode {
    const item = itemPorNodo.get(nodo.id);
    if (!item) return null;
    const frente = frentes.find((f) => f.id === item.frente_id);
    const dependencias = item.dependencias
      .map(
        (dependencia) =>
          `${dependencia.ref.slice(0, 8)} (${etiquetaTipoDependencia(dependencia.tipo)}${
            (dependencia.lag_dias ?? 0) !== 0 ? `, lag ${dependencia.lag_dias}` : ''
          })`,
      )
      .join(' · ');
    return (
      <>
        <span className="tree__meta tnum" title="Duración (días)">
          {fmtNum(item.duracion_dias)} d
        </span>
        {frente && (
          <span className="badge badge--outline" title={`${frente.clave} · ${frente.nombre}`}>
            {frente.clave}
          </span>
        )}
        {item.dependencias.length > 0 && (
          <span className="badge badge--outline" title={dependencias}>
            {item.dependencias.length} dep.
          </span>
        )}
      </>
    );
  }

  if (!sesion || rol === null) return null;

  if (!administra) {
    return (
      <div className="page">
        <div className="page__header">
          <div className="page__titlewrap">
            <div className="page__eyebrow mono">Configuración</div>
            <h1 className="page__title">Programas base</h1>
          </div>
        </div>
        <div className="text-mute text-sm" style={{ padding: '24px 12px' }}>
          Los programas base de duraciones los administra Control de obra (§11.2).
        </div>
      </div>
    );
  }

  // Un prototipo sin presupuesto cargado todavía responde 404: no es un
  // error, es el estado normal antes de la primera carga de ingeniería
  // (§10) — el árbol se ve igual, solo sin unidad/PU/importe.
  const errores = [
    prototiposQ.error,
    basesQ.error,
    itemsQ.error,
    nodosQ.error,
    presupuestoQ.error,
  ].filter(
    (error): error is ErrorApi => error !== null && error !== undefined && error.status !== 404,
  );

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Configuración</div>
          <h1 className="page__title">Programas base</h1>
          <div className="page__subtitle">
            Plantilla de duraciones y precedencias por prototipo (§7.5). Se replica a las
            obras del prototipo desde aquí, o a una obra suelta desde Ruta crítica →
            Instanciar programa.
          </div>
        </div>
        <div className="page__actions">
          {/* El canvas es el camino normal para armar un programa completo; el
              formulario se queda para el alta de pocos renglones y para
              capturar sin ratón. Necesita un prototipo: el editor se monta
              sobre el árbol WBS de uno concreto (§7.4). */}
          <Link
            className={`btn btn--accent${prototipoId === '' ? ' btn--ghost' : ''}`}
            to={`/config/programas-base/editor?prototipo=${prototipoId}`}
            aria-disabled={prototipoId === ''}
            onClick={(evento) => {
              if (prototipoId === '') {
                evento.preventDefault();
                setAviso('Elige un prototipo para abrir su editor gráfico.');
              }
            }}
            title="Nodos y cables sobre el árbol WBS del prototipo"
          >
            Editor gráfico
          </Link>
          <button type="button" className="btn btn--primary" onClick={() => setAlta(true)}>
            Nuevo programa base
          </button>
        </div>
      </div>

      {aviso !== null && (
        <div className="mb-8" role="status">
          <span className="badge badge--ok">{aviso}</span>
        </div>
      )}

      {errores.map((error, indice) => (
        <div className="mb-8" key={`${error.status}-${indice}`}>
          <ErrorBanner mensaje={error.message} />
        </div>
      ))}

      <div className="filterbar">
        <select
          className="select"
          value={prototipoId}
          onChange={(e) => {
            setPrototipoId(e.target.value);
            setAbierto(null);
          }}
          aria-label="Filtrar por prototipo"
        >
          <option value="">Todos los prototipos</option>
          {prototipos.map((prototipo) => (
            <option key={prototipo.id} value={prototipo.id}>
              {prototipo.clave} · {prototipo.nombre}
            </option>
          ))}
        </select>

        <label className="row gap-4" style={{ alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={soloVigentes}
            onChange={(e) => setSoloVigentes(e.target.checked)}
          />
          <span className="text-sm text-mute">Solo la versión vigente</span>
        </label>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Programa</th>
                <th>Prototipo</th>
                <th className="is-num">Versión</th>
                <th>Estado</th>
                <th>Renglones</th>
                <th>Editor</th>
                <th>Obras</th>
              </tr>
            </thead>
            <tbody>
              {basesQ.isLoading ? (
                <tr>
                  <td colSpan={7}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : bases.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    {/* Un prototipo sin programa base no es un callejón: su
                        árbol WBS ya trae las etapas y los conceptos, y el
                        canvas arranca desde ahí con las duraciones por llenar
                        (§7.4). */}
                    <div className="empty">
                      <div className="empty-title">
                        {prototipoId === ''
                          ? 'No hay programas base con estos filtros.'
                          : 'Este prototipo todavía no tiene programa base.'}
                      </div>
                      <div className="empty-sub">
                        {prototipoId === ''
                          ? 'Elige un prototipo para armar el suyo desde su árbol WBS.'
                          : 'El editor gráfico arranca con una caja por etapa y por concepto de su árbol WBS, sin duración: capturar el programa es llenar duraciones y tender cables.'}
                      </div>
                      {prototipoId !== '' && (
                        <Link
                          className="btn btn--accent"
                          to={`/config/programas-base/editor?prototipo=${prototipoId}`}
                        >
                          Armar desde el árbol WBS
                        </Link>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                bases.map((base) => {
                  const prototipo = prototipos.find((p) => p.id === base.prototipo_id);
                  return (
                    <tr key={base.id}>
                      <td className="is-key">{base.nombre ?? base.id.slice(0, 8)}</td>
                      <td>
                        {prototipo ? `${prototipo.clave} · ${prototipo.nombre}` : base.prototipo_id}
                      </td>
                      <td className="is-num mono tnum">{base.version}</td>
                      <td>
                        <span className={`badge badge--${base.vigente ? 'ok' : 'outline'}`}>
                          {base.vigente ? 'Vigente' : 'Retirado'}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn btn--sm"
                          aria-expanded={abierto === base.id}
                          onClick={() => setAbierto(abierto === base.id ? null : base.id)}
                        >
                          {abierto === base.id ? 'Ocultar renglones' : 'Ver renglones'}
                        </button>
                      </td>
                      <td>
                        {/* Abrir una versión en el canvas no la modifica: se
                            carga como borrador y guardar crea la siguiente
                            (§7.5). Por eso también se puede abrir una retirada
                            para partir de ella. */}
                        <Link
                          className="btn btn--sm"
                          to={`/config/programas-base/editor?prototipo=${base.prototipo_id}&base=${base.id}`}
                          title="Abrir esta versión en el canvas; guardar crea la siguiente"
                        >
                          Abrir en canvas
                        </Link>
                      </td>
                      <td>
                        {/* Replicar solo tiene sentido desde la versión
                            vigente: la instanciación siempre baja esa (§7.5),
                            así que ofrecerlo sobre una retirada sería ofrecer
                            un 422. */}
                        <button
                          type="button"
                          className="btn btn--sm btn--accent"
                          disabled={!base.vigente}
                          title={
                            base.vigente
                              ? 'Bajar este programa a las obras de su prototipo'
                              : 'Solo se replica la versión vigente del prototipo (§7.5)'
                          }
                          onClick={() => setReplicando(base.id)}
                        >
                          Replicar a obras
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {abierto !== null && (
        <div className="table-wrap mt-16">
          {itemsQ.isLoading || nodosQ.isLoading ? (
            <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
              Cargando renglones…
            </div>
          ) : items.length === 0 ? (
            <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
              Este programa base no tiene renglones.
            </div>
          ) : (
            <>
              {/* Cada renglón cuelga de su nodo del árbol (nivel → etapa →
                  concepto, §7.4): es la misma estructura de Prototipos, con
                  duración/frente/dependencias superpuestos por
                  `prototipo_nodo_id`. */}
              {arbol && (
                <ArbolPrototipo
                  raiz={arbol}
                  presupuesto={presupuestoQ.data}
                  extra={renglonDeNodo}
                  expandirTodo
                />
              )}

              {itemsSinNodo.length > 0 && (
                <div className="mt-16">
                  <div className="text-mute text-xs" style={{ padding: '4px 8px' }}>
                    Renglones sin nodo del árbol ({itemsSinNodo.length}) — no están ligados a
                    ningún nivel/etapa/concepto del prototipo, o el nodo al que apuntaban ya no
                    existe:
                  </div>
                  <div className="table-scroll">
                    <table className="table">
                      <thead>
                        <tr>
                          <th className="is-num">Orden</th>
                          <th className="is-num">Duración (días)</th>
                          <th>Frente</th>
                          <th>Dependencias</th>
                        </tr>
                      </thead>
                      <tbody>
                        {itemsSinNodo.map((item) => {
                          const frente = frentes.find((f) => f.id === item.frente_id);
                          return (
                            <tr key={item.id}>
                              <td className="is-num mono tnum">{item.orden}</td>
                              <td className="is-num mono tnum">{fmtNum(item.duracion_dias)}</td>
                              <td>
                                {frente
                                  ? `${frente.clave} · ${frente.nombre}`
                                  : (item.frente_id ?? '—')}
                              </td>
                              <td className="text-xs">
                                {item.dependencias.length === 0
                                  ? '—'
                                  : item.dependencias
                                      .map(
                                        (dependencia) =>
                                          `${dependencia.ref.slice(0, 8)} (${etiquetaTipoDependencia(dependencia.tipo)}${
                                            (dependencia.lag_dias ?? 0) !== 0
                                              ? `, lag ${dependencia.lag_dias}`
                                              : ''
                                          })`,
                                      )
                                      .join(' · ')}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {alta && (
        <AltaProgramaBase
          prototipos={prototipos}
          frentes={frentes}
          prototipoInicial={prototipoId === '' ? undefined : prototipoId}
          onCerrar={() => setAlta(false)}
          onCreado={(respuesta) => {
            setAlta(false);
            setAviso(
              `Programa base creado · versión ${respuesta.version} · ${respuesta.n_items} renglones`,
            );
            void basesQ.refetch();
          }}
        />
      )}

      {baseAReplicar !== null && (
        <ReplicarPrograma
          base={baseAReplicar}
          nombrePrototipo={
            prototipoAReplicar
              ? `${prototipoAReplicar.clave} · ${prototipoAReplicar.nombre}`
              : null
          }
          onCerrar={() => setReplicando(null)}
        />
      )}
    </div>
  );
}
