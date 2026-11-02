import {
  actividadDe,
  entrarComo,
  expect,
  hayRoles,
  llamarApi,
  motivoSinRoles,
  test,
} from '../infraestructura';

/**
 * Cuantificador · la herramienta puntual: una ventana flotante sobre la
 * actividad (cerebro WORKFLOWS.md, D-532).
 *
 *  1. Desde Avances, «Medir» abre la ventana con el renglón de la actividad.
 *  2. Se traza un polígono; el formulario ya trae la actividad elegida y, al
 *     guardar, el «medido» del renglón se actualiza sin salir de la pantalla.
 *  3. La ventana se minimiza sin perder lo hecho y se puede arrastrar.
 *  4. Solo hay una ventana a la vez: medir otra actividad sustituye a la actual.
 *  5. «Abrir en el módulo» lleva el mismo plano y la misma actividad, con lo
 *     ya trazado.
 *
 * Usa `OBRA-H` de `e2e/soporte/semilla.sql`; es de un solo uso.
 */

const ROLES_H = ['residente'] as const;

test.describe('Cuantificador · ventana flotante', () => {
  test.skip(!hayRoles(...ROLES_H), motivoSinRoles(...ROLES_H));
  test.setTimeout(90_000);

  test('medir una actividad sin salir de Avances y abrirla luego en el módulo', async ({
    page,
    request,
  }) => {
    const obras = await llamarApi<{ id: string; clave: string }[]>(
      request,
      'residente',
      'GET',
      '/obras',
    );
    const obra = obras.find((o) => o.clave === 'OBRA-H');
    expect(obra, 'OBRA-H existe (¿se sembró?)').toBeDefined();
    const plano = await llamarApi<{ id: string }>(
      request,
      'residente',
      'POST',
      `/obras/${obra!.id}/planos`,
      { nombre: 'Plano de la ventana', archivo_url: 'e2e/ventana.dwg' },
    );
    const actividadPla = await actividadDe(request, 'residente', 'OBRA-H', 'E2E-PLA');

    // --- 1. Abrir desde Avances ----------------------------------------
    await entrarComo(page, 'residente');
    await page.goto('/avances');
    await page.getByLabel('Obra', { exact: true }).selectOption({ label: 'OBRA-H' });
    await page.getByRole('tab', { name: /^Todas/ }).click();
    await page
      .getByRole('row', { name: /^E2E-PLA Plantilla de concreto/ })
      .getByRole('button', { name: 'Medir' })
      .click();

    const ventana = page.getByRole('dialog', { name: 'Cuantificador' });
    await expect(ventana).toBeVisible();
    const renglon = ventana.getByTestId('renglon-foco');
    await expect(renglon).toContainText('E2E-PLA');
    await expect(ventana.getByTestId('medido-foco')).toHaveText('—');

    // --- 2. Trazar y ver el renglón actualizarse ------------------------
    const lienzo = ventana.getByRole('img', { name: 'Plano con sus trazos' });
    await lienzo.scrollIntoViewIfNeeded();
    const caja = (await lienzo.boundingBox())!;
    await ventana.getByRole('button', { name: 'Polígono', exact: true }).click();
    for (const [fx, fy] of [
      [0.3, 0.2],
      [0.7, 0.2],
      [0.7, 0.6],
      [0.3, 0.6],
    ] as const) {
      await page.mouse.click(caja.x + caja.width * fx, caja.y + caja.height * fy);
    }
    await page.keyboard.press('Enter');

    // La herramienta puntual ya sabe sobre qué actividad se mide: el trazo se guarda solo, sin cajón.
    await expect(page.getByRole('dialog', { name: 'Guardar polígono' })).toBeHidden();

    await expect(ventana.getByTestId('medido-foco')).not.toHaveText('—');

    // --- 3. Minimizar sin perder nada, y arrastrar -----------------------
    await ventana.getByRole('button', { name: 'Minimizar ventana' }).click();
    await expect(lienzo).toBeHidden();
    await ventana.getByRole('button', { name: 'Restaurar ventana' }).click();
    await expect(lienzo).toBeVisible();
    await expect(ventana.getByTestId('medido-foco')).not.toHaveText('—');

    const antes = (await ventana.boundingBox())!;
    const encabezado = ventana.locator('.ventana-cuant__encabezado');
    const cb = (await encabezado.boundingBox())!;
    await page.mouse.move(cb.x + 40, cb.y + cb.height / 2);
    await page.mouse.down();
    await page.mouse.move(cb.x - 160, cb.y + cb.height / 2 + 30, { steps: 5 });
    await page.mouse.up();
    const despues = (await ventana.boundingBox())!;
    expect(despues.x).toBeLessThan(antes.x - 100);

    // --- 4. Una sola ventana a la vez ----------------------------------
    await page
      .getByRole('row', { name: /^E2E-EXC Excavación de cepas/ })
      .getByRole('button', { name: 'Medir' })
      .click();
    await expect(page.getByRole('dialog', { name: 'Cuantificador' })).toHaveCount(1);
    await expect(page.getByTestId('renglon-foco')).toContainText('E2E-EXC');

    // --- 5. Abrir en el módulo con el mismo plano y lo ya trazado -------
    await page.getByRole('button', { name: 'Abrir en el módulo' }).click();
    await expect(page).toHaveURL(/\/cuantificador\?/);
    const url = new URL(page.url());
    expect(url.searchParams.get('obra')).toBe(obra!.id);
    expect(url.searchParams.get('plano')).toBe(plano.id);
    await expect(page.getByRole('dialog', { name: 'Cuantificador' })).toHaveCount(0);
    await expect(page.getByLabel('Plano', { exact: true })).toHaveValue(plano.id);
    await expect(page.locator('.visor__trazo')).toHaveCount(1);
  });
});
