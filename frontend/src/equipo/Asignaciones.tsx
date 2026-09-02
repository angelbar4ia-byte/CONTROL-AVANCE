/**
 * Asignaciones — el organigrama del §4 (cadena de mando de la 0042).
 *
 * Spec §4 (alcance por rol) · §5.1 ("Equipo · Asignaciones") · §5.3 (pantalla
 * compartida) · §12.4 (RLS impone lo mismo).
 *
 * La cadena es Control de obra (raíz, ve toda la organización) → Super
 * intendente → Supervisor → Residente → Obras. Cada nivel tiene un puente
 * propio (`puenteDe`):
 *
 * · `gente` — a quién tiene a su cargo un super intendente o un supervisor
 *   (`superintendente_usuario` / `supervisor_residente`). Mover a alguien de
 *   jefe arrastra su cartera de obras con él.
 * · `obras` — las obras de un residente (`residente_obra`). Es lo que de
 *   verdad decide su alcance, y hacia arriba el de su supervisor y su super
 *   intendente.
 *
 * Control de obra no aparece en la lista: es la raíz, no cuelga de nadie y
 * no tiene puente que editar aquí.
 *
 * El Supervisor tiene esta entrada en su sidebar (§5.1) y la ve en **solo
 * lectura** cuando el objetivo no es su propia gente: sirve para saber qué
 * le tocó, no para tocar el alcance de otros.
 */

import { useState } from 'react';

import {
  useAsignarAlcanceApiV1UsuariosUsuarioIdAlcancePost,
  useConsultarAlcanceApiV1UsuariosUsuarioIdAlcanceGet,
  useListarUsuariosApiV1UsuariosGet,
} from '@/api/generado/usuarios/usuarios';
import { useListarObrasApiV1ObrasGet } from '@/api/generado/obras/obras';
import type { ObraRespuesta, UsuarioRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import {
  etiquetaRol,
  puedeAsignarAlcanceDe,
  puenteDe,
  rolesQueCuelganDe,
  tonoRol,
} from './reglas';

export default function Asignaciones() {
  const { sesion } = useSesion();
  const [seleccionadoId, setSeleccionadoId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const usuariosQ = useListarUsuariosApiV1UsuariosGet<UsuarioRespuesta[], ErrorApi>();

  // Solo quien cuelga de alguien en el organigrama: Control de obra es la
  // raíz y no tiene puente (misma razón por la que `puenteDe` le da `null`).
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
            El organigrama del §4: Control de obra → Super intendente →
            Supervisor → Residente → Obras. A un super intendente o un
            supervisor se le asigna la gente a su cargo; a un residente, sus
            obras — eso decide su alcance real, y el de su cadena hacia
            arriba.
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
                <div className="empty-title">Sin gente en el organigrama</div>
                <div className="empty-sub">
                  Da de alta a un super intendente, un supervisor o un
                  residente en Equipo y aparecerá aquí.
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
              usuarios={usuariosQ.data ?? []}
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
  readonly usuarios: readonly UsuarioRespuesta[];
  readonly puedeEditar: boolean;
  readonly onError: (mensaje: string | null) => void;
}

function PanelAlcance({ usuario, usuarios, puedeEditar, onError }: PanelProps) {
  const puente = puenteDe(usuario.rol);

  const alcanceQ = useConsultarAlcanceApiV1UsuariosUsuarioIdAlcanceGet(usuario.id);
  const obrasQ = useListarObrasApiV1ObrasGet<ObraRespuesta[], ErrorApi>(
    undefined,
    { query: { enabled: puente === 'obras' } },
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
    ((puente === 'gente' ? alcanceQ.data?.gente : alcanceQ.data?.obras) ?? []).map((fila) =>
      String((fila as { id: string }).id),
    ),
  );

  // Una obra puede llevar más de un residente, pero solo uno queda en
  // `obra.residente_id` —el que se eligió al crearla, o el relevo que dejó el
  // trigger de la 0042—. Distinguirlo importa: los repos y las notificaciones
  // leen esa columna, así que "asignado" y "principal" no son lo mismo.
  const principales = new Set(
    (alcanceQ.data?.obras ?? [])
      .filter((fila) => (fila as { es_principal?: boolean }).es_principal === true)
      .map((fila) => String((fila as { id: string }).id)),
  );

  const candidatosGente =
    puente === 'gente'
      ? usuarios.filter(
          (u) =>
            u.id !== usuario.id &&
            u.estatus === 'activo' &&
            rolesQueCuelganDe(usuario.rol as 'super_intendente' | 'supervisor').includes(
              u.rol as 'supervisor' | 'residente',
            ),
        )
      : [];

  const disponibles: readonly { id: string; etiqueta: string; sub: string }[] =
    puente === 'gente'
      ? candidatosGente.map((u) => ({ id: u.id, etiqueta: u.nombre, sub: etiquetaRol(u.rol) }))
      : (obrasQ.data ?? []).map((o) => ({
          id: o.id,
          etiqueta: o.clave,
          sub: o.estatus,
        }));

  function alternar(id: string, estaAsignado: boolean) {
    asignar.mutate({
      usuarioId: usuario.id,
      data: {
        gente: puente === 'gente' ? [id] : [],
        obras: puente === 'obras' ? [id] : [],
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
            {puente === 'gente'
              ? 'Ve las obras de toda la gente que tenga a su cargo, cadena hacia abajo (§4).'
              : 'Sus obras — lo que de verdad decide su alcance (§4).'}
          </div>
        </div>
      </div>
      <div className="card__body col gap-8">
        {!puedeEditar && (
          <div className="field__hint">Tu rol no reparte alcance para esta persona (§4).</div>
        )}

        {puente === 'obras' && (
          <div className="field__hint">
            «Principal» es el residente que quedó en la obra al crearla. Sumar a
            alguien aquí no lo destituye: la obra puede llevar varios residentes
            y el principal solo cambia si se le retira la obra o se le reasigna
            desde la obra misma.
          </div>
        )}

        {alcanceQ.isLoading ? (
          <div className="text-mute text-sm">Cargando alcance…</div>
        ) : disponibles.length === 0 ? (
          <div className="text-mute text-sm">
            No hay {puente === 'gente' ? 'gente disponible' : 'obras'} para asignar.
          </div>
        ) : (
          disponibles.map((item) => {
            const estaAsignado = asignados.has(item.id);
            return (
              <div key={item.id} className="row gap-8" style={{ alignItems: 'center' }}>
                <span className="is-key" style={{ minWidth: 120 }}>
                  {item.etiqueta}
                </span>
                <span className="text-sm" style={{ flex: 1 }}>
                  {item.sub}
                </span>
                {estaAsignado &&
                  (principales.has(item.id) ? (
                    <span className="badge badge--ok">Principal</span>
                  ) : (
                    <span className="badge badge--info">Asignado</span>
                  ))}
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
