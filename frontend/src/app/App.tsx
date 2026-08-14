/**
 * Raíz de la aplicación: providers y rutas.
 *
 * Spec §5.1 (navegación por rol) · §5.3 (pantallas compartidas).
 *
 * Las pantallas compartidas se montan **una sola vez** y cambian
 * comportamiento por rol y alcance; no hay una copia por rol (§5.3).
 */

import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '@/shell/AppShell';
import { useAplicarDensidad } from '@/shell/SelectorDensidad';
import { useSesion } from '@/app/sesion';
import { Login } from '@/app/Login';
import { queryClient } from '@/app/queryClient';
import { supabase } from '@/lib/supabase';
import { useEnLinea } from '@/lib/useEnLinea';
import Avances from '@/avance/Avances';
import Cierres from '@/cierres/Cierres';
import Estimacion from '@/estimacion/Estimacion';

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Rutas />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

function Rutas() {
  useAplicarDensidad();

  const { sesion, cargando, error } = useSesion();
  const enLinea = useEnLinea();

  if (cargando) return <Cargando />;
  if (error) return <SesionSinVincular mensaje={error} />;
  if (!sesion) return <Login />;

  return (
    <Routes>
      <Route
        element={
          <AppShell
            rol={sesion.rol}
            usuario={sesion.nombre}
            semana={sesion.semanaActiva}
            enLinea={enLinea}
          />
        }
      >
        {/* La ruta inicial depende del rol. El Residente entra a sus obras;
            los demás a Cierres —hoy la única pantalla compartida real; la
            Torre de control (§5.1) todavía no está implementada. */}
        <Route
          index
          element={
            <Navigate to={sesion.rol === 'residente' ? '/obras' : '/cierres'} replace />
          }
        />
        {/* Las features se registran aquí conforme se implementan. */}
        <Route path="/avances" element={<Avances />} />
        <Route path="/cierres" element={<Cierres />} />
        <Route path="/estimacion" element={<Estimacion />} />
        <Route path="*" element={<EnConstruccion />} />
      </Route>
    </Routes>
  );
}

function Cargando() {
  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
      <div className="text-mute text-sm">Cargando…</div>
    </div>
  );
}

/**
 * El usuario sí se autenticó en Supabase, pero su cuenta no tiene un
 * `usuario` de ObraCtrl vinculado (o está inactivo) — el Custom Access
 * Token Hook no encontró fila y el JWT salió sin `org_id`/`rol`
 * (`database/migrations/20260814000015_auth_hook.sql`). No es un error de
 * login: es una cuenta sin dar de alta en la organización.
 */
function SesionSinVincular({ mensaje }: { readonly mensaje: string }) {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div className="card" style={{ width: 360 }}>
        <div className="card__header" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
          <h1 className="card__title">Cuenta sin vincular</h1>
        </div>
        <div className="card__body col gap-12">
          <div className="badge badge--danger" role="alert">
            {mensaje}
          </div>
          <div className="field__hint">
            Pide a Control de obra que dé de alta tu usuario en la organización.
          </div>
          <button type="button" className="btn" onClick={() => void supabase.auth.signOut()}>
            Cerrar sesión
          </button>
        </div>
      </div>
    </div>
  );
}

function EnConstruccion() {
  return (
    <div className="page">
      <div className="page-head">
        <div className="eyebrow mono">ObraCtrl</div>
        <h1 className="title">Pantalla pendiente</h1>
      </div>
      <div className="empty">
        <div className="empty-title">Aún no implementada</div>
        <div className="empty-sub">
          El shell, la navegación por rol y los tokens ya están listos.
          Las features se agregan una por una en <code>src/features/</code>.
        </div>
      </div>
    </div>
  );
}
