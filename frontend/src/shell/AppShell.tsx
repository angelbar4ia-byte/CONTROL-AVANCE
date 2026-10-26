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
 *
 * ## Las clases son las del sistema de diseño, no unas parecidas
 *
 * Este archivo pintaba `nav-item`, `topbar-actions`, `badge-ok` y
 * `sidebar-brand`: **ninguna existe** en `estilos/obractrl-design.css`, que las
 * llama `sidebar__item`, `topbar__actions`, `badge--ok` y `topbar__brand`. El
 * navegador no avisa de una clase que no existe —simplemente no aplica nada— y
 * por eso el sidebar llevaba fases enteras sin su fondo, su marca de activo ni
 * su hover, con el layout aguantando solo por el `grid` de `.app`.
 *
 * `src/pruebas/estilos.test.ts` ahora falla si vuelve a pasar.
 *
 * ## Y por eso también faltaba el móvil
 *
 * El sistema de diseño ya traía las reglas: bajo 880px esconde `.sidebar`, la
 * muestra como cajón con `.app.is-mobile-nav-open` y reserva una
 * `.mobile-tabbar` abajo. Nada de eso se renderizaba, así que **por debajo de
 * 880px la web se quedaba sin ninguna navegación**: ni sidebar, ni botón para
 * abrirlo, ni tabs. Aquí se rendera lo que el CSS esperaba encontrar.
 */

import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Menu, Wifi, WifiOff, X } from 'lucide-react';

import { ALCANCE_ROL, NOMBRE_ROL, navegacionDe, tabsDe, type Rol } from './navegacion';
import { useTiempoReal, type EstadoEnVivo } from '@/lib/tiempoReal';
import { fmtSemana } from '@/lib/formato';
import { SelectorDensidad } from './SelectorDensidad';
import { ProveedorDeVentanaCuantificador } from '@/cuantificador/VentanaCuantificador';

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

  const [navAbierta, setNavAbierta] = useState(false);
  const ubicacion = useLocation();

  // Navegar cierra el cajón. Sin esto, en un teléfono se toca una entrada, la
  // pantalla cambia detrás y el usuario sigue viendo el menú encima.
  useEffect(() => setNavAbierta(false), [ubicacion.pathname]);

  // Escape también: es un cajón modal y en escritorio angosto se abre sin
  // querer más de una vez.
  useEffect(() => {
    if (!navAbierta) return;
    const alTeclear = (evento: KeyboardEvent) => {
      if (evento.key === 'Escape') setNavAbierta(false);
    };
    window.addEventListener('keydown', alTeclear);
    return () => window.removeEventListener('keydown', alTeclear);
  }, [navAbierta]);

  return (
    <ProveedorDeVentanaCuantificador>
    <div className={navAbierta ? 'app is-mobile-nav-open' : 'app'}>
      <BarraSuperior
        rol={rol}
        usuario={usuario}
        semana={semana}
        enLinea={enLinea}
        enVivo={enVivo}
        navAbierta={navAbierta}
        onAlternarNav={() => setNavAbierta((abierta) => !abierta)}
      />

      <Sidebar rol={rol} />

      {/* El velo solo existe con el cajón abierto: tocar fuera lo cierra, que
          es lo que un pulgar intenta primero.

          `aria-hidden` y un `div`, no un botón: como botón compartía nombre
          accesible con el interruptor de la barra —dos controles distintos
          llamados "Cerrar el menú"— y un lector de pantalla no puede
          distinguirlos. El teclado no se queda sin salida: Escape cierra, y el
          interruptor sigue siendo un botón de verdad. */}
      {navAbierta && (
        <div
          className="scrim"
          aria-hidden
          onClick={() => setNavAbierta(false)}
        />
      )}

      <main className="main">
        {/* Cada feature renderiza: filtros → vista principal → cajón (§12.10) */}
        <Outlet />
      </main>

      <TabsMoviles rol={rol} />
    </div>
    </ProveedorDeVentanaCuantificador>
  );
}

