/**
 * Reflejo de UX de las reglas del §4 sobre usuarios — `src/equipo/reglas.ts` y
 * `src/equipo/formulario.ts`.
 *
 * Lo que se fija aquí es que la pantalla **no ofrezca** lo que el backend va a
 * rechazar: un Control de obra no debe ver la opción de crear un Super
 * intendente, ni el botón de asignar proyectos a otro Control. Es UX, no
 * seguridad —la frontera son el dominio, el trigger de la 0025 y RLS—, pero
 * una opción visible que siempre falla es peor que no ofrecerla.
 */

import { describe, expect, it } from 'vitest';

import {
  LARGO_MINIMO_CONTRASENA,
  administraEquipo,
  etiquetaRol,
  puedeAsignarAlcanceDe,
  puedeEditar,
  puenteDe,
  rolesQueCuelganDe,
  rolesQuePuedeOtorgar,
  sugerirContrasena,
  tonoRol,
} from '@/equipo/reglas';
import {
  altaCompleta,
  cambiosDeUsuario,
  formularioDesdeUsuario,
  formularioUsuarioVacio,
  hayCambios,
  peticionDeAlta,
} from '@/equipo/formulario';
import type { UsuarioRespuesta } from '@/api/generado/modelo';

const RESIDENTE: UsuarioRespuesta = {
  id: 'u-1',
  nombre: 'Ana Ruiz',
  email: 'ana@obra.mx',
  rol: 'residente',
  cedula: null,
  telefono: null,
  estatus: 'activo',
  puede_entrar: true,
  debe_cambiar_password: false,
};

describe('quién otorga qué rol', () => {
  it('control de obra arma su equipo pero no fabrica un super intendente', () => {
    const otorgables = rolesQuePuedeOtorgar('control_obra');
    expect(otorgables).toContain('residente');
    expect(otorgables).toContain('supervisor');
    expect(otorgables).toContain('control_obra');
    expect(otorgables).not.toContain('super_intendente');
  });

  it('el super intendente sí', () => {
    expect(rolesQuePuedeOtorgar('super_intendente')).toContain('super_intendente');
  });

  it('quien no administra no otorga nada', () => {
    expect(rolesQuePuedeOtorgar('residente')).toHaveLength(0);
    expect(rolesQuePuedeOtorgar('supervisor')).toHaveLength(0);
  });

  it('administrar el equipo es de C y SI (§5.1)', () => {
    expect(administraEquipo('control_obra')).toBe(true);
    expect(administraEquipo('super_intendente')).toBe(true);
    expect(administraEquipo('residente')).toBe(false);
    expect(administraEquipo('supervisor')).toBe(false);
  });
});

describe('a quién se puede editar', () => {
  it('nadie se edita a sí mismo desde Equipo', () => {
    expect(puedeEditar('control_obra', true, 'control_obra')).toBe(false);
  });

  it('solo un super intendente edita a otro super intendente', () => {
    expect(puedeEditar('control_obra', false, 'super_intendente')).toBe(false);
    expect(puedeEditar('super_intendente', false, 'super_intendente')).toBe(true);
  });

  it('control de obra edita a los demás', () => {
    expect(puedeEditar('control_obra', false, 'residente')).toBe(true);
  });
});

describe('puentes de alcance (§4, cadena de mando 0042)', () => {
  it('cada rol tiene el suyo, y Control de obra ninguno', () => {
    expect(puenteDe('super_intendente')).toBe('gente');
    expect(puenteDe('supervisor')).toBe('gente');
    // Sus obras deciden su alcance real, y hacia arriba el de su cadena.
    expect(puenteDe('residente')).toBe('obras');
    // Es la raíz: ve toda la organización, no cuelga de nadie.
    expect(puenteDe('control_obra')).toBeNull();
  });

  it('de un super intendente cuelgan supervisores y residentes; de un supervisor, solo residentes', () => {
    expect(rolesQueCuelganDe('super_intendente')).toEqual(
      expect.arrayContaining(['supervisor', 'residente']),
    );
    expect(rolesQueCuelganDe('supervisor')).toEqual(['residente']);
    expect(rolesQueCuelganDe('residente')).toHaveLength(0);
  });

  it('control arma la gente de un super intendente; control o el SI arman la de un supervisor', () => {
    expect(puedeAsignarAlcanceDe('control_obra', 'super_intendente')).toBe(true);
    expect(puedeAsignarAlcanceDe('super_intendente', 'super_intendente')).toBe(false);
    expect(puedeAsignarAlcanceDe('control_obra', 'supervisor')).toBe(true);
    expect(puedeAsignarAlcanceDe('super_intendente', 'supervisor')).toBe(true);
    expect(puedeAsignarAlcanceDe('supervisor', 'supervisor')).toBe(false);
  });

  it('control, el SI o el supervisor arman las obras de un residente', () => {
    expect(puedeAsignarAlcanceDe('control_obra', 'residente')).toBe(true);
    expect(puedeAsignarAlcanceDe('super_intendente', 'residente')).toBe(true);
    expect(puedeAsignarAlcanceDe('supervisor', 'residente')).toBe(true);
    expect(puedeAsignarAlcanceDe('residente', 'residente')).toBe(false);
  });
});

