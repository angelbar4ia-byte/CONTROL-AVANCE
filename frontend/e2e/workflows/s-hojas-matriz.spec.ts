import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Hojas «matriz» del cuantificador (cerebro WORKFLOWS.md §8.9; D-565, D-583).
 *
 * El concepto es la matriz madre y un insumo puede ser otra matriz (nervaduras, trabes, bastones):
 * esas son las que se cuantifican.
 *
 *  1. El árbol del cuantificador abre, bajo un concepto, sus **matrices internas** con lo que el
 *     catálogo implica para esa actividad.
 *  2. Medir una matriz interna **ajusta el importe** de la actividad sin tocar su cantidad base.
 *  3. Al trazar se elige **qué se mide**: la actividad entera o una de sus matrices.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_S = ['control', 'residente'] as const;

test.describe('Hojas matriz · medir la matriz dentro del concepto', () => {
  test.skip(!hayRoles(...ROLES_S), motivoSinRoles(...ROLES_S));
  test.setTimeout(120_000);

  test('las matrices internas se abren bajo el concepto y medirlas ajusta el importe', async ({
    browser,
    request,
  }) => {
    const clave = `MTZ-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });
    await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/generar`, { modo_pago: 'destajo' });

    // Una losa (matriz madre) de 10 m² a $1,000, dada de alta como trabajo extra.
    const conceptos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/conceptos');
    const losa = conceptos.find((c) => c.clave === 'MTZ-LOSA')!;
    const nerv = conceptos.find((c) => c.clave === 'MTZ-NERV')!;
    const extra = await llamarApi<{ id: string }>(request, 'residente', 'POST', '/actividades', {
      obra_id: obra.id,
      descripcion: 'Losa de cimentación',
      orden_cambio: 'OC-MTZ-1',
      cant_base: '10',
      precio_unitario: '1000',
      precio_destajo: '600',
      concepto_id: losa.id,
    });

    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');
    await control.goto(`/cuantificador?obra=${obra.id}`);

    // --- 1. Bajo el concepto se abren sus matrices internas -------------------------------------------
    await control.getByRole('button', { name: /Matrices de MTZ-LOSA/ }).click();
    const matrices = control.getByRole('region', { name: 'Matrices de MTZ-LOSA' });
    await expect(matrices).toContainText('MTZ-NERV');
    await expect(matrices).toContainText('MTZ-TRABE');
    await expect(matrices.getByText('Sin medir')).toHaveCount(2);
    const filaNerv = matrices.getByRole('row', { name: /MTZ-NERV/ });
    await expect(filaNerv).toContainText('5'); // 10 m² × 0.5 que implica el catálogo

    // --- 2. Se mide la nervadura: 8 contra 5, y el importe se ajusta ---------------------------------------
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Cimentación',
      archivo_url: 'planos/cim.dwg',
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'LINESTRING(0 0, 8 0)',
      enlaces: [{ actividad_id: extra.id, matriz_concepto_id: nerv.id, medida: 'longitud', factor: '1' }],
    });
    await control.reload();
    await control.getByRole('button', { name: /Matrices de MTZ-LOSA/ }).click();
    const despues = control.getByRole('region', { name: 'Matrices de MTZ-LOSA' });
    await expect(despues.getByRole('row', { name: /MTZ-NERV/ })).toContainText('8');
    await expect(despues.getByText('Sin medir')).toHaveCount(1); // solo quedan las trabes
    await expect(despues).toContainText('Lo medido ajusta el importe');
    await expect(despues).toContainText('La cantidad de la actividad no cambia');

    const actividades = await llamarApi<{ id: string; cant_base: string }[]>(
      request,
      'control',
      'GET',
      `/obras/${obra.id}/actividades`,
    );
    expect(Number(actividades.find((a) => a.id === extra.id)!.cant_base)).toBe(10);
  });
});
