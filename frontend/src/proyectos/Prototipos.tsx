/**
 * Prototipos — catálogo de modelos de vivienda ya cargados (§7.2).
 *
 * Montada en `/config/prototipos`. Lista lo que trajo la carga masiva de
 * "Prototipos" (Cargas de datos, §10) o el alta individual de este mismo
 * módulo — las dos escriben la misma tabla `prototipo`, así que una sola
 * pantalla basta para ver el resultado de cualquiera de las dos.
 */

import { useMemo, useState } from 'react';

import { usePresupuestoDePrototipoApiV1PrototiposPrototipoIdPresupuestoGet } from '@/api/generado/presupuesto/presupuesto';
import {
  useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet,
  useListarPrototiposApiV1PrototiposGet,
  useListarProyectosApiV1ProyectosGet,
} from '@/api/generado/proyectos/proyectos';
import type {
  NodoPrototipoRespuesta,
  PresupuestoRespuesta,
  PrototipoRespuesta,
  ProyectoRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtNum } from '@/lib/formato';
import { AltaPrototipo } from './AltaPrototipo';
import { ArbolPrototipo } from './ArbolPrototipo';
import { CeldasNivelesYRecamaras } from './NivelesYRecamaras';
import { armarArbolPrototipo } from './nodosPrototipo';
import { puedeConfigurarEstructura } from './reglas';

export default function Prototipos() {
  const { sesion } = useSesion();
  const rol = sesion?.rol ?? null;
  const administra = rol !== null && puedeConfigurarEstructura(rol);

  const [proyectoId, setProyectoId] = useState('');
  const [alta, setAlta] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [arbolAbierto, setArbolAbierto] = useState<string | null>(null);

  const proyectosQ = useListarProyectosApiV1ProyectosGet<ProyectoRespuesta[], ErrorApi>({
    query: { enabled: administra },
  });

  const prototiposQ = useListarPrototiposApiV1PrototiposGet<PrototipoRespuesta[], ErrorApi>(
    { proyecto_id: proyectoId === '' ? undefined : proyectoId },
    { query: { enabled: administra } },
  );

  const nodosQ = useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet<
    NodoPrototipoRespuesta[],
    ErrorApi
  >(arbolAbierto ?? '', { query: { enabled: arbolAbierto !== null } });

  const presupuestoQ = usePresupuestoDePrototipoApiV1PrototiposPrototipoIdPresupuestoGet<
    PresupuestoRespuesta,
    ErrorApi
  >(arbolAbierto ?? '', {
    query: { enabled: arbolAbierto !== null, retry: false },
  });

  const proyectos = useMemo(() => proyectosQ.data ?? [], [proyectosQ.data]);
  const prototipos = useMemo(() => prototiposQ.data ?? [], [prototiposQ.data]);

  const prototipoAbierto = useMemo(
    () => prototipos.find((prototipo) => prototipo.id === arbolAbierto) ?? null,
    [prototipos, arbolAbierto],
  );
  const arbol = useMemo(
    () =>
      prototipoAbierto ? armarArbolPrototipo(prototipoAbierto, nodosQ.data ?? []) : null,
    [prototipoAbierto, nodosQ.data],
  );

  if (!sesion || rol === null) return null;

  if (!administra) {
    return (
      <div className="page">
        <div className="page__header">
          <div className="page__titlewrap">
            <div className="page__eyebrow mono">Configuración</div>
            <h1 className="page__title">Prototipos</h1>
          </div>
        </div>
        <div className="text-mute text-sm" style={{ padding: '24px 12px' }}>
          Los prototipos los administra Control de obra y Super intendente (§11.2).
        </div>
      </div>
    );
  }

  // Un prototipo sin presupuesto cargado todavía responde 404: no es un
  // error, es el estado normal antes de la primera carga de ingeniería
  // (§10) — el árbol lo muestra igual, solo sin unidad/PU/importe.
  const errores = [proyectosQ.error, prototiposQ.error, nodosQ.error, presupuestoQ.error].filter(
    (error): error is ErrorApi => error !== null && error !== undefined && error.status !== 404,
  );

  function proyectoDe(proyectoId: string | null | undefined): ProyectoRespuesta | undefined {
    return proyectoId ? proyectos.find((p) => p.id === proyectoId) : undefined;
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Configuración</div>
          <h1 className="page__title">Prototipos</h1>
          <div className="page__subtitle">
            Modelos de vivienda del proyecto (§7.2). Se dan de alta uno a uno
            aquí, o varios de golpe desde Cargas de datos.
          </div>
        </div>
        <div className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => setAlta(true)}>
            Nuevo prototipo
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
          value={proyectoId}
          onChange={(e) => {
            setProyectoId(e.target.value);
            setArbolAbierto(null);
          }}
          aria-label="Filtrar por proyecto"
        >
          <option value="">Todos los proyectos</option>
          {proyectos.map((proyecto) => (
            <option key={proyecto.id} value={proyecto.id}>
              {proyecto.clave} · {proyecto.nombre}
            </option>
          ))}
        </select>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Clave</th>
                <th>Nombre</th>
                <th>Proyecto</th>
                <th className="is-num">m²</th>
                <th className="is-num">Niveles</th>
                <th className="is-num">Recámaras</th>
                <th>Ingeniería</th>
              </tr>
            </thead>
            <tbody>
              {prototiposQ.isLoading ? (
                <tr>
                  <td colSpan={7}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : prototipos.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Todavía no hay prototipos con estos filtros.
                    </div>
                  </td>
                </tr>
              ) : (
                prototipos.map((prototipo) => {
                  const proyecto = proyectoDe(prototipo.proyecto_id);
                  return (
                    <tr key={prototipo.id}>
                      <td className="is-key mono">{prototipo.clave}</td>
                      <td>{prototipo.nombre}</td>
                      <td>
                        {proyecto
                          ? `${proyecto.clave} · ${proyecto.nombre}`
                          : (prototipo.proyecto_id ?? 'Todos los proyectos')}
                      </td>
                      <td className="is-num mono tnum">{fmtNum(prototipo.m2)}</td>
                      <CeldasNivelesYRecamaras prototipo={prototipo} editable={administra} />
                      <td>
                        <button
                          type="button"
                          className="btn btn--sm"
                          aria-expanded={arbolAbierto === prototipo.id}
                          onClick={() =>
                            setArbolAbierto(arbolAbierto === prototipo.id ? null : prototipo.id)
                          }
                        >
                          {arbolAbierto === prototipo.id ? 'Ocultar árbol' : 'Ver árbol'}
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

      {arbolAbierto !== null && (
        <div className="table-wrap mt-16">
          {nodosQ.isLoading ? (
            <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
              Cargando árbol…
            </div>
          ) : (
            arbol && <ArbolPrototipo raiz={arbol} presupuesto={presupuestoQ.data} expandirTodo />
          )}
        </div>
      )}

      {alta && (
        <AltaPrototipo
          proyectos={proyectos}
          proyectoInicial={proyectoId === '' ? undefined : proyectoId}
          onCerrar={() => setAlta(false)}
          onCreado={() => {
            setAlta(false);
            setAviso('Prototipo creado');
            void prototiposQ.refetch();
          }}
        />
      )}
    </div>
  );
}