describe('etiquetas', () => {
  it('traduce los cuatro roles del §4', () => {
    expect(etiquetaRol('control_obra')).toBe('Control de obra');
    expect(etiquetaRol('super_intendente')).toBe('Super intendente');
  });

  it('un rol desconocido se muestra tal cual en vez de desaparecer', () => {
    expect(etiquetaRol('inventado')).toBe('inventado');
  });

  it('el rol de más privilegio se distingue', () => {
    expect(tonoRol('super_intendente')).not.toBe(tonoRol('residente'));
  });
});

describe('contraseña temporal', () => {
  it('la sugerida cumple el mínimo que exige el backend', () => {
    for (let i = 0; i < 20; i += 1) {
      expect(sugerirContrasena().length).toBeGreaterThanOrEqual(
        LARGO_MINIMO_CONTRASENA,
      );
    }
  });

  it('es legible: alguien la va a dictar por teléfono', () => {
    expect(sugerirContrasena()).toMatch(/^[a-z]+-\d{3}$/);
  });

  it('no se repite entre altas', () => {
    const muestras = new Set(Array.from({ length: 20 }, sugerirContrasena));
    expect(muestras.size).toBeGreaterThan(15);
  });
});

describe('formulario de alta', () => {
  it('exige nombre, correo y una contraseña de largo suficiente', () => {
    const vacio = formularioUsuarioVacio('residente', '');
    expect(altaCompleta(vacio, LARGO_MINIMO_CONTRASENA)).toBe(false);

    const corta = { ...vacio, nombre: 'Ana', email: 'a@b.mx', contrasenaTemporal: 'x' };
    expect(altaCompleta(corta, LARGO_MINIMO_CONTRASENA)).toBe(false);

    const completa = { ...corta, contrasenaTemporal: 'x'.repeat(LARGO_MINIMO_CONTRASENA) };
    expect(altaCompleta(completa, LARGO_MINIMO_CONTRASENA)).toBe(true);
  });

  it('normaliza el correo a minúsculas', () => {
    // `uq_usuario_email_org` distingue mayúsculas: sin esto "Ana@obra.mx" y
    // "ana@obra.mx" serían dos personas.
    const formulario = {
      ...formularioUsuarioVacio('residente', 'x'.repeat(12)),
      nombre: ' Ana  Ruiz ',
      email: '  ANA@Obra.MX  ',
    };
    const peticion = peticionDeAlta(formulario);
    expect(peticion.email).toBe('ana@obra.mx');
    expect(peticion.nombre).toBe('Ana  Ruiz');
  });

  it('los opcionales vacíos no viajan en el cuerpo', () => {
    const peticion = peticionDeAlta({
      ...formularioUsuarioVacio('residente', 'x'.repeat(12)),
      nombre: 'Ana',
      email: 'ana@obra.mx',
      cedula: '   ',
      telefono: '',
    });
    expect(peticion.cedula).toBeUndefined();
    expect(peticion.telefono).toBeUndefined();
  });
});

describe('edición: solo lo que cambió', () => {
  it('un formulario sin tocar no manda nada', () => {
    const cambios = cambiosDeUsuario(formularioDesdeUsuario(RESIDENTE), RESIDENTE);
    expect(hayCambios(cambios)).toBe(false);
  });

  it('editar el teléfono no arrastra el rol', () => {
    const formulario = {
      ...formularioDesdeUsuario(RESIDENTE),
      telefono: '5512345678',
    };
    const cambios = cambiosDeUsuario(formulario, RESIDENTE);
    expect(cambios).toEqual({ telefono: '5512345678' });
    // El trigger de la 0025 vigila los cambios de rol: no tiene por qué viajar
    // en una edición de teléfono.
    expect(cambios.rol).toBeUndefined();
  });

  it('un cambio de rol sí viaja', () => {
    const formulario = { ...formularioDesdeUsuario(RESIDENTE), rol: 'supervisor' as const };
    expect(cambiosDeUsuario(formulario, RESIDENTE).rol).toBe('supervisor');
  });
});
