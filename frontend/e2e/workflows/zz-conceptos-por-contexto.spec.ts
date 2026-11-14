import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, solicitarApi, test } from '../infraestructura';

/**
 * Los conceptos que paga un elemento por contexto (plan de elementos de muro, fase C):
 *  1. El mismo elemento paga EST-02010 (niveles 1 y 2) y EST-02011 (desde el nivel 3).
 *  2. El acero del castillo se paga por escalón de altura; un concepto nuevo queda «pendiente de autorizar».
 *  3. Una parte la toma un solo concepto por contexto (422 al repetirla).
 *  4. La tarjeta del elemento en la pestaña Trazos lo muestra, marca el concepto que paga en el nivel elegido y avisa del
 *     alto sin escalón.
 *
 * Es una obra nueva por corrida; el elemento lleva un alto único por corrida para no chocar con los de otros specs.
 */

const ROLES_ZC = ['control'] as const;

test.describe('Cuantificador · conceptos del elemento por contexto', () => {
  test.skip(!hayRoles(...ROLES_ZC), motivoSinRoles(...ROLES_ZC));
  test.setTimeout(120_000);

  test('la tarjeta del elemento muestra los conceptos por nivel, el escalón y el estado', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const unidades = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/unidades');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `CPC-${sufijo}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Conceptos por contexto',
      archivo_url: 'planos/conceptos-por-contexto.dwg',
    });
    const concepto = (clave: string) =>
      llamarApi<{ id: string }>(request, 'control', 'POST', '/conceptos', {
        tipo: 'concepto', clave: `${clave}-${sufijo}`, descripcion: `Concepto ${clave}`, unidad_id: unidades.find((u) => u.clave === 'pza')!.id,
      });
    const c10 = await concepto('C10');
    const c11 = await concepto('C11');
    const acero = await concepto('AC');

    const clave = `KC-${sufijo}`.slice(0, 20);
    const alto = 3.5 + (Date.now() % 1_000_000) / 1e7;
    const elemento = await llamarApi<{ id: string }>(request, 'control', 'POST', '/elementos-parametricos', {
      clave, nombre: 'Castillo por contexto', tipo: 'castillo', parametros: { alto },
    });
    const ruta = `/elementos-parametricos/${elemento.id}/conceptos-por-contexto`;
    const completo = { acero: true, concreto: true, cimbra: true };
    await llamarApi(request, 'control', 'POST', ruta, { concepto_id: c10.id, unidad: 'ml', toma: { concreto: true, cimbra: true }, nivel_min: 1, nivel_max: 2 });
    await llamarApi(request, 'control', 'POST', ruta, { concepto_id: c11.id, unidad: 'ml', toma: { concreto: true, cimbra: true }, nivel_min: 3 });
    // El acero, por escalón de altura: uno del catálogo (hasta 4.00 m) y uno nuevo propuesto (hasta 8.00 m).
    await llamarApi(request, 'control', 'POST', ruta, { concepto_id: acero.id, unidad: 'pza', toma: { acero: true, alambre: true }, alto_hasta_m: 4 });
    const propuesto = `EJ-${sufijo}`.slice(0, 20);
    await llamarApi(request, 'control', 'POST', ruta, {
      clave_propuesta: propuesto, descripcion: 'Acero del castillo hasta 8 m', unidad: 'pza', toma: { acero: true, alambre: true }, alto_hasta_m: 8,
    });
    // Una parte la toma un solo concepto por contexto.
    const doble = await solicitarApi(request, 'control', 'POST', ruta, { concepto_id: c11.id, unidad: 'ml', toma: completo, nivel_min: 2 });
    expect(doble.status()).toBe(422);

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /^Trazos/ }).click();
    await page.getByRole('button', { name: `Ver ${clave}` }).click();

    const tarjeta = page.locator(`[data-conceptos-por-contexto="${clave}"]`);
    await expect(tarjeta.locator('[data-concepto-por-contexto]')).toHaveCount(4);
    await expect(tarjeta.locator(`[data-concepto-por-contexto="C10-${sufijo}"]`)).toContainText('niveles 1 a 2');
    await expect(tarjeta.locator(`[data-concepto-por-contexto="C11-${sufijo}"]`)).toContainText('nivel 3 en adelante');
    await expect(tarjeta.locator(`[data-concepto-por-contexto="AC-${sufijo}"]`)).toContainText('hasta 4.00 m');
    await expect(tarjeta.locator(`[data-estado-del-concepto="AC-${sufijo}"]`)).toHaveText('Autorizado');
    await expect(tarjeta.locator(`[data-estado-del-concepto="${propuesto}"]`)).toHaveText('Nuevo, pendiente de autorizar');
    // El alto del castillo (> 3.5 m) llega a un escalón; sin avisos.
    await expect(tarjeta.locator('[data-aviso-de-concepto]')).toHaveCount(0);

    // Con el nivel 3 se marca el concepto que paga; el del nivel 1 y 2 queda atenuado.
    await page.getByLabel(`Nivel del muro para ${clave}`).selectOption('3');
    await expect(tarjeta.locator(`[data-concepto-por-contexto="C11-${sufijo}"]`)).toHaveAttribute('data-elegido', 'true');
    await expect(tarjeta.locator(`[data-concepto-por-contexto="C10-${sufijo}"]`)).toHaveAttribute('data-elegido', 'false');
    await expect(tarjeta.locator(`[data-concepto-por-contexto="AC-${sufijo}"]`)).toHaveAttribute('data-elegido', 'true');
    await page.getByLabel(`Nivel del muro para ${clave}`).selectOption('1');
    await expect(tarjeta.locator(`[data-concepto-por-contexto="C10-${sufijo}"]`)).toHaveAttribute('data-elegido', 'true');
    await expect(tarjeta.locator(`[data-concepto-por-contexto="C11-${sufijo}"]`)).toHaveAttribute('data-elegido', 'false');

    // Un castillo más alto que su último escalón avisa del alto sin escalón.
    const alto2 = 9 + (Date.now() % 1_000_000) / 1e7;
    const clave2 = `KD-${sufijo}`.slice(0, 20);
    const alto_elemento = await llamarApi<{ id: string }>(request, 'control', 'POST', '/elementos-parametricos', {
      clave: clave2, nombre: 'Castillo alto', tipo: 'castillo', parametros: { alto: alto2 },
    });
    await llamarApi(request, 'control', 'POST', `/elementos-parametricos/${alto_elemento.id}/conceptos-por-contexto`, {
      concepto_id: acero.id, unidad: 'pza', toma: { acero: true }, alto_hasta_m: 6,
    });
    await page.reload();
    await page.getByRole('tab', { name: /^Trazos/ }).click();
    await page.getByRole('button', { name: `Ver ${clave2}` }).click();
    await expect(page.locator(`[data-conceptos-por-contexto="${clave2}"] [data-aviso-de-concepto]`)).toContainText('no tiene escalón');
  });
});
