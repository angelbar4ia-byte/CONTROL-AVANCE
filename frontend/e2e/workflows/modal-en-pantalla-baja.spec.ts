import { entrarComo, expect, hayRoles, motivoSinRoles, test } from '../infraestructura';

/**
 * Un modal más alto que la pantalla no puede esconder su botón de enviar.
 *
 * Es el mismo defecto que tuvo el cajón lateral (`.sheet`): el contenedor
 * crecía con el formulario en vez de limitarse a la pantalla y el pie quedaba
 * fuera, sin forma de llegar. Aquí se baja la ventana a 420 px de alto, mucho
 * menos que el alta de obra, y se exige que el botón esté **a la vista sin
 * desplazar la página**: el cuerpo del modal es lo que se desplaza, el pie no.
 */

const ROLES = ['control'] as const;

test.describe('Modales en una pantalla baja', () => {
  test.skip(!hayRoles(...ROLES), motivoSinRoles(...ROLES));

  test('el alta de obra deja su botón a la vista y su cuerpo se desplaza', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 420 });
    await entrarComo(page, 'control');
    await page.goto('/obras');
    await page.getByRole('button', { name: 'Nueva obra' }).click();

    const alta = page.getByRole('dialog');
    await expect(alta).toBeVisible();
    // El modal cabe en la pantalla…
    const caja = (await alta.boundingBox())!;
    expect(caja.y).toBeGreaterThanOrEqual(0);
    expect(caja.y + caja.height).toBeLessThanOrEqual(420);
    // …y el botón de enviar está a la vista sin desplazar nada.
    await expect(alta.getByRole('button', { name: 'Crear obra' })).toBeInViewport();
  });
});
