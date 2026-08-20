import { expect, test } from '../infraestructura';
import { entrar } from '../infraestructura';

/**
 * Alta de usuario de punta a punta — el criterio de cierre de la Fase 7.
 *
 * «Un Control de obra da de alta a un residente, le asigna sus obras, el
 * residente entra con su propia contraseña y captura avance — sin que nadie
 * toque SQL.»
 *
 * ## Por qué esta sí se escribe y los seis del §11.3 siguen en `fixme`
 *
 * La diferencia no es el esfuerzo: es que **esta UI ya se puede ejecutar**.
 * Los `fixme` de `seis-workflows.spec.ts` existen para no inventar selectores
 * contra pantallas que aún no corren; aquí las pantallas son de este mismo
 * commit y los selectores salen de su código, no de una suposición.
 *
 * ## Lo que esta prueba deja fuera, y por qué
 *
 * El último tramo del criterio —que el residente **entre** con la contraseña
 * recién fijada— exige un proveedor de auth real y crea una cuenta que después
 * hay que borrar. Contra un Supabase compartido eso deja basura, y contra uno
 * desechable no aporta nada que la prueba de integración del backend no cubra
 * ya. Lo que se verifica aquí es la mitad que solo existe en la UI: que Control
 * de obra pueda hacerlo sin abrir `psql`, que la lista lo refleje y que la
 * pantalla no ofrezca lo que el backend va a rechazar.
 *
 * Corre solo con `E2E_API_URL`, `E2E_USUARIO` y `E2E_PASSWORD` apuntando a una
 * API con Postgres migrado; si no, se salta con motivo (ver
 * `../infraestructura.ts`).
 */

/** Correo irrepetible: dos corridas seguidas chocarían con `uq_usuario_email_org`. */
function correoDePrueba(): string {
  return `e2e-${Date.now().toString(36)}@obra.mx`;
}

test.describe('Fase 7 · alta de usuario sin tocar SQL', () => {
  test('Control de obra da de alta a un residente y aparece en el equipo', async ({
    page,
  }) => {
    await entrar(page);
    await page.goto('/config/equipo');

    // Si quien entró no administra el equipo, la pantalla no ofrece el alta.
    // Se falla con un mensaje que lo dice en vez de con un timeout opaco.
    const botonAlta = page.getByRole('button', { name: 'Dar de alta' });
    await expect(
      botonAlta,
      'E2E_USUARIO debe ser control_obra o super_intendente (§5.1)',
    ).toBeVisible({ timeout: 15_000 });

    const correo = correoDePrueba();
    await botonAlta.click();

    await page.getByLabel('Nombre').fill('Residente E2E');
    await page.getByLabel('Correo').fill(correo);
    await page.getByLabel('Rol').selectOption('residente');

    // La contraseña viene sugerida al abrir el formulario: es parte del
    // diseño, porque quien da el alta la tiene que poder dictar.
    await expect(page.getByLabel('Contraseña temporal')).not.toBeEmpty();

    await page.getByRole('button', { name: 'Dar de alta' }).last().click();

    const fila = page.getByRole('row', { name: new RegExp(correo, 'i') });
    await expect(fila).toBeVisible({ timeout: 15_000 });
    // Nace obligado a cambiar la contraseña que le eligieron (§5.1).
    await expect(fila.getByText('Contraseña temporal')).toBeVisible();
  });

  test('el alta no ofrece un rol que el backend va a rechazar', async ({ page }) => {
    await entrar(page);
    await page.goto('/config/equipo');

    const botonAlta = page.getByRole('button', { name: 'Dar de alta' });
    await expect(botonAlta).toBeVisible({ timeout: 15_000 });
    await botonAlta.click();

    const opciones = await page.getByLabel('Rol').locator('option').allTextContents();

    // Control de obra no puede fabricar un Super intendente (§4). Si quien
    // corre la prueba **es** Super intendente, sí debe verlo: la aserción se
    // adapta a lo que la pantalla misma declara.
    const esSuperIntendente = await page
      .getByText('El rol de super intendente solo lo otorga otro super intendente')
      .isHidden();

    if (esSuperIntendente) {
      expect(opciones).toContain('Super intendente');
    } else {
      expect(opciones).not.toContain('Super intendente');
    }
  });

  test('Asignaciones solo lista a quien tiene puente de alcance', async ({ page }) => {
    await entrar(page);
    await page.goto('/asignaciones');

    await expect(page.getByRole('heading', { name: 'Asignaciones' })).toBeVisible({
      timeout: 15_000,
    });

    // El residente no lleva puente: llega a su obra por `obra.residente_id`
    // (§4). Si apareciera aquí, la pantalla estaría ofreciendo asignarle algo
    // que no le daría alcance.
    await expect(page.getByRole('button', { name: /Residente E2E/ })).toHaveCount(0);
  });
});
