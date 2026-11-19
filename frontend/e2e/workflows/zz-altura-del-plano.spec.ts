import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Desacople del plano del driver `altura_estandar`: el plano NO lo lee. La altura de un muro trazado sale del trazo, de su zona de losa,
 * de la ALTURA BASE del artefacto (la plantilla de muro elegida) o, sin plantilla, de la HERRAMIENTA (3.00 m). Q1: lo guardado la conserva.
 *
 * Aquí: cambiar el driver en el Paramétrico no cambia lo que propone el plano ni lo que mide un muro nuevo; cambiar la altura base de la
 * plantilla en el panel del Artefacto sí cambia lo que propone el siguiente muro; y un muro ya trazado no se mueve.
 */

const ROLES_Z = ['control'] as const;

test.describe('Cuantificador · altura del plano sin el driver', () => {
  test.skip(!hayRoles(...ROLES_Z), motivoSinRoles(...ROLES_Z));
  test.setTimeout(150_000);

  test('el driver no mueve la altura del plano; la altura base de la plantilla sí', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave: `ALT-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Altura del plano',
      archivo_url: 'planos/altura.dwg',
    });
    // Una plantilla (artefacto) con su altura base de 2.7 m.
    const nombre = `Altura base ${sufijo}`;
    await llamarApi(request, 'control', 'POST', '/muro-plantillas', {
      nombre, tipo: 'con_cadena', material: 'tabique_rojo', ubicacion: 'interior', altura_m: '2.7', partes: [], elementos: [],
    });

    type Trazos = { features: { id: string; geometry: { type: string }; properties: { enlaces: { enlace_id: string; cantidad: string; vigente: boolean }[] } }[] };
    const muros = async () => {
      const trazos = await llamarApi<Trazos>(request, 'control', 'GET', `/planos/${plano.id}/trazos`);
      const salida: { id: string; alt: number }[] = [];
      for (const f of trazos.features.filter((x) => x.geometry.type === 'LineString')) {
        const enlace = f.properties.enlaces.find((e) => e.vigente)!;
        const conv = await llamarApi<{ conversion: { alt: number } }>(request, 'control', 'GET', `/enlaces/${enlace.enlace_id}/conversion`);
        salida.push({ id: f.id, alt: conv.conversion.alt });
      }
      return salida;
    };

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });

    // --- 1. Cambiar el driver en el Paramétrico (2.2 m para ESTA obra) -------------------------------------------------------
    await pestanas.getByRole('tab', { name: /^Paramétrico/ }).click();
    const tabla = page.locator('#area-parametrico').getByRole('table', { name: 'Drivers del Paramétrico' });
    const fila = tabla.locator('tr[data-driver="altura_estandar"]');
    await fila.getByLabel(/^Valor de la obra para/).fill('2.2');
    await fila.getByLabel(/^Valor de la obra para/).press('Enter');
    await expect(fila.locator('[data-vigente]')).toHaveText('2.2');

    // --- 2. El plano propone 3.00 m (la herramienta), no 2.2 m del driver -----------------------------------------------------
    await pestanas.getByRole('tab', { name: /^Trazos/ }).click();
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = await cajaEstable(page, lienzo);
    const clic = (fx: number, fy: number) => page.mouse.click(c.x + c.width * fx, c.y + c.height * fy);
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    await expect(page.getByLabel('Altura (m)')).toHaveValue('3');
    await clic(0.68, 0.85);
    await clic(0.9, 0.85);
    await expect(page.getByRole('status')).toContainText('(o 3 m si no cae bajo ninguna)');
    await expect.poll(async () => (await muros()).length).toBe(1);
    const primero = (await muros())[0]!;
    expect(primero.alt).toBeCloseTo(3, 6);

    // --- 3. Con una plantilla elegida, el panel propone su altura base y el muro nace con ella --------------------------------
    await page.getByRole('button', { name: '0.15 m' }).click();
    await page.getByRole('group', { name: 'Tipo de muro' }).getByRole('button', { name: 'Con cadena' }).click();
    await page.getByLabel('Plantilla del muro nuevo').selectOption({ label: `${nombre} · v1 (por validar)` });
    await expect(page.getByLabel('Altura (m)')).toHaveValue('2.7');
    await clic(0.68, 0.7);
    await clic(0.9, 0.7);
    await expect.poll(async () => (await muros()).length).toBe(2);
    const conPlantilla = (await muros()).find((m) => m.id !== primero.id)!;
    expect(conPlantilla.alt).toBeCloseTo(2.7, 6);

    // --- 4. Editar la altura base de la plantilla en el panel del Artefacto cambia lo que propone el plano ---------------------
    await pestanas.getByRole('tab', { name: /^Artefacto/ }).click();
    const area = page.getByRole('region', { name: 'Artefacto', exact: true });
    await page.getByRole('navigation', { name: 'Plantillas de muro' }).getByRole('button', { name: new RegExp(nombre) }).click();
    await area.getByLabel('Altura de la plantilla (m)').fill('3.4');
    await area.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(area.getByLabel('Altura de la plantilla (m)')).toHaveValue('3.4');
    await pestanas.getByRole('tab', { name: /^Trazos/ }).click();
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    await page.getByLabel('Plantilla del muro nuevo').selectOption({ label: `${nombre} · v1 (por validar)` });
    await expect(page.getByLabel('Altura (m)')).toHaveValue('3.4');

    // --- 5. Q1: lo ya trazado conserva su altura, cambie lo que cambie ---------------------------------------------------------
    await llamarApi(request, 'control', 'PUT', `/obras/${obra.id}/drivers/altura_estandar`, { valor: '3.9' });
    const despues = await muros();
    expect(despues.find((m) => m.id === primero.id)!.alt).toBeCloseTo(3, 6);
    expect(despues.find((m) => m.id === conPlantilla.id)!.alt).toBeCloseTo(2.7, 6);
  });
});
