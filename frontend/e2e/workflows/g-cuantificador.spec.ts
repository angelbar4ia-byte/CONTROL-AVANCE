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
 * Cuantificador · trazar sobre un plano y ver la cantidad en la obra
 * (cerebro MODELO.md §1b: plano → trazo → enlace → cantidad).
 *
 *  1. El residente abre el cuantificador, elige la obra y su plano.
 *  2. Dibuja un polígono con cuatro clics y lo termina con Enter.
 *  3. Lo enlaza al Área de una actividad y lo guarda.
 *  4. La cantidad medida aparece en la tabla de la obra, y el servidor
 *     (PostGIS) coincide: el visor no calcula nada.
 *  5. Un clic dentro del polígono lo elige y muestra su enlace; recargar la
 *     página no lo pierde.
 *
 * El plano se registra con un `archivo_url` que no es imagen a propósito: así
 * el visor traza sobre su rejilla y la prueba no depende de R2 (en CI no hay).
 *
 * Usa `OBRA-G` de `e2e/soporte/semilla.sql`; es de un solo uso (cada prueba
 * registra su propio plano y lo elige por nombre, así no dependen del orden).
 */

const ROLES_G = ['residente'] as const;

test.describe('Cuantificador · trazar un polígono', () => {
  test.skip(!hayRoles(...ROLES_G), motivoSinRoles(...ROLES_G));
  test.setTimeout(90_000);

  test('un polígono enlazado a una actividad suma su área a la obra', async ({
    page,
    request,
  }) => {
    const obras = await llamarApi<{ id: string; clave: string }[]>(
      request,
      'residente',
      'GET',
      '/obras',
    );
    const obra = obras.find((o) => o.clave === 'OBRA-G');
    expect(obra, 'OBRA-G existe (¿se sembró?)').toBeDefined();
    await llamarApi(request, 'residente', 'POST', `/obras/${obra!.id}/planos`, {
      nombre: 'Planta baja E2E',
      archivo_url: 'e2e/planta-baja.pdf',
    });

    // --- 1. Abrir el cuantificador -------------------------------------
    await entrarComo(page, 'residente');
    await page.goto('/cuantificador');
    await page.getByLabel('Obra', { exact: true }).selectOption({ label: 'OBRA-G' });
    await page.getByLabel('Plano', { exact: true }).selectOption({ label: 'Planta baja E2E · v1' });

    // --- 2. Dibujar -----------------------------------------------------
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(lienzo).toBeVisible();
    const caja = (await lienzo.boundingBox())!;
    const en = (fx: number, fy: number) => ({
      x: caja.x + caja.width * fx,
      y: caja.y + caja.height * fy,
    });

    await page.getByRole('button', { name: 'Polígono', exact: true }).click();
    // Dos vértices no cierran un polígono: Enter no abre el formulario.
    for (const [fx, fy] of [
      [0.3, 0.3],
      [0.7, 0.3],
    ] as const) {
      await page.mouse.click(en(fx, fy).x, en(fx, fy).y);
    }
    await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog')).toHaveCount(0);

    for (const [fx, fy] of [
      [0.7, 0.7],
      [0.3, 0.7],
    ] as const) {
      await page.mouse.click(en(fx, fy).x, en(fx, fy).y);
    }
    await expect(page.getByText('4 vértices')).toBeVisible();
    await page.keyboard.press('Enter');

    // --- 3. Enlazar y guardar ------------------------------------------
    const alta = page.getByRole('dialog', { name: 'Guardar polígono' });
    const valorActividad = await alta
      .locator('#enlace-actividad-0 option', { hasText: 'E2E-EXC' })
      .getAttribute('value');
    await alta.getByLabel('Actividad 1').selectOption(valorActividad!);
    await alta.getByLabel('Medida').selectOption('area');
    await alta.getByRole('button', { name: 'Guardar trazo' }).click();

    // --- 4. La cantidad llega a la obra --------------------------------
    await expect(page.getByRole('status')).toContainText('Trazo guardado');
    const filas = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
      request,
      'residente',
      'GET',
      `/obras/${obra!.id}/cuantificacion`,
    );
    const actividadId = await actividadDe(request, 'residente', 'OBRA-G', 'E2E-EXC');
    const nodo = filas.find((n) => n.nodo_id === actividadId);
    expect(nodo, 'la actividad enlazada aparece en la cuantificación').toBeDefined();
    expect(Number(nodo!.cantidad_medida)).toBeGreaterThan(0);

    const tabla = page.getByRole('row', { name: /Excavación de cepas/ });
    await expect(tabla).toBeVisible();

    // --- 5. Elegirlo con un clic y que sobreviva a recargar -------------
    await page.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await page.mouse.click(en(0.5, 0.5).x, en(0.5, 0.5).y);
    await expect(page.getByText('Trazo elegido')).toBeVisible();
    await expect(page.getByRole('cell', { name: /Área × 1/ })).toBeVisible();

    await page.reload();
    await page.getByLabel('Obra', { exact: true }).selectOption({ label: 'OBRA-G' });
    await expect(page.locator('.visor__trazo')).toHaveCount(1);
  });

  test('un plano que es imagen se pinta de fondo y el visor encuadra a su tamaño', async ({
    page,
    request,
  }) => {
    const obras = await llamarApi<{ id: string; clave: string }[]>(
      request,
      'residente',
      'GET',
      '/obras',
    );
    const obra = obras.find((o) => o.clave === 'OBRA-G')!;
    await llamarApi(request, 'residente', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Plano con imagen',
      archivo_url: 'e2e/fachada.png',
    });

    // R2 no existe en CI: se simula la URL firmada y el archivo que serviría.
    // La imagen mide 400×200 y las coordenadas del plano son las suyas.
    await page.route('**/api/v1/planos/*/archivo', (ruta) =>
      ruta.fulfill({
        json: {
          url: 'http://127.0.0.1:5173/__e2e/fachada.svg',
          expira_en_segundos: 900,
          expira_en: new Date(Date.now() + 900_000).toISOString(),
        },
      }),
    );
    await page.route('**/__e2e/fachada.svg', (ruta) =>
      ruta.fulfill({
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><rect width="400" height="200" fill="#ddd"/></svg>',
      }),
    );

    await entrarComo(page, 'residente');
    await page.goto('/cuantificador');
    await page.getByLabel('Obra', { exact: true }).selectOption({ label: 'OBRA-G' });
    await page.getByLabel('Plano', { exact: true }).selectOption({ label: 'Plano con imagen · v1' });

    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(lienzo.locator('image')).toHaveAttribute('width', '400');
    await expect(lienzo).toHaveAttribute('viewBox', '0 0 400 200');
  });
});
