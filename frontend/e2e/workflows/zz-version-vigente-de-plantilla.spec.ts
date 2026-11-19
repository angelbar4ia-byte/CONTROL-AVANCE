import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, pulsarMarca, test } from '../infraestructura';

/**
 * C4: un muro ya medido conserva la versión de la plantilla que eligió (Q9). Si la plantilla cambió después, la ventana del muro lo dice y
 * ofrece «Actualizar a la versión vigente» (con el aviso de qué cambia) o «Eliminar el trazo».
 *
 * Una plantilla de tabique sin elementos solo trae avisos al validarla (se aceptan con casilla): una parte sin concepto del catálogo
 * bloquearía la validación (C3), y aquí no se prueba eso.
 */

const ROLES_ZZ = ['control'] as const;

test.describe('Cuantificador · versión vigente de la plantilla', () => {
  test.skip(!hayRoles(...ROLES_ZZ), motivoSinRoles(...ROLES_ZZ));
  test.setTimeout(180_000);

  test('un muro con una versión anterior se actualiza a la vigente o se elimina el trazo', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const partes = [{ nombre: 'Cuerpo', desde_m: '0', hasta_m: '3', rol: 'cuerpo' }];
    const base = { nombre: `Versionada ${sufijo}`, tipo: 'tabique', material: 'tabique_rojo', ubicacion: 'interior', partes, elementos: [] };
    const v1 = await llamarApi<{ id: string }>(request, 'control', 'POST', '/muro-plantillas', base);
    await llamarApi(request, 'control', 'POST', `/muro-plantillas/${v1.id}/validar`, { aceptar_alertas: true });
    // Cambiar una plantilla ya validada crea la versión 2; el trazo que ya usa la 1 la conserva.
    const v2 = await llamarApi<{ id: string; version: number; version_nueva: boolean }>(request, 'control', 'PUT', `/muro-plantillas/${v1.id}`, {
      ...base,
      altura_m: '2.8',
    });
    expect([v2.version, v2.version_nueva]).toEqual([2, true]);

    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `VVP-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Versión vigente',
      archivo_url: 'planos/version-vigente.dwg',
    });
    const trazar = async (wkt: string) =>
      (
        await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
          version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, grosor_m: '0.15', alineacion: 'centro',
          enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad!.id, conversion: { modo: 'area', mide: 'eje' } }],
        })
      ).trazo_id;
    const muro = await trazar('LINESTRING(0 0, 10 0)');
    await llamarApi(request, 'control', 'PUT', `/trazos/${muro}/muro/plantilla`, { plantilla_id: v1.id });
    const clasificacion = async () =>
      llamarApi<{ plantilla_id: string | null }>(request, 'control', 'GET', `/trazos/${muro}/muro/clasificacion`);
    expect((await clasificacion()).plantilla_id).toBe(v1.id);

    await page.setViewportSize({ width: 1400, height: 1100 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await cajaEstable(page, lienzo);
    await pulsarMarca(page, page.locator('.visor__trazo').first());

    // --- 1. Hay una versión nueva: se dice, con las dos salidas ---------------------------------------------------------------------
    const aviso = page.getByTestId('version-nueva-de-plantilla');
    await expect(aviso).toBeVisible();
    await expect(aviso).toContainText('versión 1');
    await expect(aviso).toContainText('la vigente es la versión 2');
    await expect(aviso.getByRole('button', { name: 'Eliminar el trazo' })).toBeVisible();

    // --- 2. Actualizar a la vigente: dice qué cambia, cancelar no cambia nada --------------------------------------------------------
    await aviso.getByRole('button', { name: 'Actualizar a la versión vigente' }).click();
    const cambio = page.getByRole('region', { name: 'Cambiar de plantilla' });
    await expect(cambio).toBeVisible();
    await expect(cambio).toContainText('medición del muro');
    await cambio.getByRole('button', { name: 'Cancelar' }).click();
    await expect(cambio).toHaveCount(0);
    expect((await clasificacion()).plantilla_id).toBe(v1.id);

    await aviso.getByRole('button', { name: 'Actualizar a la versión vigente' }).click();
    await cambio.getByRole('button', { name: 'Cambiar de plantilla' }).click();
    await expect.poll(async () => (await clasificacion()).plantilla_id).toBe(v2.id);
    await expect(aviso).toHaveCount(0); // ya usa la vigente: no queda nada que ofrecer

    // --- 3. La otra salida: eliminar el trazo desde la misma ventana -----------------------------------------------------------------
    // La plantilla vuelve a cambiar (la 2 ya estaba por validar: se valida y su cambio crea la 3), así que el muro queda con una anterior.
    await llamarApi(request, 'control', 'POST', `/muro-plantillas/${v2.id}/validar`, { aceptar_alertas: true });
    const v3 = await llamarApi<{ id: string; version: number }>(request, 'control', 'PUT', `/muro-plantillas/${v2.id}`, { ...base, altura_m: '2.5' });
    expect(v3.version).toBe(3);
    await page.reload();
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await cajaEstable(page, lienzo);
    await pulsarMarca(page, page.locator('.visor__trazo').first());
    await expect(aviso).toBeVisible();
    await aviso.getByRole('button', { name: 'Eliminar el trazo' }).click();
    await page.getByRole('button', { name: 'Borrar trazo' }).click();
    await expect.poll(async () => {
      const trazos = await llamarApi<{ features: { id: string }[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`);
      return trazos.features.length;
    }).toBe(0);
  });
});
