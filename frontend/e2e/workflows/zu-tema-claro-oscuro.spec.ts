import { entrarComo, expect, hayRoles, motivoSinRoles, test } from '../infraestructura';

/** El tema de la app: el botón de la barra alterna sistema → claro → oscuro y los colores cambian de verdad. */

const ROLES_ZU = ['control'] as const;

test.describe('Tema claro y oscuro', () => {
  test.skip(!hayRoles(...ROLES_ZU), motivoSinRoles(...ROLES_ZU));
  test.setTimeout(90_000);

  test('el botón alterna el tema y se recuerda al recargar', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await entrarComo(page, 'control');
    const html = page.locator('html');
    const fondo = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    const boton = page.getByRole('button', { name: /^Tema/ });

    await expect(html).toHaveAttribute('data-theme', 'claro'); // sistema = claro
    const claro = await fondo();

    await boton.click(); // → claro (fijo)
    await boton.click(); // → oscuro
    await expect(html).toHaveAttribute('data-theme', 'oscuro');
    expect(await fondo()).not.toBe(claro);
    await page.screenshot({ path: process.env.E2E_CAPTURAS ? `${process.env.E2E_CAPTURAS}/oscuro.png` : undefined });

    await page.reload();
    await expect(html).toHaveAttribute('data-theme', 'oscuro');

    await boton.click(); // → sistema (claro)
    await expect(html).toHaveAttribute('data-theme', 'claro');
  });
});
