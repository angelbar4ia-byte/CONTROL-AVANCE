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
import { queryClient } from '@/app/queryClient';
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

  const { sesion, cargando } = useSesion();
  const enLinea = useEnLinea();

  if (cargando) return <Cargando />;
  if (!sesion) return <PantallaLogin />;

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
        {/* La ruta inicial depende del rol: el Residente entra a sus obras,
            los demás a la Torre de control (§5.1). */}
        <Route
          index
          element={
            <Navigate to={sesion.rol === 'residente' ? '/obras' : '/torre'} replace />
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
    <div className="empty">
      <div className="empty-title">Cargando…</div>
    </div>
  );
}

function PantallaLogin() {
  return (
    <div className="empty">
      <div className="empty-title">Inicia sesión</div>
      <div className="empty-sub">
        El alta de usuarios la realiza Control de obra (§5.1).
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
