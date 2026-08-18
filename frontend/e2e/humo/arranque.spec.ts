import { expect, test } from '@playwright/test';

/**
 * Humo: la aplicación arranca y pinta el login (§5.1).
 *
 * No necesita backend. Lo que verifica es lo que ninguna prueba de Vitest ve,
 * porque Vitest nunca monta la app entera en un navegador real: que el bundle
 * cargue, que los providers se monten en orden y que la primera pantalla
 * aparezca. Un import circular, un `@/` mal resuelto o un provider fuera de
 * lugar rompen aquí y en ningún otro lado.
 */

test.describe('Arranque de la web', () => {
  test('pinta la pantalla de acceso', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'ObraCtrl' })).toBeVisible();
    await expect(page.getByLabel('Correo')).toBeVisible();
    await expect(page.getByLabel('Contraseña')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible();
  });

  test('el formulario exige correo y contraseña', async ({ page }) => {
    /**
     * La validación es del navegador (`required`), no nuestra: se comprueba
     * que el envío no ocurra, que es lo que importa. Sin esto, un submit vacío
     * viajaría hasta el proveedor de auth por nada.
     */
    await page.goto('/');
    await page.getByRole('button', { name: 'Entrar' }).click();

    await expect(page.getByLabel('Correo')).toBeFocused();
    await expect(page).toHaveURL(/\/$/);
  });

  test('dice quién da de alta a los usuarios', async ({ page }) => {
    // §5.1: el alta es de Control de obra. Sin esta línea, un residente sin
    // cuenta se queda en la pantalla sin saber a quién pedirle acceso.
    await page.goto('/');
    await expect(page.getByText(/alta de usuarios/i)).toBeVisible();
  });

  test('no deja errores de consola al cargar', async ({ page }) => {
    /**
     * Un `console.error` en el arranque suele ser un warning de React sobre
     * hooks o claves duplicadas: barato de arreglar cuando se ve, caro cuando
     * se acumula.
     *
     * Se ignoran los fallos de red: sin backend, la consulta de sesión a
     * Supabase falla y eso es esperado en este nivel.
     */
    const errores: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !/net::|fetch|Failed to load/i.test(msg.text())) {
        errores.push(msg.text());
      }
    });

    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'ObraCtrl' })).toBeVisible();

    expect(errores).toEqual([]);
  });
});
