/**
 * Navegación por rol (§5.1) y formato es-MX (§12.10).
 *
 * La navegación es una guarda de UX, pero un error aquí manda a un rol a una
 * pantalla que no le toca, así que conviene fijarla con pruebas.
 */

import { describe, expect, it } from 'vitest';

import { navegacionDe, rutaPermitida, type Rol } from '@/shell/navegacion';
import { colorAvance, fmtFecha, fmtMXN, fmtNum, fmtPct, fmtSemana } from '@/lib/formato';

const ROLES: readonly Rol[] = [
  'residente',
  'supervisor',
  'control_obra',
  'super_intendente',
];

describe('navegación por rol (§5.1)', () => {
  it('cada rol tiene al menos una sección con items', () => {
    for (const rol of ROLES) {
      const secciones = navegacionDe(rol);
      expect(secciones.length).toBeGreaterThan(0);
      expect(secciones.every((s) => s.items.length > 0)).toBe(true);
    }
  });

  it('no repite rutas dentro de un mismo rol', () => {
    for (const rol of ROLES) {
      const rutas = navegacionDe(rol).flatMap((s) => s.items.map((i) => i.a));
      expect(new Set(rutas).size).toBe(rutas.length);
    }
  });

  it('solo Control de obra y Super intendente tienen Configuración (§5.1)', () => {
    const conConfig = ROLES.filter((rol) =>
      navegacionDe(rol).some((s) => s.items.some((i) => i.a.startsWith('/config'))),
    );
    expect(conConfig).toEqual(['control_obra']);
  });

  it('el Residente ve Control de materiales solo en lectura (§6)', () => {
    const item = navegacionDe('residente')
      .flatMap((s) => s.items)
      .find((i) => i.a === '/materiales');

    expect(item?.soloLectura).toBe(true);
  });

  it('Asignaciones la ven los tres roles que tienen algo que hacer ahí', () => {
    // Hasta la Fase 7 solo la traía el Supervisor, que la usa para **ver** qué
    // clusters le tocaron. Al abrirse la pantalla, Control de obra y Super
    // intendente la necesitan para lo contrario: repartir (§4). El Residente
    // sigue fuera — llega a su obra por `obra.residente_id`, no por un puente.
    const conAsignaciones = ROLES.filter((rol) =>
      navegacionDe(rol).some((s) => s.items.some((i) => i.a === '/asignaciones')),
    );
    expect(conAsignaciones).toEqual(['supervisor', 'control_obra', 'super_intendente']);
  });

  it('la Torre es la primera entrada de los tres roles que la tienen (§5.1)', () => {
    // Y es primera de verdad, no una más: es a donde caen al entrar. Si dejara
    // de estarlo, `App.tsx` los mandaría a una ruta que su sidebar no marca
    // como activa.
    const conTorre = ROLES.filter((rol) =>
      navegacionDe(rol).some((s) => s.items.some((i) => i.a === '/torre')),
    );
    expect(conTorre).toEqual(['supervisor', 'control_obra', 'super_intendente']);

    for (const rol of conTorre) {
      const primera = navegacionDe(rol)[0]?.items[0];
      expect(primera?.a, `la Torre no abre el sidebar de ${rol}`).toBe('/torre');
    }
  });

  it('el Residente no tiene Torre: entra a sus obras (§5.1)', () => {
    const items = navegacionDe('residente').flatMap((s) => s.items);
    expect(items.some((i) => i.a === '/torre')).toBe(false);
    expect(items.some((i) => i.a === '/obras')).toBe(true);
  });

  it('el alta de usuarios es de Control de obra y Super intendente (§5.1)', () => {
    // Es lo que la pantalla de Login promete: «el alta de usuarios la realiza
    // Control de obra». Un residente o un supervisor que viera la entrada
    // acabaría en un 403.
    const conUsuarios = ROLES.filter((rol) =>
      navegacionDe(rol).some((s) =>
        s.items.some((i) => i.a === '/equipo' || i.a === '/config/equipo'),
      ),
    );
    expect(conUsuarios).toEqual(['control_obra', 'super_intendente']);
  });

  it('el cierre de obra final es solo del Super intendente (§6)', () => {
    const conCierreObra = ROLES.filter((rol) =>
      navegacionDe(rol).some((s) => s.items.some((i) => i.a === '/cierres-obra')),
    );
    expect(conCierreObra).toEqual(['super_intendente']);
  });

  it('rutaPermitida acepta subrutas del módulo', () => {
    expect(rutaPermitida('control_obra', '/config/catalogos')).toBe(true);
    expect(rutaPermitida('control_obra', '/materiales/salidas')).toBe(true);
    expect(rutaPermitida('residente', '/config/catalogos')).toBe(false);
  });
});

describe('formato es-MX (§12.10)', () => {
  it('moneda MXN', () => {
    expect(fmtMXN(1234.5)).toBe('$1,234.50');
    expect(fmtMXN(null)).toBe('—');
    expect(fmtMXN('no-es-numero')).toBe('—');
  });

  it('cantidades con 2 decimales', () => {
    expect(fmtNum('1234.567')).toBe('1,234.57');
  });

  it('porcentaje recibe 0–100 como lo guarda la BD (§7.6)', () => {
    expect(fmtPct(95)).toBe('95.0%');
    expect(fmtPct(0)).toBe('0.0%');
  });

  it('fecha dd mmm aa', () => {
    expect(fmtFecha('2026-03-09')).toBe('09 mar 26');
    expect(fmtFecha(null)).toBe('—');
    expect(fmtFecha('fecha-inválida')).toBe('—');
  });

  it('semana de obra', () => {
    expect(fmtSemana(5, 2026)).toBe('S05 · 2026');
  });

  it('color de la barra de avance', () => {
    expect(colorAvance(95)).toBe('ok');
    expect(colorAvance(50)).toBe('accent');
    expect(colorAvance(10)).toBe('danger');
  });
});
