import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, solicitarApi, test } from '../infraestructura';

/**
 * La clasificación de los elementos paramétricos en la biblioteca (plan de elementos de muro, fase A):
 *  1. Cada elemento trae su categoría y su subcategoría, y la pestaña Trazos las muestra.
 *  2. Una cadena de cerramiento y una de desplante con la misma geometría conviven (la subcategoría es parte de la identidad).
 *  3. Un elemento idéntico a otro no se guarda: 409 con la clave del que ya existe.
 *  4. Reclasificar un elemento hasta dejarlo idéntico a otro se rechaza y el aviso dice cuál es.
 *
 * Es una obra nueva por corrida; los elementos llevan un alto único por corrida para no chocar con los de otros specs.
 */

const ROLES_ZZ = ['control'] as const;

test.describe('Cuantificador · clasificación de los elementos', () => {
  test.skip(!hayRoles(...ROLES_ZZ), motivoSinRoles(...ROLES_ZZ));
  test.setTimeout(120_000);

  test('cerramiento y desplante conviven, un idéntico se rechaza y la pantalla muestra el uso', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `CLA-${sufijo}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Clasificación',
      archivo_url: 'planos/clasificacion.dwg',
    });

    const alto = 0.5 + (Date.now() % 1_000_000) / 1e7;
    const cadena = (clave: string, subcategoria: string) => ({
      clave,
      nombre: `Cadena ${clave}`,
      tipo: 'lineal',
      categoria: 'cadenas',
      subcategoria,
      parametros: { ancho: 0.15, alto },
    });
    const ce = `CE-${sufijo}`.slice(0, 20);
    const cd = `CD-${sufijo}`.slice(0, 20);
    const otra = `CX-${sufijo}`.slice(0, 20);

    await llamarApi(request, 'control', 'POST', '/elementos-parametricos', cadena(ce, 'cerramiento'));
    await llamarApi(request, 'control', 'POST', '/elementos-parametricos', cadena(cd, 'desplante'));
    const repetido = await solicitarApi(request, 'control', 'POST', '/elementos-parametricos', cadena(otra, 'desplante'));
    expect(repetido.status()).toBe(409);
    expect((await repetido.json()).clave_igual).toBe(cd);

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /^Trazos/ }).click();
    await expect(page.locator(`[data-uso-del-elemento="${ce}"]`)).toHaveText('Cadenas › Cadenas de cerramiento');
    await expect(page.locator(`[data-uso-del-elemento="${cd}"]`)).toHaveText('Cadenas › Cadenas de desplante');
    await expect(page.locator(`[data-parametrico="${otra}"]`)).toHaveCount(0); // el rechazado no se guardó

    // Pasar el desplante a cerramiento lo dejaría idéntico al de cerramiento: se rechaza y el aviso dice con cuál choca.
    await page.getByRole('button', { name: `Ver ${cd}` }).click();
    await page.getByLabel(`Subcategoría de ${cd}`).selectOption('cerramiento');
    await expect(page.getByRole('status')).toContainText(ce);
    await expect(page.locator(`[data-uso-del-elemento="${cd}"]`)).toHaveText('Cadenas › Cadenas de desplante');
  });
});
