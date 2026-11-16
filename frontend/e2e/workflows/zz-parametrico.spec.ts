import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, solicitarApi, test } from '../infraestructura';

/**
 * La pestaña Paramétrico: drivers (global, por obra, mixto) y enlace de ranuras con el árbol de la obra (Ola 4B).
 *
 *  1. La tabla trae los 14 drivers; un driver fijo no se ajusta por obra.
 *  2. Control de obra ajusta la altura estándar de SU obra: el vigente y el origen cambian, el global no; vaciar el campo la devuelve al global.
 *  3. Cambiar un driver global lo guarda (y se restaura al final: la organización es compartida por todos los specs).
 *  4. Enlazar una ranura con un concepto que está en el árbol cuenta; con uno que el árbol no trae avisa y no cuenta; un concepto que no existe se rechaza.
 *  5. Quitar un enlace. Costos también edita; el residente no (la API responde 403).
 */

const ROLES = ['control', 'costos', 'residente'] as const;

interface Driver {
  clave: string;
  valor_global: string;
  valor_obra: string | null;
  valor_vigente: string;
  origen: string;
  modo: string;
}
interface Enlaces {
  enlaces: { id: string; ranura: string; estado: string; cuenta: boolean; concepto_clave: string }[];
  partidas_del_arbol: number;
}

