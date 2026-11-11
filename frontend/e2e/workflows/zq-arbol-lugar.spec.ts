import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * El lugar de las partidas en el árbol (D-634): «Bajar posición» y «Subir posición» cambian el orden de una partida dentro
 * de su etapa y el orden queda guardado, de modo que lo ve cualquiera que abra la obra.
 */

const ROLES_ZQ = ['control'] as const;

type Partida = { concepto_clave: string; etapa_clave: string | null; orden: number | null };

test.describe('Cuantificador · lugar de las partidas', () => {
  test.skip(!hayRoles(...ROLES_ZQ), motivoSinRoles(...ROLES_ZQ));
  test.setTimeout(120_000);

  test('una partida baja y sube de posición y el orden queda guardado', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const unidades = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/unidades');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave: `LUG-${sufijo}`,
    });
    for (const k of ['A', 'B']) {
      await llamarApi(request, 'control', 'POST', '/conceptos', {
        tipo: 'concepto',
        clave: `LU${k}-${sufijo}`,
        descripcion: `Partida ${k}`,
        unidad_id: unidades.find((u) => u.clave === 'm2')!.id,
      });
    }
    const partidas = async () => llamarApi<Partida[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const lugar = async (clave: string) =>
      (await partidas())
        .filter((p) => p.etapa_clave === `ET${sufijo}`)
        .sort((x, y) => (x.orden ?? 0) - (y.orden ?? 0))
        .findIndex((p) => p.concepto_clave === clave);

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}`);
    await page.getByRole('tab', { name: 'Árbol' }).click();
    const arbol = page.getByRole('region', { name: 'Armar el árbol' });
    await arbol.getByRole('button', { name: 'Nuevo nivel' }).click();
    await arbol.getByLabel('Nuevo nivel: Clave').fill(`NV${sufijo}`);
    await arbol.getByLabel('Nuevo nivel: Descripción').fill('Planta');
    await arbol.getByLabel('Nuevo nivel: Descripción').press('Enter');
    const nivel = arbol.locator(`[data-nivel="NV${sufijo}"]`);
    await nivel.getByRole('button', { name: `Nueva etapa en NV${sufijo}` }).click();
    await nivel.getByLabel(`Nueva etapa en NV${sufijo}: Clave`).fill(`ET${sufijo}`);
    await nivel.getByLabel(`Nueva etapa en NV${sufijo}: Descripción`).fill('Etapa');
    await nivel.getByLabel(`Nueva etapa en NV${sufijo}: Descripción`).press('Enter');
    const etapa = arbol.locator(`[data-etapa="ET${sufijo}"]`);
    await expect(etapa).toBeVisible();

    for (const k of ['A', 'B']) {
      await etapa.getByRole('button', { name: 'Agregar partida' }).click();
      await etapa.getByLabel('Concepto de la partida (clave)').fill(`LU${k}-${sufijo}`);
      await etapa.getByLabel('Concepto de la partida (clave)').press('Enter');
      await expect(arbol.locator(`[data-partida="LU${k}-${sufijo}"]`)).toBeVisible();
    }
    // Nacen en orden: A antes que B.
    await expect.poll(async () => (await lugar(`LUA-${sufijo}`)) < (await lugar(`LUB-${sufijo}`))).toBe(true);

    // Los controles están en la barra de arriba y actúan sobre la partida elegida con un clic.
    await arbol.locator(`[data-partida="LUA-${sufijo}"]`).click();
    await expect(arbol.getByRole('toolbar', { name: 'Controles del árbol' })).toContainText(`LUA-${sufijo}`);
    if (process.env.E2E_CAPTURAS) await arbol.screenshot({ path: `${process.env.E2E_CAPTURAS}/arbol-barra.png` });
    await arbol.getByRole('button', { name: `Bajar posición de LUA-${sufijo}` }).click();
    await expect.poll(async () => (await lugar(`LUA-${sufijo}`)) > (await lugar(`LUB-${sufijo}`))).toBe(true);
    await arbol.getByRole('button', { name: `Subir posición de LUA-${sufijo}` }).click();
    await expect.poll(async () => (await lugar(`LUA-${sufijo}`)) < (await lugar(`LUB-${sufijo}`))).toBe(true);

    // Bajo cada partida van sus trabajos, con «+ Trabajo» (como en el mockup del Árbol).
    const trabajos = arbol.getByRole('group', { name: `Trabajos de LUA-${sufijo}` });
    await expect(trabajos).toContainText('Sin trabajos en la receta');
    await trabajos.getByRole('button', { name: `Agregar trabajo a LUA-${sufijo}` }).click();
    await trabajos.getByLabel(`Nombre del trabajo de LUA-${sufijo}`).fill('Colado de prueba');
    await trabajos.getByLabel(`Nombre del trabajo de LUA-${sufijo}`).press('Enter');
    await expect(trabajos.locator('[data-trabajo]')).toHaveCount(1);
    await expect(trabajos).toContainText('Colado de prueba');
    if (process.env.E2E_CAPTURAS) await arbol.screenshot({ path: `${process.env.E2E_CAPTURAS}/arbol-mockup.png` });
  });
});