function Sidebar({ rol }: { readonly rol: Rol }) {
  return (
    <aside className="sidebar" aria-label="Navegación principal">
      <nav>
        {navegacionDe(rol).map((seccion) => (
          <div key={seccion.titulo}>
            <div className="sidebar__section">{seccion.titulo}</div>

            {seccion.items.map((item) => {
              const Icono = item.icono;
              return (
                <NavLink
                  key={item.a}
                  to={item.a}
                  className={({ isActive }) =>
                    isActive ? 'sidebar__item is-active' : 'sidebar__item'
                  }
                >
                  <span className="sidebar__icon">
                    <Icono size={16} strokeWidth={1.6} />
                  </span>
                  <span>{item.etiqueta}</span>
                  {item.soloLectura && (
                    <span className="sidebar__count" title="Solo lectura">
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

/**
 * Tabs de abajo: la navegación de un teléfono (§12.10, `.mobile-tabbar`).
 *
 * No repite el sidebar entero —no cabe— sino **las primeras entradas del rol**,
 * que son las que su §5.1 pone arriba de todo. El resto se alcanza abriendo el
 * cajón desde la barra superior.
 *
 * El CSS la esconde por encima de 880px, así que no hace falta condicionarla
 * en JS: una sola fuente para el punto de quiebre, en vez de un `matchMedia`
 * aquí que se desincronice del `@media` de allá.
 */
function TabsMoviles({ rol }: { readonly rol: Rol }) {
  return (
    <nav className="mobile-tabbar" aria-label="Accesos rápidos">
      {tabsDe(rol).map((item) => {
        const Icono = item.icono;
        return (
          <NavLink
            key={item.a}
            to={item.a}
            className={({ isActive }) =>
              isActive ? 'mobile-tabbar__item is-active' : 'mobile-tabbar__item'
            }
          >
            <Icono size={18} strokeWidth={1.6} />
            <span>{item.etiqueta}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}

function BarraSuperior({
  rol,
  usuario,
  semana,
  enLinea,
  enVivo,
  navAbierta,
  onAlternarNav,
}: Props & {
  readonly enVivo: EstadoEnVivo;
  readonly navAbierta: boolean;
  readonly onAlternarNav: () => void;
}) {
  return (
    <header className="topbar">
      {/* Solo visible en pantalla angosta (`.topbar__nav-toggle`): en
          escritorio el sidebar está siempre ahí y un botón para abrir algo
          que ya se ve sería ruido. */}
      <button
        type="button"
        className="btn btn--ghost btn--icon topbar__nav-toggle"
        aria-label={navAbierta ? 'Cerrar el menú' : 'Abrir el menú'}
        aria-expanded={navAbierta}
        onClick={onAlternarNav}
      >
        {navAbierta ? <X size={18} strokeWidth={1.6} /> : <Menu size={18} strokeWidth={1.6} />}
      </button>

      <div className="topbar__brand">
        <span className="topbar__brand-mark" aria-hidden>
          OC
        </span>
        <span className="topbar__brand-name">ObraCtrl</span>
      </div>

      <div className="crumbs">
        <span className="mono">{fmtSemana(semana.numero, semana.anio)}</span>
        <span className="crumbs__sep">/</span>
        <span className="crumbs__item-mut">{ALCANCE_ROL[rol]}</span>
      </div>

      <div className="topbar__spacer" />

      <div className="topbar__actions">
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
          className={enLinea ? 'badge badge--ok' : 'badge badge--warn'}
          title={
            enLinea
              ? 'En línea'
              : 'Sin conexión: la captura se guarda local y se sincroniza al reconectar'
          }
        >
          {enLinea ? <Wifi size={14} strokeWidth={1.6} /> : <WifiOff size={14} strokeWidth={1.6} />}
          <span className="topbar__solo-ancho">{enLinea ? 'En línea' : 'Sin conexión'}</span>
        </span>

        <SelectorDensidad />

        <div className="role-chip">
          <span className="role-chip__dot" aria-hidden>
            {inicial(usuario)}
          </span>
          <div className="topbar__solo-ancho">
            <div>{usuario}</div>
            <div className="role-chip__sub mono">{NOMBRE_ROL[rol]}</div>
          </div>
        </div>
      </div>
    </header>
  );
}

/** Inicial para el avatar del chip. Cae en `?` antes que quedar vacío. */
function inicial(nombre: string): string {
  return nombre.trim().charAt(0).toUpperCase() || '?';
}
