import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * La pestaña «Árbol» (entrega 7): se arma la estructura desde el cuantificador.
 *
 *  1. Control crea un nivel, una etapa dentro de él y, en la etapa, una partida con un concepto que ya existe.
 *  2. La partida llega sin cantidad; se cambia su unidad y con ella el tipo de medición (sin botón de guardar).
 *  3. Se crea un concepto nuevo como partida de la misma etapa y se mueve de etapa.
 *  4. El residente no ve la pestaña.
 */

const ROLES_ZG = ['control', 'residente'] as const;

test.describe('Cuantificador · árbol editable', () => {
  test.skip(!hayRoles(...ROLES_ZG), motivoSinRoles(...ROLES_ZG));
  test.setTimeout(150_000);

  test('se crean niveles, etapas y partidas y se cambia la unidad', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave: `ARB-${sufijo}`,
    });
    await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/generar`, { modo_pago: 'destajo' });
    const unidades = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/unidades');
    const concepto = await llamarApi<{ id: string }>(request, 'control', 'POST', '/conceptos', {
      tipo: 'concepto',
      clave: `FIR-${sufijo}`,
      descripcion: 'Firme de concreto',
      unidad_id: unidades.find((u) => u.clave === 'm2')!.id,
    });
    const partidas = async () =>
      llamarApi<{ concepto_clave: string; unidad: string | null; cant_base: string; etapa_clave: string | null }[]>(
        request,
        'control',
        'GET',
        `/obras/${obra.id}/actividades`,
      );

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}`);
    await page.getByRole('tab', { name: 'Árbol' }).click();
    const arbol = page.getByRole('region', { name: 'Armar el árbol' });

    // --- 1. Nivel, etapa y partida ---------------------------------------------------------------------------
    await arbol.getByRole('button', { name: 'Nuevo nivel' }).click();
    await arbol.getByLabel('Nuevo nivel: Clave').fill(`NV${sufijo}`);
    await arbol.getByLabel('Nuevo nivel: Descripción').fill('Planta de prueba');
    await arbol.getByLabel('Nuevo nivel: Descripción').press('Enter');
    const nivel = arbol.locator(`[data-nivel="NV${sufijo}"]`);
    await expect(nivel).toBeVisible();

    await nivel.getByRole('button', { name: `Nueva etapa en NV${sufijo}` }).click();
    await nivel.getByLabel(`Nueva etapa en NV${sufijo}: Clave`).fill(`ET${sufijo}`);
    await nivel.getByLabel(`Nueva etapa en NV${sufijo}: Descripción`).fill('Etapa de prueba');
    await nivel.getByLabel(`Nueva etapa en NV${sufijo}: Descripción`).press('Enter');
    const etapa = arbol.locator(`[data-etapa="ET${sufijo}"]`);
    await expect(etapa).toBeVisible();

    await etapa.getByRole('button', { name: 'Agregar partida' }).click();
    await etapa.getByLabel('Concepto de la partida (clave)').fill(`FIR-${sufijo}`);
    await etapa.getByLabel('Concepto de la partida (clave)').press('Enter');
    const partida = arbol.locator(`[data-partida="FIR-${sufijo}"]`);
    await expect(partida).toBeVisible({ timeout: 15_000 }); // espera a la API; el runner de CI es lento
    await expect.poll(async () => (await partidas()).find((p) => p.concepto_clave === `FIR-${sufijo}`)?.etapa_clave).toBe(`ET${sufijo}`);
    expect(Number((await partidas()).find((p) => p.concepto_clave === `FIR-${sufijo}`)!.cant_base)).toBe(0);

    // --- 2. Cambiar la unidad cambia cómo se mide --------------------------------------------------------------
    await expect(partida).toContainText('Área');
    await partida.getByLabel(`Unidad de FIR-${sufijo}`).selectOption({ label: 'pza' });
    await expect(partida).toContainText('Conteo');
    await expect.poll(async () => (await partidas()).find((p) => p.concepto_clave === `FIR-${sufijo}`)?.unidad).toBe('pza');

    // --- 3. Un concepto nuevo como partida, y moverlo de etapa -------------------------------------------------
    await etapa.getByRole('button', { name: 'Agregar partida' }).click();
    await etapa.getByLabel('Concepto de la partida (clave)').fill(`NUE-${sufijo}`);
    await etapa.getByLabel('Descripción del concepto nuevo').fill('Concepto creado aquí');
    const unidadNueva = etapa.getByLabel('Unidad del concepto nuevo');
    await unidadNueva.selectOption({ label: (await unidadNueva.locator('option').allTextContents()).find((t) => t.startsWith('ml ·'))! });
    const nueva = arbol.locator(`[data-partida="NUE-${sufijo}"]`);
    await expect(nueva).toBeVisible();
    await expect(nueva).toContainText('Lineal');
    await nueva.getByLabel(`Mover NUE-${sufijo} a`).selectOption('__sin_etapa__');
    await expect(arbol.getByRole('list', { name: 'Partidas sin etapa' }).locator(`[data-partida="NUE-${sufijo}"]`)).toBeVisible();

    // --- 4. El residente no ve la pestaña --------------------------------------------------------------------------
    const res = await page.context().browser()!.newContext();
    const pagina = await res.newPage();
    await entrarComo(pagina, 'residente');
    await pagina.goto(`/cuantificador?obra=${obra.id}`);
    await expect(pagina.getByRole('tab', { name: 'Presupuesto' })).toBeVisible();
    await expect(pagina.getByRole('tab', { name: 'Árbol' })).toHaveCount(0);
  });
});
