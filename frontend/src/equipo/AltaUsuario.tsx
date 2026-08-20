/**
 * Alta de usuario — `POST /usuarios` (§5.1, §11.2).
 *
 * Es la pantalla que la de Login lleva prometiendo desde la Fase 1: «el alta
 * de usuarios la realiza Control de obra». Hasta ahora había que insertar
 * filas a mano en SQL.
 *
 * LA CONTRASEÑA TEMPORAL
 *
 * La elige quien da de alta y se comunica por fuera —teléfono, papel—, así que
 * se sugiere una **legible**: la seguridad viene del largo y de que la persona
 * está obligada a cambiarla al entrar, no de meterle símbolos que se
 * transcriben mal. Se muestra en claro a propósito: quien la escribe la tiene
 * que poder dictar.
 *
 * `Idempotency-Key` va fija por formulario (regla 1 del ROADMAP): se genera al
 * montar y se manda igual en cada intento. Aquí importa más que en otras
 * pantallas porque el alta cruza a **otro sistema** —crea una cuenta en el
 * proveedor de auth— y un doble clic no se deshace solo.
 */

import { useMemo, useState, type FormEvent } from 'react';

import { useCrearUsuarioApiV1UsuariosPost } from '@/api/generado/usuarios/usuarios';
import { claveDeIdempotencia, type ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import type { Rol } from '@/shell/navegacion';
import {
  altaCompleta,
  formularioUsuarioVacio,
  peticionDeAlta,
  type FormularioUsuario,
} from './formulario';
import {
  LARGO_MINIMO_CONTRASENA,
  etiquetaRol,
  rolesQuePuedeOtorgar,
  sugerirContrasena,
} from './reglas';

interface Props {
  /** Rol de quien da el alta: decide qué roles se pueden otorgar (§4). */
  readonly rolPropio: Rol;
  readonly onCerrar: () => void;
  readonly onCreado: () => void;
}

export function AltaUsuario({ rolPropio, onCerrar, onCreado }: Props) {
  const clave = useMemo(claveDeIdempotencia, []);
  const otorgables = useMemo(() => rolesQuePuedeOtorgar(rolPropio), [rolPropio]);
  const [formulario, setFormulario] = useState<FormularioUsuario>(() =>
    formularioUsuarioVacio(otorgables[0] ?? 'residente', sugerirContrasena()),
  );
  const [error, setError] = useState<string | null>(null);

  const crear = useCrearUsuarioApiV1UsuariosPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onCreado();
      },
      onError: (err) => setError(err.message),
    },
    request: { headers: { 'Idempotency-Key': clave } },
  });

  function cambiar<K extends keyof FormularioUsuario>(
    campo: K,
    valor: FormularioUsuario[K],
  ) {
    setFormulario((previo) => ({ ...previo, [campo]: valor }));
  }

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!altaCompleta(formulario, LARGO_MINIMO_CONTRASENA)) return;
    crear.mutate({ data: peticionDeAlta(formulario) });
  }

  return (
    <Sheet
      titulo="Dar de alta a alguien del equipo"
      subtitulo="POST /usuarios · §5.1"
      onCerrar={onCerrar}
    >
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}

          <div className="field">
            <label className="field__label" htmlFor="usuario-nombre">
              Nombre
            </label>
            <input
              id="usuario-nombre"
              className="input"
              value={formulario.nombre}
              onChange={(e) => cambiar('nombre', e.target.value)}
              autoComplete="off"
              required
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="usuario-email">
              Correo
            </label>
            <input
              id="usuario-email"
              className="input"
              type="email"
              value={formulario.email}
              onChange={(e) => cambiar('email', e.target.value)}
              autoComplete="off"
              required
            />
            <div className="field__hint">
              Con este correo inicia sesión. No se puede repetir dentro de la
              organización.
            </div>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="usuario-rol">
              Rol
            </label>
            <select
              id="usuario-rol"
              className="select"
              value={formulario.rol}
              onChange={(e) => cambiar('rol', e.target.value as Rol)}
            >
              {otorgables.map((rol) => (
                <option key={rol} value={rol}>
                  {etiquetaRol(rol)}
                </option>
              ))}
            </select>
            {rolPropio !== 'super_intendente' && (
              <div className="field__hint">
                El rol de super intendente solo lo otorga otro super intendente
                (§4).
              </div>
            )}
          </div>

          <div className="field">
            <label className="field__label" htmlFor="usuario-contrasena">
              Contraseña temporal
            </label>
            <div className="row gap-8">
              <input
                id="usuario-contrasena"
                className="input mono"
                value={formulario.contrasenaTemporal}
                onChange={(e) => cambiar('contrasenaTemporal', e.target.value)}
                minLength={LARGO_MINIMO_CONTRASENA}
                autoComplete="off"
                required
              />
              <button
                type="button"
                className="btn btn--sm"
                onClick={() => cambiar('contrasenaTemporal', sugerirContrasena())}
              >
                Sugerir
              </button>
            </div>
            <div className="field__hint">
              Comunícasela por fuera. Al entrar se le pedirá cambiarla; mientras
              no lo haga aparece marcada en la lista.
            </div>
          </div>

          <div className="row gap-12">
            <div className="field" style={{ flex: 1 }}>
              <label className="field__label" htmlFor="usuario-cedula">
                Cédula <span className="text-mute">(opcional)</span>
              </label>
              <input
                id="usuario-cedula"
                className="input"
                value={formulario.cedula}
                onChange={(e) => cambiar('cedula', e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label className="field__label" htmlFor="usuario-telefono">
                Teléfono <span className="text-mute">(opcional)</span>
              </label>
              <input
                id="usuario-telefono"
                className="input"
                value={formulario.telefono}
                onChange={(e) => cambiar('telefono', e.target.value)}
                autoComplete="off"
              />
            </div>
          </div>
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={
              crear.isPending || !altaCompleta(formulario, LARGO_MINIMO_CONTRASENA)
            }
          >
            {crear.isPending ? 'Creando…' : 'Dar de alta'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
