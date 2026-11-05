import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Un concepto nace desde el cuantificador (entrega 5).
 *
 *  1. Control abre «+ Concepto», escribe clave y descripción y, al elegir la unidad, el concepto se crea
 *     **sin botón**: entra al árbol sin cantidad y queda activo.
 *  2. Existe en el servidor como adicional y sin cantidad; con clave repetida avisa y no duplica.
 *  3. El residente no ve la opción de crear; Costos sí, y llega hasta la base (RLS de la migración 0090).
 *
 * Es una obra nueva por corrida.
 */

const ROLES_Z = ['control', 'residente', 'costos'] as const;

test.describe('Cuantificador · concepto nuevo', () => {
  test.skip(!hayRoles(...ROLES_Z), motivoSinRoles(...ROLES_Z));
  test.setTimeout(120_000);

  test('se crea al elegir la unidad y entra a la obra sin cantidad', async ({ page, request }) => {
    const clave = `NUE-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Nuevos',
      archivo_url: 'planos/nuevos.dwg',
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);

    // Los conceptos nacen en la pestaña «Árbol»; el Presupuesto solo elige y mide.
    await expect(page.getByRole('button', { name: 'Nuevo concepto' })).toHaveCount(0);
    await page.getByRole('tab', { name: /Árbol/ }).click();
    await page.getByRole('button', { name: 'Nuevo concepto' }).click();
    const forma = page.getByRole('form', { name: 'Nuevo concepto' });
    await forma.getByLabel('Clave').fill(`${clave}-FIR`);
    await forma.getByLabel('Descripción').fill('Firme especial de 8 cm');
    // No hay botón de guardar: elegir la unidad lo crea.
    await forma.getByLabel('Unidad').selectOption({ label: 'm2 · Metro cuadrado' });

    await expect(page.getByText(`Concepto ${clave}-FIR creado`)).toBeVisible();
    await expect(forma).toHaveCount(0);
    await expect(page.getByText('Firme especial de 8 cm').first()).toBeVisible();

    const actividades = await llamarApi<{ concepto_clave: string; cant_base: string }[]>(
      request,
      'control',
      'GET',
      `/obras/${obra.id}/actividades`,
    );
    const nueva = actividades.find((a) => a.concepto_clave === `${clave}-FIR`);
    expect(nueva, 'la actividad nueva existe').toBeDefined();
    expect(Number(nueva!.cant_base)).toBe(0);

    // Clave repetida: avisa y no duplica.
    await page.getByRole('button', { name: 'Nuevo concepto' }).click();
    const otra = page.getByRole('form', { name: 'Nuevo concepto' });
    await otra.getByLabel('Clave').fill(`${clave}-FIR`);
    await otra.getByLabel('Descripción').fill('Repetido');
    await otra.getByLabel('Unidad').selectOption({ label: 'm2 · Metro cuadrado' });
    await expect(page.getByText(/Ya existe un concepto/)).toBeVisible();
  });

  test('el residente no crea conceptos', async ({ page, request }) => {
    const obras = await llamarApi<{ id: string; clave: string }[]>(request, 'residente', 'GET', '/obras');
    const obra = obras[0];
    expect(obra, 'el residente tiene una obra').toBeDefined();
    await entrarComo(page, 'residente');
    await page.goto(`/cuantificador?obra=${obra!.id}`);
    await expect(page.getByRole('tab', { name: /Presupuesto/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /Árbol/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Nuevo concepto' })).toHaveCount(0);
  });

  test('Costos también da de alta un concepto, con su propio rol en la base', async ({ page, request }) => {
    const clave = `COS-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });

    await entrarComo(page, 'costos');
    await page.goto(`/cuantificador?obra=${obra.id}`);
    await page.getByRole('tab', { name: /Árbol/ }).click();
    await page.getByRole('button', { name: 'Nuevo concepto' }).click();
    const forma = page.getByRole('form', { name: 'Nuevo concepto' });
    await forma.getByLabel('Clave').fill(`${clave}-X`);
    await forma.getByLabel('Descripción').fill('Concepto de Costos');
    await forma.getByLabel('Unidad').selectOption({ label: 'm2 · Metro cuadrado' });
    // Sin planos no hay dónde mostrar el aviso; el concepto entra a la obra y queda en el árbol.
    await page.getByRole('tab', { name: /Presupuesto/ }).click();
    await expect(page.getByRole('treeitem', { name: new RegExp(`${clave}-X`) })).toBeVisible();
  });
});
