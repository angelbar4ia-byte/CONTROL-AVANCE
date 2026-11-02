import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Escala automática (Fase 2): la hoja de un PDF dice «ESC. 1:50».
 *
 *  1. «Proponer la escala» lee el texto de la hoja y ofrece 1:50, con lo que cubriría la hoja.
 *  2. No se aplica sola: el plano sigue sin calibrar hasta confirmar.
 *  3. Al confirmar, el plano queda calibrado con la escala de un PDF a su tamaño de impresión.
 *  4. Un plano que no es PDF no ofrece la propuesta.
 */

const ROLES_ZB = ['control'] as const;

// Hoja de 300×200 puntos con el rótulo «ESC. 1:50» (Helvetica, sin fuente incrustada).
const PDF = [
  '%PDF-1.4',
  '1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj',
  '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj',
  '3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>endobj',
  '4 0 obj<</Length 44>>stream',
  'BT /F1 12 Tf 20 20 Td (ESC. 1:50) Tj ET',
  'endstream endobj',
  '5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj',
  'trailer<</Root 1 0 R/Size 6>>',
  '%%EOF',
].join('\n');

test.describe('Cuantificador · escala automática', () => {
  test.skip(!hayRoles(...ROLES_ZB), motivoSinRoles(...ROLES_ZB));
  test.setTimeout(120_000);

  test('la escala que dice la hoja se propone y solo se aplica al confirmar', async ({ page, request }) => {
    const clave = `ESA-${Date.now().toString(36).toUpperCase()}`;
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
    const pdf = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Con escala',
      archivo_url: 'e2e/escala.pdf',
    });
    const dwg = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Sin PDF',
      archivo_url: 'e2e/sin-pdf.dwg',
    });
    await page.route('**/api/v1/planos/*/archivo', (ruta) =>
      ruta.fulfill({
        json: {
          url: 'http://127.0.0.1:5173/__e2e/escala.pdf',
          expira_en_segundos: 900,
          expira_en: new Date(Date.now() + 900_000).toISOString(),
        },
      }),
    );
    await page.route('**/__e2e/escala.pdf', (ruta) => ruta.fulfill({ contentType: 'application/pdf', body: PDF }));
    const escala = async () =>
      (await llamarApi<{ id: string; escala_m_por_unidad: string | null }[]>(request, 'control', 'GET', `/obras/${obra.id}/planos`)).find(
        (p) => p.id === pdf.id,
      )?.escala_m_por_unidad ?? null;

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${pdf.id}`);
    const funciones = page.getByRole('toolbar', { name: 'Funciones' });

    // --- 1. Se propone lo que dice la hoja -----------------------------------------------------------------
    await funciones.getByRole('button', { name: 'Proponer la escala' }).click();
    const hoja = page.getByRole('dialog', { name: 'Proponer la escala' });
    await expect(hoja.getByRole('radio', { name: /1:50/ })).toBeChecked();
    // 300×200 pt a 1:50 cubren 5.29 × 3.53 m.
    await expect(hoja.getByTestId('cobertura-de-la-hoja')).toContainText('5.29');

    // --- 2. No se aplicó sola ------------------------------------------------------------------------------
    expect(await escala()).toBeNull();

    // --- 3. Al confirmar queda calibrado -------------------------------------------------------------------
    await hoja.getByRole('button', { name: 'Aplicar esta escala' }).click();
    await expect(page.getByRole('status')).toContainText('Escala aplicada');
    await expect.poll(async () => Number(await escala())).toBeCloseTo((0.0254 / 72) * 25, 5);

    // --- 4. Un plano que no es PDF no la ofrece --------------------------------------------------------------
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${dwg.id}`);
    await expect(funciones.getByRole('button', { name: 'Proponer la escala' })).toBeDisabled();
  });
});
