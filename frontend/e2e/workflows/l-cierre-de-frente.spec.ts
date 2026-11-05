import {
  entrarComo,
  expect,
  hayRoles,
  llamarApi,
  motivoSinRoles,
  solicitarApi,
  test,
} from '../infraestructura';

/**
 * El cierre de un frente (migración 0071; cerebro D-515/D-522/D-261/D-516).
 *
 * Un frente es un nivel constructivo. El residente solicita su cierre al 90 % de
 * avance, el supervisor aprueba y control de obra valida; cerrado el frente, el
 * residente ya no registra avance ahí.
 *
 *  1. Mientras el frente no llega al 90 %, el residente no puede solicitar el cierre.
 *  2. Al llegar, **avisa** («listo para cierre») y el residente lo solicita.
 *  3. El supervisor lo aprueba y control de obra lo valida: queda «Cerrado».
 *  4. El residente ya no registra avance en ese frente: el servidor responde 409.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_L = ['residente', 'supervisor', 'control'] as const;

interface ActividadApi {
  id: string;
  cant_base: string;
}

test.describe('Cierre de frente · el segundo candado del cierre', () => {
  test.skip(!hayRoles(...ROLES_L), motivoSinRoles(...ROLES_L));
  test.setTimeout(120_000);

  test('se avisa al 90 %, se solicita, se aprueba, se valida y el residente ya no registra ahí', async ({
    browser,
    request,
  }) => {
    const clave = `FRE-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });
    const actividades = await llamarApi<ActividadApi[]>(request, 'residente', 'GET', `/obras/${obra.id}/actividades`);

    const avanzar = async (fraccion: number) => {
      for (const a of actividades) {
        await llamarApi(request, 'residente', 'PATCH', `/actividades/${a.id}/avance`, {
          cant_ejecutada: String(Number(a.cant_base) * fraccion),
        });
      }
    };

    // --- 1. Al 60 % el frente no está listo, y el servidor no deja solicitarlo -----
    await avanzar(0.6);
    const [frente] = await llamarApi<{ nivel_id: string; clave: string; listo_para_cierre: boolean }[]>(
      request,
      'residente',
      'GET',
      `/obras/${obra.id}/cierres-frente`,
    );
    expect(frente!.listo_para_cierre).toBe(false);
    const pronto = await solicitarApi(request, 'residente', 'POST', `/obras/${obra.id}/cierres-frente`, {
      nivel_id: frente!.nivel_id,
    });
    expect(pronto.status()).toBe(409);

    // --- 2. Al 95 % avisa; el residente lo solicita desde la pantalla --------------
    await avanzar(0.95);
    const residente = await (await browser.newContext()).newPage();
    await entrarComo(residente, 'residente');
    await residente.goto('/cierre-frentes');
    await residente.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const fila = residente.getByRole('row', { name: new RegExp(`^${frente!.clave} `) });
    await expect(fila).toContainText('listo para cierre');
    await fila.getByRole('button', { name: 'Solicitar cierre' }).click();
    await expect(fila).toContainText('Cierre solicitado');
    await expect(fila).not.toContainText('listo para cierre'); // ya se solicitó: deja de avisar
    await expect(fila.getByRole('button', { name: 'Solicitar cierre' })).toHaveCount(0);

    // --- 3. El supervisor aprueba y control valida ----------------------------------
    const supervisor = await (await browser.newContext()).newPage();
    await entrarComo(supervisor, 'supervisor');
    await supervisor.goto('/cierre-frentes');
    await supervisor.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const filaSup = supervisor.getByRole('row', { name: new RegExp(`^${frente!.clave} `) });
    await expect(filaSup.getByRole('button', { name: 'Validar' })).toHaveCount(0); // no es de su rol
    await filaSup.getByRole('button', { name: 'Aprobar' }).click();
    await expect(filaSup).toContainText('Aprobado por supervisión');

    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');
    await control.goto('/cierre-frentes');
    await control.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const filaCtrl = control.getByRole('row', { name: new RegExp(`^${frente!.clave} `) });
    await expect(filaCtrl.getByRole('button', { name: 'Aprobar' })).toHaveCount(0);
    await filaCtrl.getByRole('button', { name: 'Validar' }).click();
    await control.getByRole('dialog').getByLabel('Comentario (opcional)').fill('Recorrido hecho');
    await control.getByRole('dialog').getByRole('button', { name: 'Validar', exact: true }).click();
    await expect(filaCtrl).toContainText('Cerrado');

    // --- 4. Cerrado el frente, el residente ya no registra avance ahí --------------
    const bloqueada = await solicitarApi(
      request,
      'residente',
      'PATCH',
      `/actividades/${actividades[0]!.id}/avance`,
      { cant_ejecutada: String(Number(actividades[0]!.cant_base) * 0.97) },
    );
    expect(bloqueada.status()).toBe(409);
    expect(await bloqueada.text()).toContain('ya está cerrado');
  });
});
