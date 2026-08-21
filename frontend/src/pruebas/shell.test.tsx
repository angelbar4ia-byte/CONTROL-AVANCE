/**
 * El shell: sidebar en su lugar y navegación cuando la pantalla es angosta.
 *
 * `estilos.test.ts` comprueba que las clases existan; esto comprueba que el
 * shell **se comporte**. Son dos fallos distintos y ninguno de los dos lo ve
 * un typecheck:
 *
 * - pintar una clase que no existe (el sidebar quedó sin estilo varias fases),
 * - no renderizar el interruptor que el `@media` de 880px da por hecho, que
 *   dejaba la web **sin ninguna navegación** en una tablet o un teléfono.
 *
 * Se monta el `AppShell` real con un router de memoria. Lo que se sustituye es
 * lo que sale del navegador —el canal de avisos, que abriría una conexión— y
 * nada más: la navegación por rol viene de `navegacion.ts` de verdad.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('@/lib/tiempoReal', () => ({
  useTiempoReal: () => 'en-vivo',
}));

import { AppShell } from '@/shell/AppShell';
import { TABS_MOVILES, navegacionDe, tabsDe } from '@/shell/navegacion';
import type { Rol } from '@/shell/navegacion';

function montar(rol: Rol = 'control_obra') {
  return render(
    <MemoryRouter initialEntries={['/torre']}>
      <Routes>
        <Route
          element={
            <AppShell
              rol={rol}
              usuario="Ana Ruiz"
              semana={{ numero: 33, anio: 2026 }}
              enLinea
            />
          }
        >
          <Route path="/torre" element={<p>Torre</p>} />
          <Route path="/incidencias" element={<p>Incidencias</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

/** La raíz `.app`, que es donde vive el estado del cajón. */
function raiz(contenedor: HTMLElement): HTMLElement {
  const nodo = contenedor.querySelector('.app');
  expect(nodo).not.toBeNull();
  return nodo as HTMLElement;
}

describe('sidebar', () => {
  it('pinta las entradas del rol con la clase del sistema de diseño', () => {
    const { container } = montar('control_obra');

    const items = container.querySelectorAll('.sidebar__item');
    const esperadas = navegacionDe('control_obra').flatMap((s) => s.items);

    expect(items.length).toBe(esperadas.length);
    // Y no la clase inventada que estuvo ahí durante fases.
    expect(container.querySelectorAll('.nav-item').length).toBe(0);
  });

  it('marca la entrada activa, que es lo que se perdía sin la clase', () => {
    const { container } = montar('control_obra');

    const activas = container.querySelectorAll('.sidebar__item.is-active');
    expect(activas.length).toBe(1);
    expect(activas[0]?.textContent).toContain('Torre de control');
  });

  it('cada rol ve su propio sidebar (§5.1)', () => {
    const { container, unmount } = montar('residente');
    const delResidente = [...container.querySelectorAll('.sidebar__item')].map(
      (n) => n.textContent,
    );
    unmount();

    const { container: otro } = montar('super_intendente');
    const delSuper = [...otro.querySelectorAll('.sidebar__item')].map((n) => n.textContent);

    expect(delResidente).not.toEqual(delSuper);
    expect(delSuper.join(' ')).toContain('Mejora de procesos');
  });
});

describe('navegación en pantalla angosta', () => {
  it('el cajón empieza cerrado', () => {
    const { container } = montar();
    expect(raiz(container).className).toBe('app');
  });

  it('el botón de menú lo abre y lo cierra', () => {
    const { container } = montar();
    const boton = screen.getByRole('button', { name: 'Abrir el menú' });

    fireEvent.click(boton);
    expect(raiz(container).className).toContain('is-mobile-nav-open');

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar el menú' }));
    expect(raiz(container).className).toBe('app');
  });

  it('tocar el velo lo cierra', () => {
    // Es lo primero que intenta un pulgar, y sin el velo el cajón se quedaba
    // encima de la pantalla que acababa de abrir.
    const { container } = montar();
    fireEvent.click(screen.getByRole('button', { name: 'Abrir el menú' }));

    const velo = container.querySelector('.scrim');
    expect(velo).not.toBeNull();
    fireEvent.click(velo as Element);

    expect(raiz(container).className).toBe('app');
  });

  it('Escape lo cierra', () => {
    const { container } = montar();
    fireEvent.click(screen.getByRole('button', { name: 'Abrir el menú' }));

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(raiz(container).className).toBe('app');
  });

  it('navegar lo cierra', () => {
    // Sin esto, en un teléfono se toca una entrada, la pantalla cambia detrás
    // y el menú se queda encima tapándola.
    const { container } = montar('control_obra');
    fireEvent.click(screen.getByRole('button', { name: 'Abrir el menú' }));

    const incidencias = [...container.querySelectorAll('.sidebar__item')].find((n) =>
      n.textContent?.includes('Incidencias'),
    );
    fireEvent.click(incidencias as Element);

    expect(raiz(container).className).toBe('app');
  });

  it('el velo no existe con el cajón cerrado', () => {
    // Un velo invisible pero presente se come los clics de toda la pantalla.
    const { container } = montar();
    expect(container.querySelector('.scrim')).toBeNull();
  });
});

describe('tabs del móvil', () => {
  it('lleva las primeras entradas del sidebar del rol, no una lista aparte', () => {
    const { container } = montar('residente');

    const tabs = [...container.querySelectorAll('.mobile-tabbar__item')].map(
      (n) => n.textContent,
    );
    const esperadas = tabsDe('residente').map((i) => i.etiqueta);

    expect(tabs).toEqual(esperadas);
    expect(tabs.length).toBeLessThanOrEqual(TABS_MOVILES);
  });

  it('las trae todo rol, porque el CSS es quien decide si se ven', () => {
    // El punto de quiebre vive una sola vez, en el `@media`. Condicionarlo
    // también en JS sería una segunda copia que se desincroniza.
    for (const rol of ['residente', 'supervisor', 'control_obra', 'super_intendente'] as const) {
      const { container, unmount } = montar(rol);
      expect(container.querySelectorAll('.mobile-tabbar__item').length).toBe(
        tabsDe(rol).length,
      );
      unmount();
    }
  });
});

describe('barra superior', () => {
  it('dice el estado del canal y el de la red por separado', () => {
    // Se puede tener red y no tener avisos —API caída, proxy que corta el
    // streaming—; mostrarlo como uno solo haría creer que la Torre está al día.
    montar();
    expect(screen.getByText('En vivo')).toBeVisible();
    expect(screen.getByText('En línea')).toBeVisible();
  });

  it('el chip de rol lleva la inicial y el nombre del rol', () => {
    const { container } = montar('control_obra');

    // Acotado al chip: "Control de obra" también es un título de sección del
    // sidebar (§5.1), así que buscarlo suelto encuentra dos y la prueba
    // pasaría o fallaría por dónde mire, no por lo que comprueba.
    const chip = container.querySelector('.role-chip');
    expect(chip?.textContent).toContain('A');
    expect(chip?.querySelector('.role-chip__sub')?.textContent).toBe('Control de obra');
  });
});
