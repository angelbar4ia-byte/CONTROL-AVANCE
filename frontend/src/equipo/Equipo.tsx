/**
 * Equipo — el directorio de la organización (§5.1, §11.2 "Identidad").
 *
 * Es lo que desbloquea el piloto: hasta ahora dar de alta a alguien exigía
 * insertar filas en SQL, y la pantalla de Login lleva prometiendo desde la
 * Fase 1 que «el alta de usuarios la realiza Control de obra».
 *
 * Pantalla compartida (§5.3): la lista la ve cualquier rol —saber quién es el
 * residente de una obra no es información privilegiada, y RLS ya la acota a la
 * organización del token—; el alta y la edición son de Control de obra y Super
 * intendente.
 */

import { useState } from 'react';

import { useListarUsuariosApiV1UsuariosGet } from '@/api/generado/usuarios/usuarios';
import type { UsuarioRespuesta } from '@/api/generado/modelo';
import { useSesion } from '@/app/sesion';
import { AltaUsuario } from './AltaUsuario';
import { PanelUsuario } from './PanelUsuario';
import { ROLES, administraEquipo, etiquetaRol, tonoRol } from './reglas';

export default function Equipo() {
  const { sesion } = useSesion();
  const [rol, setRol] = useState<string>('todos');
  const [abriendoAlta, setAbriendoAlta] = useState(false);
  const [seleccionado, setSeleccionado] = useState<UsuarioRespuesta | null>(null);

  const consulta = useListarUsuariosApiV1UsuariosGet(
    rol === 'todos' ? undefined : { rol: rol as never },
  );

  if (!sesion) return null;

  const administra = administraEquipo(sesion.rol);
  const filas = consulta.data ?? [];

  // El contrato no publica `GET /usuarios/{id}`: tras editar se recarga la
  // lista y el cajón se recupera de ella, igual que en Evaluaciones.
  const abierto =
    seleccionado === null
      ? null
      : (filas.find((u) => u.id === seleccionado.id) ?? seleccionado);

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Equipo</div>
          <h1 className="page__title">Usuarios</h1>
          <div className="page__subtitle">
            Quién trabaja en esta organización y con qué rol (§4). El alta crea
            también su cuenta de acceso con una contraseña temporal que la
            persona cambia al entrar.
          </div>
        </div>
        {administra && (
          <div className="page__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setAbriendoAlta(true)}
            >
              Dar de alta
            </button>
          </div>
        )}
      </div>

      <div className="filterbar">
        <div className="tabs">
          <button
            type="button"
            className={`tabs__tab ${rol === 'todos' ? 'is-active' : ''}`}
            onClick={() => setRol('todos')}
          >
            Todos
          </button>
          {ROLES.map((r) => (
            <button
              key={r}
              type="button"
              className={`tabs__tab ${rol === r ? 'is-active' : ''}`}
              onClick={() => setRol(r)}
            >
              {etiquetaRol(r)}
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Correo</th>
                <th>Rol</th>
                <th>Teléfono</th>
                <th>Estado</th>
                <th className="cell-actions">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={6}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : filas.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      No hay usuarios en este filtro.
                    </div>
                  </td>
                </tr>
              ) : (
                filas.map((usuario) => (
                  <tr
                    key={usuario.id}
                    className={usuario.estatus === 'activo' ? '' : 'is-muted'}
                  >
                    <td className="is-key">{usuario.nombre}</td>
                    <td>{usuario.email}</td>
                    <td>
                      <span className={`badge badge--${tonoRol(usuario.rol)}`}>
                        {etiquetaRol(usuario.rol)}
                      </span>
                    </td>
                    <td className="mono">{usuario.telefono ?? '—'}</td>
                    <td>
                      <div className="row gap-4">
                        {usuario.estatus !== 'activo' && (
                          <span className="badge badge--danger">Inactivo</span>
                        )}
                        {/* Sin cuenta ligada: aparece en el equipo, se le
                            asignan obras y no puede iniciar sesión. Es el
                            síntoma de un alta que quedó a medias, y por eso se
                            muestra en vez de esconderse. */}
                        {!usuario.puede_entrar && (
                          <span className="badge badge--danger">No puede entrar</span>
                        )}
                        {usuario.debe_cambiar_password && (
                          <span className="badge badge--warn">Contraseña temporal</span>
                        )}
                        {usuario.estatus === 'activo' &&
                          usuario.puede_entrar &&
                          !usuario.debe_cambiar_password && (
                            <span className="text-mute text-sm">Activo</span>
                          )}
                      </div>
                    </td>
                    <td className="cell-actions">
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={() => setSeleccionado(usuario)}
                      >
                        Abrir
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {abriendoAlta && (
        <AltaUsuario
          rolPropio={sesion.rol}
          onCerrar={() => setAbriendoAlta(false)}
          onCreado={() => {
            setAbriendoAlta(false);
            void consulta.refetch();
          }}
        />
      )}

      {abierto && (
        <PanelUsuario
          usuario={abierto}
          rolPropio={sesion.rol}
          usuarioIdPropio={sesion.usuarioId}
          onCerrar={() => setSeleccionado(null)}
          onCambiado={() => void consulta.refetch()}
        />
      )}
    </div>
  );
}
