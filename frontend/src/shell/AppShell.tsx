/**
 * Shell de 3 columnas.
 *
 * Spec §12.10 (layout) · §5.1 (sidebar por rol) · §3.1 (semana activa).
 *
 * La misma estructura en toda pantalla operativa, para que el usuario
 * construya memoria muscular:
 *
 *   Sidebar (módulos del rol) │ Barra superior (contexto vivo)
 *                             │ Filtros de página
 *                             │ Área central elástica
 *                             │ Cajón derecho (drill-down)
 */

import { NavLink, Outlet } from 'react-router-dom';
import { Wifi, WifiOff } from 'lucide-react';

import { ALCANCE_ROL, NOMBRE_ROL, navegacionDe, type Rol } from './navegacion';
import { fmtSemana } from '@/lib/formato';
import { SelectorDensidad } from './SelectorDensidad';

interface Props {
  readonly rol: Rol;
  readonly usuario: string;
  /** Semana activa del ancla de configuración (§3.1). */
  readonly semana: { readonly numero: number; readonly anio: number };
  readonly enLinea: boolean;
}

export function AppShell({ rol, usuario, semana, enLinea }: Props) {
  return (
    <div className="app">
      <Sidebar rol={rol} />
      <BarraSuperior
        rol={rol}
        usuario={usuario}
        semana={semana}
        enLinea={enLinea}
      />
      <main className="main">
        {/* Cada feature renderiza: filtros → vista principal → cajón (§12.10) */}
        <Outlet />
      </main>
    </div>
  );
}

function Sidebar({ rol }: { readonly rol: Rol }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand mono">ObraCtrl</div>

      <nav>
        {navegacionDe(rol).map((seccion) => (
          <div key={seccion.titulo} className="nav-section">
            <div className="nav-section-title">{seccion.titulo}</div>

            {seccion.items.map((item) => {
              const Icono = item.icono;
              return (
                <NavLink
                  key={item.a}
                  to={item.a}
                  className={({ isActive }) =>
                    isActive ? 'nav-item is-active' : 'nav-item'
                  }
                >
                  <Icono size={16} strokeWidth={1.6} />
                  <span>{item.etiqueta}</span>
                  {item.soloLectura && (
                    <span className="badge badge-outline mono" title="Solo lectura">
                      L
                    </span>
                  )}
                </NavLink>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}

function BarraSuperior({ rol, usuario, semana, enLinea }: Props) {
  return (
    <header className="topbar">
      <div className="crumbs">
        <span className="mono">{fmtSemana(semana.numero, semana.anio)}</span>
        <span className="crumb-sep">/</span>
        <span>{ALCANCE_ROL[rol]}</span>
      </div>

      <div className="topbar-actions">
        {/* Estado online/offline: el Residente captura sin señal (§12.5) */}
        <span
          className={enLinea ? 'badge badge-ok' : 'badge badge-warn'}
          title={
            enLinea
              ? 'En línea'
              : 'Sin conexión: la captura se guarda local y se sincroniza al reconectar'
          }
        >
          {enLinea ? <Wifi size={14} strokeWidth={1.6} /> : <WifiOff size={14} strokeWidth={1.6} />}
          {enLinea ? 'En línea' : 'Sin conexión'}
        </span>

        <SelectorDensidad />

        <div className="role-chip">
          <span className="role-dot" aria-hidden />
          <div>
            <div>{usuario}</div>
            <div className="role-chip-sub mono">{NOMBRE_ROL[rol]}</div>
          </div>
        </div>
      </div>
    </header>
  );
}