test.describe('Cuantificador · pestaña Paramétrico', () => {
  test.skip(!hayRoles(...ROLES), motivoSinRoles(...ROLES));
  test.setTimeout(150_000);

  test('drivers por obra y enlace de ranuras con el árbol, con sus permisos', async ({ page, browser, request }) => {
    const clave = `PAR-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Paramétrico',
      archivo_url: 'planos/parametrico.dwg',
    });
    const drivers = async () =>
      Object.fromEntries((await llamarApi<Driver[]>(request, 'control', 'GET', `/obras/${obra.id}/drivers`)).map((d) => [d.clave, d]));
    const enlaces = () => llamarApi<Enlaces>(request, 'control', 'GET', `/obras/${obra.id}/enlaces-de-ranura`);

    const url = `/cuantificador?obra=${obra.id}&plano=${plano.id}`;
    await entrarComo(page, 'control');
    await page.goto(url);
    await page.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Paramétrico/ }).click();
    const area = page.locator('#area-parametrico');
    const tabla = area.getByRole('table', { name: 'Drivers del Paramétrico' });

    // --- 1. Los drivers -------------------------------------------------------------------------------------------------
    await expect(tabla.locator('tr[data-driver]')).toHaveCount(14);
    const escarpio = tabla.locator('tr[data-driver="escarpio_minimo"]');
    await expect(escarpio.getByLabel(/^Valor de la obra para/)).toBeDisabled();
    await expect(escarpio.getByText('por confirmar', { exact: true })).toBeVisible();

    // --- 2. El ajuste de la obra ----------------------------------------------------------------------------------------
    const altura = tabla.locator('tr[data-driver="altura_estandar"]');
    const global = (await drivers()).altura_estandar!.valor_global;
    await expect(altura.locator('[data-vigente]')).toHaveText(global);
    await altura.getByLabel(/^Valor de la obra para/).fill('2.6');
    await altura.getByLabel(/^Valor de la obra para/).press('Enter');
    await expect(altura.locator('[data-vigente]')).toHaveText('2.6');
    await expect(altura.getByText('obra', { exact: true })).toBeVisible();
    const ajustada = (await drivers()).altura_estandar!;
    expect([ajustada.valor_obra, ajustada.valor_vigente, ajustada.origen, ajustada.valor_global]).toEqual(['2.6', '2.6', 'obra', global]);
    await altura.getByLabel(/^Valor de la obra para/).fill('');
    await altura.getByLabel(/^Valor de la obra para/).press('Enter');
    await expect(altura.locator('[data-vigente]')).toHaveText(global);
    expect((await drivers()).altura_estandar!.valor_obra).toBeNull();

    // --- 3. Un driver global (y se restaura) -----------------------------------------------------------------------------
    const puntas = tabla.locator('tr[data-driver="puntas_armex_cm"]');
    const antes = (await drivers()).puntas_armex_cm!.valor_global;
    try {
      await puntas.getByLabel(/^Valor global de/).fill('55');
      await puntas.getByLabel(/^Valor global de/).press('Enter');
      await expect.poll(async () => (await drivers()).puntas_armex_cm!.valor_global).toBe('55');
      await expect(puntas.locator('[data-vigente]')).toHaveText('55');
    } finally {
      await llamarApi(request, 'control', 'PUT', '/drivers/puntas_armex_cm', { valor: antes });
    }
    expect((await drivers()).puntas_armex_cm!.valor_global).toBe(antes);

    // --- 4. El enlace de ranuras ----------------------------------------------------------------------------------------
    expect((await enlaces()).partidas_del_arbol).toBeGreaterThanOrEqual(3);
    const form = area.getByRole('group', { name: 'Enlazar una ranura' });
    await form.getByLabel('Ranura', { exact: true }).selectOption('acabado:gris:exterior');
    await form.getByLabel('Concepto (clave del catálogo)').fill('E2E-CIM');
    await form.getByRole('button', { name: 'Enlazar' }).click();
    const tablaEnlaces = area.getByRole('table', { name: 'Enlaces de ranura de la obra' });
    const bueno = tablaEnlaces.locator('tr[data-enlace="acabado:gris:exterior"]');
    await expect(bueno).toHaveAttribute('data-estado', 'enlazado');
    await expect(bueno).toContainText('E2E-CIM');

    await form.getByLabel('Qué se enlaza').selectOption('elemento');
    await form.getByLabel('Elemento', { exact: true }).selectOption('K-1');
    await form.getByLabel('Concepto (clave del catálogo)').fill('MTZ-LOSA'); // existe en el catálogo, no en el árbol
    await form.getByLabel('Ubicación').selectOption('barda');
    await form.getByRole('button', { name: 'Enlazar' }).click();
    const falta = tablaEnlaces.locator('tr[data-enlace="elemento:K-1:acero"]');
    await expect(falta).toHaveAttribute('data-estado', 'falta_partida');
    await expect(falta).toContainText('no cuenta');
    await expect(area.getByRole('status')).toContainText('1 enlace no cuenta');
    const lista = (await enlaces()).enlaces;
    expect(lista.map((e) => [e.ranura, e.estado, e.cuenta])).toEqual(
      expect.arrayContaining([
        ['acabado:gris:exterior', 'enlazado', true],
        ['elemento:K-1:acero', 'falta_partida', false],
      ]),
    );

    // Un concepto que no existe en el catálogo no se inventa.
    await form.getByLabel('Concepto (clave del catálogo)').fill('EJ-101');
    await form.getByLabel('Ubicación').selectOption('pretil');
    await form.getByRole('button', { name: 'Enlazar' }).click();
    await expect(area.getByRole('alert')).toContainText('no existe en el catálogo');

    // --- 5. Quitar el enlace; Costos también edita; el residente no ----------------------------------------------------
    await falta.getByRole('button', { name: /^Quitar el enlace/ }).click();
    await expect(falta).toHaveCount(0);
    expect((await enlaces()).enlaces).toHaveLength(1);

    const costos = await browser.newPage();
    await entrarComo(costos, 'costos');
    await costos.goto(url);
    await costos.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Paramétrico/ }).click();
    const areaCostos = costos.locator('#area-parametrico');
    await expect(areaCostos.locator('tr[data-driver="altura_estandar"]').getByLabel(/^Valor de la obra para/)).toBeEnabled();
    await expect(areaCostos.getByRole('group', { name: 'Enlazar una ranura' })).toBeVisible();
    await costos.close();

    const residente = await solicitarApi(request, 'residente', 'PUT', '/drivers/altura_estandar', { valor: '2' });
    expect(residente.status()).toBe(403);
    const residenteEnlace = await solicitarApi(request, 'residente', 'PUT', `/obras/${obra.id}/enlaces-de-ranura`, {
      ranura: 'mamposteria:tabique_rojo',
      concepto_clave: 'E2E-CIM',
    });
    expect(residenteEnlace.status()).toBe(403);
  });
});
