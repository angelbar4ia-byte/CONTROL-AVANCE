import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Las pestañas del panel izquierdo del cuantificador, como en el artefacto de diseño:
 * Presupuesto · Planos · Mediciones · Trazos · Elementos (· Árbol para Control y Costos).
 *
 *  1. «Trazos» lista todos los trazos del plano, agrupados por concepto, con su cantidad.
 *  2. Un clic en un trazo de la lista lo elige en el plano y el detalle muestra sus enlaces.
 *  3. La búsqueda filtra la lista.
 *  4. «Elementos» tiene su propia pestaña y ya no está dentro de Mediciones.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_X = ['control'] as const;

test.describe('Cuantificador · pestañas Trazos y Elementos', () => {
  test.skip(!hayRoles(...ROLES_X), motivoSinRoles(...ROLES_X));
  test.setTimeout(120_000);

  test('la lista de trazos elige en el plano y Elementos tiene su pestaña', async ({ page, request }) => {
    const clave = `PES-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });
    await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/generar`, { modo_pago: 'destajo' });
    const actividades = await llamarApi<{ id: string; concepto_clave: string }[]>(
      request,
      'control',
      'GET',
      `/obras/${obra.id}/actividades`,
    );
    const [a, b] = actividades as [(typeof actividades)[number], (typeof actividades)[number]];
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta pestañas',
      archivo_url: 'planos/pestanas.dwg',
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))',
      enlaces: [{ actividad_id: a.id, medida: 'area', factor: '1' }],
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'LINESTRING(20 0, 30 0)',
      enlaces: [{ actividad_id: b.id, medida: 'longitud', factor: '1' }],
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);

    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    for (const nombre of ['Presupuesto', 'Planos', 'Mediciones', 'Trazos', 'Elementos', 'Árbol']) {
      await expect(pestanas.getByRole('tab', { name: new RegExp(`^${nombre}`) })).toBeVisible();
    }
    // El contador de la pestaña Trazos es el número de trazos del plano.
    await expect(pestanas.getByRole('tab', { name: /^Trazos/ })).toContainText('2');

    // --- 1. La lista de trazos, agrupada por concepto ---------------------------------------------
    await pestanas.getByRole('tab', { name: /^Trazos/ }).click();
    const lista = page.getByRole('list', { name: 'Todos los trazos del plano' });
    await expect(lista.getByRole('listitem')).toHaveCount(2);
    await expect(lista.getByText(new RegExp(a.concepto_clave)).first()).toBeVisible();
    await expect(lista.getByText(new RegExp(b.concepto_clave)).first()).toBeVisible();

    // --- 2. Un clic en la lista elige el trazo y el detalle lo muestra -----------------------------
    await lista.getByRole('listitem').first().click();
    await expect(page.getByText('Trazo elegido')).toBeVisible();
    await expect(lista.getByRole('listitem').first()).toHaveAttribute('aria-current', 'true');

    // --- 3. La búsqueda filtra -----------------------------------------------------------------
    await page.getByRole('searchbox', { name: 'Buscar trazo' }).fill(b.concepto_clave);
    await expect(lista.getByRole('listitem')).toHaveCount(1);
    await page.getByRole('searchbox', { name: 'Buscar trazo' }).fill('zzzz-no-existe');
    await expect(page.getByText('Ningún trazo coincide.')).toBeVisible();

    // --- 4. Elementos tiene su propia pestaña, y ya no está dentro de Mediciones --------------------
    await pestanas.getByRole('tab', { name: /^Mediciones/ }).click();
    await expect(page.getByRole('tabpanel', { name: /Mediciones/ }).getByText('Elementos con peso')).toHaveCount(0);
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    await expect(page.getByRole('tabpanel', { name: /Elementos/ })).toBeVisible();
  });
});
