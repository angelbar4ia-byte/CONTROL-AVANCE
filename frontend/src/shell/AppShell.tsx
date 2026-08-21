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
import { useTiempoReal, type EstadoEnVivo } from '@/lib/tiempoReal';
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
  // El canal de avisos se abre **aquí y solo aquí** (§11.2): dos suscripciones
  // serían dos conexiones por pestaña y cada hecho invalidaría dos veces.
  const enVivo = useTiempoReal();

  return (
    <div className="app">
      <Sidebar rol={rol} />
      <BarraSuperior
        rol={rol}
        usuario={usuario}
        semana={semana}
        enLinea={enLinea}
        enVivo={enVivo}
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

function BarraSuperior({
  rol,
  usuario,
  semana,
  enLinea,
  enVivo,
}: Props & { readonly enVivo: EstadoEnVivo }) {
  return (
    <header className="topbar">
      <div className="crumbs">
        <span className="mono">{fmtSemana(semana.numero, semana.anio)}</span>
        <span className="crumb-sep">/</span>
        <span>{ALCANCE_ROL[rol]}</span>
      </div>

      <div className="topbar-actions">
        {/* Avisos en vivo (§11.2). Se distingue de "en línea" a propósito: se
            puede tener red y no tener canal —la API caída, un proxy que corta
            el streaming— y en ese caso las pantallas siguen funcionando pero
            dejan de enterarse solas. Decirlo evita que alguien mire una Torre
            vieja creyéndola actual. */}
        <span
          className={enVivo === 'en-vivo' ? 'badge badge--ok' : 'badge badge--outline'}
          title={
            enVivo === 'en-vivo'
              ? 'Recibiendo avisos: la pantalla se actualiza sola'
              : 'Sin avisos en vivo: los datos se recargan al navegar o al recargar'
          }
        >
          {enVivo === 'en-vivo' ? 'En vivo' : 'Sin avisos'}
        </span>

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
