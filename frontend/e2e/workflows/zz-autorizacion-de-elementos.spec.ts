import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, solicitarApi, test } from '../infraestructura';

/**
 * Costos propone, Control de obra autoriza (plan de elementos de muro, fase I):
 *  1. El elemento que da de alta Costos queda pendiente (provisional); Control de obra lo autoriza en la tarjeta y nace la versión 1.
 *  2. El cambio de Costos sobre un elemento autorizado es una propuesta (202): no se aplica hasta que Control de obra la autoriza.
 *  3. El concepto nuevo propuesto no cuenta (no existe en el catálogo) hasta que Control de obra lo autoriza, sin precio.
 */

const ROLES_ZZ = ['control', 'costos'] as const;

test.describe('Cuantificador · autorización de elementos', () => {
  test.skip(!hayRoles(...ROLES_ZZ), motivoSinRoles(...ROLES_ZZ));
  test.setTimeout(120_000);

  test('Costos propone y Control de obra autoriza: elemento, cambio y concepto nuevo', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `AUT-${sufijo}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Autorización de elementos',
      archivo_url: 'planos/autorizacion-de-elementos.dwg',
    });

    // Costos da de alta un elemento: queda pendiente y se usa como provisional.
    const clave = `KA-${sufijo}`.slice(0, 20);
    const alto = 3.2 + (Date.now() % 1_000_000) / 1e7;
    const elemento = await llamarApi<{ id: string; estado_autorizacion: string }>(request, 'costos', 'POST', '/elementos-parametricos', {
      clave, nombre: 'Castillo propuesto', tipo: 'castillo', parametros: { alto },
    });
    expect(elemento.estado_autorizacion).toBe('pendiente');

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /^Trazos/ }).click();
    await page.getByRole('button', { name: `Ver ${clave}` }).click();
    const tarjeta = page.locator(`[data-autorizacion-del-elemento="${clave}"]`);

    // --- 1. El elemento nuevo --------------------------------------------------------------------------------------
    await expect(tarjeta.locator('[data-estado-de-autorizacion]')).toHaveAttribute('data-estado-de-autorizacion', 'pendiente');
    await tarjeta.getByRole('button', { name: 'Autorizar y crear v1' }).click();
    await expect(tarjeta.locator('[data-estado-de-autorizacion]')).toHaveAttribute('data-estado-de-autorizacion', 'autorizado');
    await expect(tarjeta.locator('[data-version-del-elemento]')).toHaveText('v1');

    // --- 2. El cambio que propone Costos ---------------------------------------------------------------------------
    const propuesta = await solicitarApi(request, 'costos', 'PATCH', `/elementos-parametricos/${elemento.id}`, { nombre: 'Castillo reforzado' });
    expect(propuesta.status()).toBe(202);
    const lista = () => llamarApi<{ id: string; clave: string; nombre: string; version_autorizada: number }[]>(request, 'control', 'GET', '/elementos-parametricos');
    expect((await lista()).find((e) => e.clave === clave)?.nombre).toBe('Castillo propuesto');
    await page.reload();
    await page.getByRole('tab', { name: /^Trazos/ }).click();
    await page.getByRole('button', { name: `Ver ${clave}` }).click();
    const pendiente = page.locator(`[data-autorizacion-del-elemento="${clave}"] [data-propuesta-pendiente="elemento"]`);
    await expect(pendiente).toContainText('Nombre: Castillo propuesto → Castillo reforzado');
    await pendiente.getByRole('button', { name: 'Autorizar' }).click();
    await expect.poll(async () => (await lista()).find((e) => e.clave === clave)?.nombre).toBe('Castillo reforzado');
    expect((await lista()).find((e) => e.clave === clave)?.version_autorizada).toBe(2);
    await expect(page.locator(`[data-autorizacion-del-elemento="${clave}"] [data-version-del-elemento]`)).toHaveText('v2');

    // --- 3. El concepto nuevo ---------------------------------------------------------------------------------------
    const claveNueva = `EJ-${sufijo}`.slice(0, 20);
    await llamarApi(request, 'costos', 'POST', `/elementos-parametricos/${elemento.id}/conceptos-por-contexto`, {
      clave_propuesta: claveNueva, descripcion: 'Castillo de entrepiso', unidad: 'ml', toma: { concreto: true },
    });
    expect(await llamarApi<unknown[]>(request, 'control', 'GET', `/elementos-parametricos/${elemento.id}/conceptos`)).toHaveLength(0);
    await page.reload();
    await page.getByRole('tab', { name: /^Trazos/ }).click();
    await page.getByRole('button', { name: `Ver ${clave}` }).click();
    const fila = page.locator(`[data-concepto-por-contexto="${claveNueva}"]`);
    await expect(fila).toContainText('No cuenta en el presupuesto hasta autorizarse');
    await fila.getByRole('button', { name: 'Autorizar concepto' }).click();
    await expect(fila.locator('[data-version-del-concepto]')).toHaveText('v1');
    await expect(fila).toHaveAttribute('data-estado', 'autorizado');
    expect(await llamarApi<unknown[]>(request, 'control', 'GET', `/elementos-parametricos/${elemento.id}/conceptos`)).toHaveLength(1);
  });
});
