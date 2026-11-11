import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * El paramétrico de muro (F-22): el muro nace con el tipo y el acabado que se eligen en el panel de la línea, y el tipo se
 * cambia después en el detalle del trazo (confinado ↔ con cadena ↔ tabique). Solo clasifica: lo que mide es lo mismo.
 */

const ROLES_ZZ = ['control'] as const;

test.describe('Cuantificador · paramétrico de muro', () => {
  test.skip(!hayRoles(...ROLES_ZZ), motivoSinRoles(...ROLES_ZZ));
  test.setTimeout(120_000);

  test('un muro nace clasificado y su tipo se cambia en el detalle', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `MUR-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Muros',
      archivo_url: 'planos/muros.dwg',
    });
    const trazos = async () =>
      (await llamarApi<{ features: { properties: Record<string, unknown> }[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features;

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = (await lienzo.boundingBox())!;

    // Con grosor (un muro) aparece «Tipo de muro»; se elige con cadena y se quita la pintura de la fachada.
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    await page.getByRole('button', { name: '0.15 m' }).click();
    const tipo = page.getByRole('group', { name: 'Tipo de muro' });
    await expect(tipo).toBeVisible();
    await tipo.getByRole('button', { name: 'Con cadena' }).click();
    await page.getByRole('checkbox', { name: 'Pintura, fachada' }).uncheck();

    await page.mouse.click(c.x + c.width * 0.55, c.y + c.height * 0.6);
    await page.mouse.click(c.x + c.width * 0.9, c.y + c.height * 0.6);
    await expect.poll(async () => (await trazos()).length).toBe(1);

    // Nació clasificado.
    await expect.poll(async () => (await trazos())[0]!.properties.muro_tipo).toBe('con_cadena');
    const acabado = (await trazos())[0]!.properties.muro_acabado as Record<string, Record<string, boolean>>;
    expect(acabado.fachada).toEqual({ gris: true, blanca: true, pintura: false });
    expect(acabado.interior).toEqual({ gris: true, blanca: true, pintura: true });

    // En el detalle se cambia a tabique.
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const caja = (await page.locator('.visor__trazo').first().boundingBox())!;
    await page.mouse.click(caja.x + caja.width / 2, caja.y + caja.height / 2);
    const detalle = page.getByRole('group', { name: 'Tipo de muro' }).last();
    await expect(detalle.getByRole('button', { name: 'Con cadena' })).toHaveAttribute('aria-pressed', 'true');
    await detalle.getByRole('button', { name: 'Tabique' }).click();
    await expect.poll(async () => (await trazos())[0]!.properties.muro_tipo).toBe('tabique');

    // --- Revestimiento: un concepto del catálogo con su largo y su altura (D-645, tanda 2) ------------------------------
    const muroId = (await llamarApi<{ features: { id: string }[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features[0]!.id;
    const revestimientos = page.getByRole('group', { name: 'Revestimientos del muro' });
    await expect(revestimientos).toContainText('Sin revestimientos');
    await revestimientos.getByRole('button', { name: '+ Revestimiento' }).click();
    const alta = revestimientos.getByRole('group', { name: 'Revestimiento nuevo' });
    await alta.getByLabel('Concepto del revestimiento').selectOption({ index: 1 }); // el primer concepto en m² de la obra
    await alta.getByRole('button', { name: 'Fachada' }).click();
    const altura = alta.getByLabel('Altura del revestimiento (m)');
    await altura.fill('');
    await altura.pressSequentially('2.1');
    await alta.getByRole('button', { name: 'Dibujar el largo' }).click();
    await expect(revestimientos.getByRole('status')).toContainText('Dibuja el largo');

    // Se dibuja el largo sobre el muro: dos clics sobre su recorrido (en la parte que el panel de opciones no tapa).
    const sobre = (await page.locator('.visor__trazo').first().boundingBox())!;
    const y = sobre.y + sobre.height / 2;
    await page.mouse.click(sobre.x + sobre.width * 0.62, y);
    await page.mouse.click(sobre.x + sobre.width * 0.9, y);
    await expect.poll(async () => (await trazos()).length).toBe(2);

    const hijo = (await llamarApi<{ features: { id: string; geometry: { coordinates: number[][] }; properties: Record<string, unknown> }[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features.find(
      (f) => f.properties.revestimiento_de === muroId,
    )!;
    expect(hijo.properties.revestimiento_cara).toBe('fachada');
    const largo = Math.hypot(hijo.geometry.coordinates[1]![0]! - hijo.geometry.coordinates[0]![0]!, hijo.geometry.coordinates[1]![1]! - hijo.geometry.coordinates[0]![1]!);
    const enlace = (hijo.properties.enlaces as { cantidad: string }[])[0]!;
    expect(Number(enlace.cantidad)).toBeCloseTo(largo * 2.1, 2); // largo × altura, en m²
    await expect(revestimientos.locator('[data-revestimiento]')).toHaveCount(1);
    if (process.env.E2E_CAPTURAS) await page.screenshot({ path: `${process.env.E2E_CAPTURAS}/paramerico-muro.png` });

    // Se quita: el revestimiento deja de existir y el muro sigue.
    await revestimientos.getByRole('button', { name: /^Quitar el revestimiento/ }).click();
    await expect.poll(async () => (await trazos()).length).toBe(1);
  });
});
