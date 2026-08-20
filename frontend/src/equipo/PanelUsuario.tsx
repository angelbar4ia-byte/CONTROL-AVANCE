/**
 * Detalle de una persona del equipo: editar, cambiar rol, dar de baja y
 * resetear su contraseña (§5.1, §11.2).
 *
 * Las tres acciones peligrosas —cambiar rol, dar de baja, resetear
 * contraseña— viven aquí y no en la fila de la tabla, a propósito: en la tabla
 * bastaría un clic para degradar a alguien, y el sistema de diseño usa el
 * cajón justamente para el drill-down que exige mirar antes de tocar.
 *
 * Lo que esta pantalla **no** decide es quién puede hacer qué: `reglas.ts` es
 * un reflejo de UX para no ofrecer un botón que va a responder 403, y la
 * verdad vive en el dominio, en el trigger de la migración 0025 y en RLS.
 */

import { useMemo, useState } from 'react';

import {
  useActualizarUsuarioApiV1UsuariosUsuarioIdPatch,
  useResetearContrasenaApiV1UsuariosUsuarioIdContrasenaPost,
} from '@/api/generado/usuarios/usuarios';
import type { UsuarioRespuesta } from '@/api/generado/modelo';
import { claveDeIdempotencia, type ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import type { Rol } from '@/shell/navegacion';
import {
  cambiosDeUsuario,
  formularioDesdeUsuario,
  hayCambios,
  type FormularioUsuario,
} from './formulario';
import {
  LARGO_MINIMO_CONTRASENA,
  etiquetaRol,
  puedeEditar,
  rolesQuePuedeOtorgar,
  sugerirContrasena,
  tonoRol,
} from './reglas';

interface Props {
  readonly usuario: UsuarioRespuesta;
  readonly rolPropio: Rol;
  readonly usuarioIdPropio: string;
  readonly onCerrar: () => void;
  readonly onCambiado: () => void;
}

export function PanelUsuario({
  usuario,
  rolPropio,
  usuarioIdPropio,
  onCerrar,
  onCambiado,
}: Props) {
  const esUnoMismo = usuario.id === usuarioIdPropio;
  const editable = puedeEditar(rolPropio, esUnoMismo, usuario.rol);
  const otorgables = useMemo(() => rolesQuePuedeOtorgar(rolPropio), [rolPropio]);

  const [formulario, setFormulario] = useState<FormularioUsuario>(() =>
    formularioDesdeUsuario(usuario),
  );
  const [error, setError] = useState<string | null>(null);
  const [nuevaContrasena, setNuevaContrasena] = useState('');
  const [contrasenaFijada, setContrasenaFijada] = useState(false);

  // Una clave por operación y por cajón abierto: el reseteo cruza al proveedor
  // de auth, y repetirlo dejaría a la persona con una contraseña distinta de
  // la que le acaban de dictar (regla 1 del ROADMAP).
  const claveReseteo = useMemo(claveDeIdempotencia, []);

  const actualizar = useActualizarUsuarioApiV1UsuariosUsuarioIdPatch<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onCambiado();
      },
      onError: (err) => setError(err.message),
    },
  });

  const resetear = useResetearContrasenaApiV1UsuariosUsuarioIdContrasenaPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        setContrasenaFijada(true);
        onCambiado();
      },
      onError: (err) => setError(err.message),
    },
    request: { headers: { 'Idempotency-Key': claveReseteo } },
  });

  function cambiar<K extends keyof FormularioUsuario>(
    campo: K,
    valor: FormularioUsuario[K],
  ) {
    setFormulario((previo) => ({ ...previo, [campo]: valor }));
  }

  function guardar() {
    const cambios = cambiosDeUsuario(formulario, usuario);
    if (!hayCambios(cambios)) return;
    actualizar.mutate({ usuarioId: usuario.id, data: cambios });
  }

  function cambiarEstatus(activo: boolean) {
    actualizar.mutate({ usuarioId: usuario.id, data: { activo } });
  }

  const cambios = cambiosDeUsuario(formulario, usuario);

  return (
    <Sheet
      titulo={usuario.nombre}
      subtitulo={usuario.email}
      onCerrar={onCerrar}
    >
      <div className="sheet__body col gap-12">
        {error && <ErrorBanner mensaje={error} />}

        <div className="row gap-8">
          <span className={`badge badge--${tonoRol(usuario.rol)}`}>
            {etiquetaRol(usuario.rol)}
          </span>
          {usuario.estatus !== 'activo' && (
            <span className="badge badge--danger">Inactivo</span>
          )}
          {!usuario.puede_entrar && (
            <span className="badge badge--danger" title="Sin cuenta ligada">
              No puede entrar
            </span>
          )}
          {usuario.debe_cambiar_password && (
            <span className="badge badge--warn">Contraseña temporal</span>
          )}
        </div>

        {esUnoMismo && (
          <div className="field__hint">
            Eres tú. Nadie cambia su propio rol ni su propio estatus (§4); tu
            perfil se edita desde tu cuenta.
          </div>
        )}

        {!editable && !esUnoMismo && (
          <div className="field__hint">
            {usuario.rol === 'super_intendente'
              ? 'Solo un super intendente puede editar a otro super intendente (§4).'
              : 'Tu rol no administra el equipo (§5.1).'}
          </div>
        )}

        <div className="field">
          <label className="field__label" htmlFor="panel-nombre">
            Nombre
          </label>
          <input
            id="panel-nombre"
            className="input"
            value={formulario.nombre}
            onChange={(e) => cambiar('nombre', e.target.value)}
            disabled={!editable}
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="panel-rol">
            Rol
          </label>
          <select
            id="panel-rol"
            className="select"
            value={formulario.rol}
            onChange={(e) => cambiar('rol', e.target.value as Rol)}
            disabled={!editable}
          >
            {/* El rol actual va siempre en la lista aunque no se pueda
                otorgar: si no, el `select` mostraría otro valor y parecería
                que ya cambió. */}
            {[...new Set([usuario.rol as Rol, ...otorgables])].map((rol) => (
              <option key={rol} value={rol}>
                {etiquetaRol(rol)}
              </option>
            ))}
          </select>
        </div>

        <div className="row gap-12">
          <div className="field" style={{ flex: 1 }}>
            <label className="field__label" htmlFor="panel-cedula">
              Cédula
            </label>
            <input
              id="panel-cedula"
              className="input"
              value={formulario.cedula}
              onChange={(e) => cambiar('cedula', e.target.value)}
              disabled={!editable}
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label className="field__label" htmlFor="panel-telefono">
              Teléfono
            </label>
            <input
              id="panel-telefono"
              className="input"
              value={formulario.telefono}
              onChange={(e) => cambiar('telefono', e.target.value)}
              disabled={!editable}
            />
          </div>
        </div>

        {editable && (
          <>
            <hr className="sep" />

            <div className="field">
              <label className="field__label" htmlFor="panel-contrasena">
                Fijarle una contraseña temporal nueva
              </label>
              <div className="row gap-8">
                <input
                  id="panel-contrasena"
                  className="input mono"
                  value={nuevaContrasena}
                  onChange={(e) => {
                    setNuevaContrasena(e.target.value);
                    setContrasenaFijada(false);
                  }}
                  placeholder="Para cuando pierde la suya"
                  autoComplete="off"
                />
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() => {
                    setNuevaContrasena(sugerirContrasena());
                    setContrasenaFijada(false);
                  }}
                >
                  Sugerir
                </button>
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={
                    resetear.isPending ||
                    nuevaContrasena.length < LARGO_MINIMO_CONTRASENA
                  }
                  onClick={() =>
                    resetear.mutate({
                      usuarioId: usuario.id,
                      data: { contrasena_temporal: nuevaContrasena },
                    })
                  }
                >
                  Fijar
                </button>
              </div>
              {contrasenaFijada && (
                <div className="field__hint">
                  Lista. Comunícasela; se le pedirá cambiarla al entrar.
                </div>
              )}
            </div>

            <hr className="sep" />

            <div className="field">
              <div className="field__label">
                {usuario.estatus === 'activo' ? 'Dar de baja' : 'Reactivar'}
              </div>
              <div className="field__hint">
                Dar de baja <strong>no borra</strong>: sus capturas, cierres y
                estimaciones siguen apuntando a esta persona y el expediente
                tiene que poder decir quién los hizo (§11.3).
              </div>
              <button
                type="button"
                className={`btn btn--sm ${usuario.estatus === 'activo' ? 'btn--danger' : ''}`}
                style={{ alignSelf: 'flex-start', marginTop: 8 }}
                disabled={actualizar.isPending}
                onClick={() => cambiarEstatus(usuario.estatus !== 'activo')}
              >
                {usuario.estatus === 'activo' ? 'Dar de baja' : 'Reactivar'}
              </button>
            </div>
          </>
        )}
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cerrar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!editable || actualizar.isPending || !hayCambios(cambios)}
          onClick={guardar}
        >
          {actualizar.isPending ? 'Guardando…' : 'Guardar cambios'}
        </button>
      </div>
    </Sheet>
  );
}
