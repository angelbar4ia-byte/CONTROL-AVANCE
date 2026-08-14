/**
 * Login — email + contraseña contra Supabase Auth (§12.4, §5.1).
 *
 * El alta de usuarios la hace Control de obra desde Configuración (fuera de
 * alcance aquí); esta pantalla solo autentica. `org_id`/`rol` no se piden ni
 * se eligen aquí: salen del JWT vía el Custom Access Token Hook
 * (`database/migrations/20260814000015_auth_hook.sql`) — si el usuario no
 * tiene un `usuario` de ObraCtrl ligado a su cuenta de Auth, el backend
 * rechaza el token después (401) aunque el login en sí haya sido válido.
 */

import { useState, type FormEvent } from 'react';

import { supabase } from '@/lib/supabase';

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError(null);

    const { error: errorSupabase } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });

    setEnviando(false);
    if (errorSupabase) {
      // Mensaje genérico a propósito: no confirmar si el email existe.
      setError('Correo o contraseña incorrectos.');
    }
    // Éxito: onAuthStateChange (useSesion, app/sesion.ts) recoge la sesión
    // nueva solo; no hay redirect manual aquí.
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--c-bg)',
      }}
    >
      <div className="card" style={{ width: 360 }}>
        <div className="card__header" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
          <h1 className="card__title" style={{ fontSize: 'var(--fs-2xl)' }}>
            ObraCtrl
          </h1>
          <div className="card__sub">Inicia sesión con tu cuenta.</div>
        </div>

        <div className="card__body">
          <form onSubmit={(e) => void enviar(e)} className="col gap-12">
            <div className="field">
              <label className="field__label" htmlFor="login-email">
                Correo
              </label>
              <input
                id="login-email"
                type="email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                required
              />
            </div>

            <div className="field">
              <label className="field__label" htmlFor="login-password">
                Contraseña
              </label>
              <input
                id="login-password"
                type="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            {error && (
              <div className="badge badge--danger" role="alert">
                {error}
              </div>
            )}

            <button type="submit" className="btn btn--accent" disabled={enviando}>
              {enviando ? 'Entrando…' : 'Entrar'}
            </button>
          </form>

          <div className="field__hint" style={{ marginTop: 12 }}>
            El alta de usuarios la realiza Control de obra (§5.1).
          </div>
        </div>
      </div>
    </div>
  );
}
