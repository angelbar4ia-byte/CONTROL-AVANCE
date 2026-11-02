import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Conteo automático por plantilla (Fase 2): se marca un símbolo y se buscan los iguales.
 *
 *  1. Un plano en imagen con cuatro símbolos «T» y un círculo de distracción.
 *  2. Con «Conteo automático» se marca la primera «T»: la búsqueda encuentra las cuatro (y no el círculo).
 *  3. «Proponer 4» las deja como **propuestas por revisar**: la cantidad medida sigue en cero.
 *  4. Se descarta una con un clic y se aceptan tres: la cantidad medida es 3.
 */

const ROLES_ZE = ['control', 'residente'] as const;
const ANCHO = 600;
const ALTO = 400;
const T = [
  [100, 100],
  [300, 120],
  [180, 260],
  [440, 300],
] as const;

test.describe('Cuantificador · conteo automático', () => {
  test.skip(!hayRoles(...ROLES_ZE), motivoSinRoles(...ROLES_ZE));
  test.setTimeout(150_000);

  test('encuentra los símbolos iguales y los propone sin sumarlos', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const unidades = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/unidades');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave: `CAU-${sufijo}`,
    });
    await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/generar`, { modo_pago: 'destajo' });
    const concepto = await llamarApi<{ id: string }>(request, 'control', 'POST', '/conceptos', {
      tipo: 'concepto',
      clave: `SAL-${sufijo}`,
      descripcion: 'Salida eléctrica',
      unidad_id: unidades.find((u) => u.clave === 'pza')!.id,
    });
    const actividad = await llamarApi<{ id: string }>(request, 'residente', 'POST', '/actividades', {
      obra_id: obra.id,
      descripcion: 'Salidas eléctricas',
      orden_cambio: 'OC-CAU-1',
      cant_base: '10',
      precio_unitario: '50',
      precio_destajo: '30',
      concepto_id: concepto.id,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Salidas',
      archivo_url: 'e2e/simbolos.png',
    });
    const cantidad = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request,
        'control',
        'GET',
        `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === actividad.id)?.cantidad_medida ?? 0);
    };

    await entrarComo(page, 'control');

    // El plano: una hoja blanca con cuatro «T» y un círculo, dibujada en el navegador.
    const base64 = await page.evaluate(
      ([ancho, alto, ts]) => {
        const lienzo = document.createElement('canvas');
        lienzo.width = ancho as number;
        lienzo.height = alto as number;
        const c = lienzo.getContext('2d')!;
        c.fillStyle = '#fff';
        c.fillRect(0, 0, ancho as number, alto as number);
        c.fillStyle = '#000';
        for (const [x, y] of ts as number[][]) {
          c.fillRect(x!, y!, 20, 6); // la barra
          c.fillRect(x! + 7, y!, 6, 20); // el tronco
        }
        c.beginPath();
        c.arc(520, 80, 11, 0, Math.PI * 2);
        c.fill(); // el distractor
        return lienzo.toDataURL('image/png').split(',')[1]!;
      },
      [ANCHO, ALTO, T as unknown as number[][]] as const,
    );
    await page.route('**/api/v1/planos/*/archivo', (ruta) =>
      ruta.fulfill({
        json: {
          url: 'http://localhost:5173/__e2e/simbolos.png',
          expira_en_segundos: 900,
          expira_en: new Date(Date.now() + 900_000).toISOString(),
        },
      }),
    );
    await page.route('**/__e2e/simbolos.png', (ruta) =>
      ruta.fulfill({ contentType: 'image/png', body: Buffer.from(base64, 'base64') }),
    );

    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const imagen = page.getByRole('img', { name: 'Plano con sus trazos' }).locator('image');
    await expect(imagen).toHaveCount(1);
    const caja = (await imagen.boundingBox())!;
    const aPantalla = (ix: number, iy: number) => [caja.x + (ix * caja.width) / ANCHO, caja.y + (iy * caja.height) / ALTO] as const;

    // --- 2. Marcar el símbolo y buscar -------------------------------------------------------------------------
    await page.getByRole('toolbar', { name: 'Herramientas de trazo' }).getByRole('button', { name: 'Conteo automático', exact: true }).click();
    const [x1, y1] = aPantalla(T[0][0] - 8, T[0][1] - 8);
    const [x2, y2] = aPantalla(T[0][0] + 28, T[0][1] + 28);
    await page.mouse.click(x1, y1);
    await page.mouse.click(x2, y2);
    const hoja = page.getByRole('dialog', { name: 'Conteo automático' });
    await expect(hoja.getByTestId('coincidencias')).toContainText('4 coincidencias', { timeout: 30_000 });
    // El único concepto de conteo de la obra ya viene elegido.
    await expect(hoja.getByLabel('Concepto que se cuenta')).toHaveValue(actividad.id);

    // --- 3. Se proponen, no suman ------------------------------------------------------------------------------
    await hoja.getByRole('button', { name: 'Proponer 4' }).click();
    const panel = page.getByRole('region', { name: 'Propuestas por revisar' });
    await expect(panel).toContainText('No suman nada');
    const marcas = page.locator('[data-propuesta-id]');
    await expect(marcas).toHaveCount(4);
    expect(await cantidad()).toBe(0);

    // --- 4. Descartar una y aceptar tres ---------------------------------------------------------------------------
    await marcas.first().locator('circle').first().click();
    await panel.getByRole('button', { name: 'Aceptar 3' }).click();
    await expect.poll(cantidad).toBe(3);
  });
});
