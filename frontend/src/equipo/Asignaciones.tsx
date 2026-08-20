/**
 * Asignaciones — repartir el alcance del §4.
 *
 * Spec §4 (alcance por rol) · §5.1 ("Equipo · Asignaciones") · §5.3 (pantalla
 * compartida) · §12.4 (RLS impone lo mismo).
 *
 * DOS PUENTES CON PERMISOS DISTINTOS, Y NO ES UN DESCUIDO
 *
 * · `supervisor_cluster` — clusters a un supervisor. Lo reparte Control de
 *   obra: es operación diaria.
 * · `control_proyecto` — proyectos a un Control de obra. **Solo** el Super
 *   intendente, porque ese puente decide el alcance de quien administra: si
 *   Control pudiera editarlo, se ampliaría el suyo.
 *
 * El residente no aparece en esta pantalla: llega a su obra por
 * `obra.residente_id`, que se asigna desde la obra (Creador de obra, §5.1).
 * Ofrecerle un cluster no le daría alcance, solo una fila que nadie lee.
 *
 * El Supervisor tiene esta entrada en su sidebar (§5.1) y la ve en **solo
 * lectura**: sirve para saber qué clusters le tocaron.
 */

import { useState } from 'react';

import {
  useAsignarAlcanceApiV1UsuariosUsuarioIdAlcancePost,
  useConsultarAlcanceApiV1UsuariosUsuarioIdAlcanceGet,
  useListarUsuariosApiV1UsuariosGet,
} from '@/api/generado/usuarios/usuarios';
import {
  useListarClustersApiV1ClustersGet,
  useListarProyectosApiV1ProyectosGet,
} from '@/api/generado/proyectos/proyectos';
import type {
  ClusterRespuesta,
  ProyectoRespuesta,
  UsuarioRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { etiquetaRol, puedeAsignarAlcanceDe, puenteDe, tonoRol } from './reglas';

export default function Asignaciones() {
  const { sesion } = useSesion();
  const [seleccionadoId, setSeleccionadoId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const usuariosQ = useListarUsuariosApiV1UsuariosGet<UsuarioRespuesta[], ErrorApi>();

  // Solo supervisores y controles: los otros dos roles no tienen puente. Es la
  // misma razón por la que `puenteDe` devuelve `null` para ellos.
  const conAlcance = (usuariosQ.data ?? []).filter(
    (u) => puenteDe(u.rol) !== null && u.estatus === 'activo',
  );

  const seleccionado =
    conAlcance.find((u) => u.id === seleccionadoId) ?? conAlcance[0] ?? null;

  if (!sesion) return null;

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Equipo</div>
          <h1 className="page__title">Asignaciones</h1>
          <div className="page__subtitle">
            Qué ve cada quien (§4): clusters para un supervisor, proyectos para
            un control de obra. El residente no aparece aquí — su alcance sale
            de la obra donde es residente.
          </div>
        </div>
      </div>

      {error && <ErrorBanner mensaje={error} />}

      <div className="split">
        <div className="split__list">
          <div className="list">
            {usuariosQ.isLoading ? (
              <div className="text-mute text-sm" style={{ padding: 16 }}>
                Cargando…
              </div>
            ) : conAlcance.length === 0 ? (
              <div className="empty">
                <div className="empty-title">Sin supervisores ni controles</div>
                <div className="empty-sub">
                  Da de alta a alguien con uno de esos dos roles en Equipo y
                  aparecerá aquí.
                </div>
              </div>
            ) : (
              conAlcance.map((usuario) => (
                <button
                  key={usuario.id}
                  type="button"
                  className={`list__item ${seleccionado?.id === usuario.id ? 'is-active' : ''}`}
                  onClick={() => {
                    setSeleccionadoId(usuario.id);
                    setError(null);
                  }}
                >
                  <div className="col gap-2" style={{ alignItems: 'flex-start' }}>
                    <span className="is-key">{usuario.nombre}</span>
                    <span className={`badge badge--${tonoRol(usuario.rol)}`}>
                      {etiquetaRol(usuario.rol)}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="split__detail">
          {seleccionado === null ? (
            <div className="empty">
              <div className="empty-title">Elige a alguien</div>
            </div>
          ) : (
            <PanelAlcance
              usuario={seleccionado}
              puedeEditar={puedeAsignarAlcanceDe(sesion.rol, seleccionado.rol)}
              onError={setError}
            />
          )}
        </div>
      </div>
    </div>
  );
}

interface PanelProps {
  readonly usuario: UsuarioRespuesta;
  readonly puedeEditar: boolean;
  readonly onError: (mensaje: string | null) => void;
}

function PanelAlcance({ usuario, puedeEditar, onError }: PanelProps) {
  const puente = puenteDe(usuario.rol);

  const alcanceQ = useConsultarAlcanceApiV1UsuariosUsuarioIdAlcanceGet(usuario.id);
  const clustersQ = useListarClustersApiV1ClustersGet<ClusterRespuesta[], ErrorApi>(
    undefined,
    { query: { enabled: puente === 'clusters' } },
  );
  const proyectosQ = useListarProyectosApiV1ProyectosGet<ProyectoRespuesta[], ErrorApi>(
    { query: { enabled: puente === 'proyectos' } },
  );

  const asignar = useAsignarAlcanceApiV1UsuariosUsuarioIdAlcancePost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        onError(null);
        void alcanceQ.refetch();
      },
      onError: (err) => onError(err.message),
    },
  });

  // `alcance` viene como `list[dict]` en el contrato —el backend devuelve las
  // filas del join tal cual—, así que aquí se estrecha a lo que la pantalla usa.
  const asignados = new Set(
    ((puente === 'clusters'
      ? alcanceQ.data?.clusters
      : alcanceQ.data?.proyectos) ?? []
    ).map((fila) => String((fila as { id: string }).id)),
  );

  const disponibles: readonly { id: string; clave: string; nombre: string }[] =
    puente === 'clusters' ? (clustersQ.data ?? []) : (proyectosQ.data ?? []);

  function alternar(id: string, estaAsignado: boolean) {
    asignar.mutate({
      usuarioId: usuario.id,
      data: {
        clusters: puente === 'clusters' ? [id] : [],
        proyectos: puente === 'proyectos' ? [id] : [],
        retirar: estaAsignado,
      },
    });
  }

  return (
    <div className="card">
      <div className="card__header">
        <div className="col gap-2" style={{ alignItems: 'flex-start' }}>
          <h2 className="card__title">{usuario.nombre}</h2>
          <div className="text-mute text-xs">
            {puente === 'clusters'
              ? 'Ve las obras de los clusters que tenga asignados (§4).'
              : 'Ve las obras de los proyectos que tenga asignados (§4).'}
          </div>
        </div>
      </div>
      <div className="card__body col gap-8">
        {!puedeEditar && (
          <div className="field__hint">
            {usuario.rol === 'control_obra'
              ? 'Solo un super intendente reparte proyectos: ese puente decide el alcance de quien administra (§4).'
              : 'Tu rol no reparte alcance (§5.1).'}
          </div>
        )}

        {alcanceQ.isLoading ? (
          <div className="text-mute text-sm">Cargando alcance…</div>
        ) : disponibles.length === 0 ? (
          <div className="text-mute text-sm">
            No hay {puente === 'clusters' ? 'clusters' : 'proyectos'} en tu
            alcance para asignar.
          </div>
        ) : (
          disponibles.map((item) => {
            const estaAsignado = asignados.has(item.id);
            return (
              <div key={item.id} className="row gap-8" style={{ alignItems: 'center' }}>
                <span className="is-key" style={{ minWidth: 120 }}>
                  {item.clave}
                </span>
                <span className="text-sm" style={{ flex: 1 }}>
                  {item.nombre}
                </span>
                {estaAsignado && <span className="badge badge--ok">Asignado</span>}
                <button
                  type="button"
                  className={`btn btn--sm ${estaAsignado ? '' : 'btn--primary'}`}
                  disabled={!puedeEditar || asignar.isPending}
                  onClick={() => alternar(item.id, estaAsignado)}
                >
                  {estaAsignado ? 'Retirar' : 'Asignar'}
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
