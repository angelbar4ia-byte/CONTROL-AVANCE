/**
 * Programación · CPM: escala del Gantt, armado de filas y diff del PATCH.
 *
 * Todo lo que se prueba aquí es **presentación**. El cálculo de la ruta
 * crítica, la holgura y el desfase vive en el motor del backend
 * (`domain/programacion/cpm.py`, §6) y llega resuelto por la API; estas
 * pruebas fijan que el front lo **refleja** sin recalcularlo: que una barra
 * cae donde dicen las fechas recibidas, que `es_critica` manda en el color y
 * que un PATCH solo lleva lo que el usuario cambió (§11.2).
 */

import { describe, expect, it } from 'vitest';

import type {
  ActividadEnRutaRespuesta,
  ActividadProgramadaRespuesta,
  FrenteRespuesta,
  ProgramaObraRespuesta,
  RutaCriticaRespuesta,
} from '@/api/generado/modelo';
import {
  aDia,
  aIso,
  construirEscala,
  posicionDeFecha,
  tramoDeBarra,
  tramoDeHolgura,
} from '@/programacion/escala';
import {
  agruparPorFrente,
  construirFilas,
  filtrarPorTexto,
  resumirPrograma,
  soloCriticas,
  type FilaGantt,
} from '@/programacion/filas';
import {
  cambiosDeProgramacion,
  dependeDeSiMisma,
  dependenciasDelFormulario,
  formularioDeFila,
  hayCambios,
  refsDesconocidas,
} from '@/programacion/formulario';
import {
  claseBarra,
  etiquetaTipoDependencia,
  puedeAdministrarProgramasBase,
  puedeEditarProgramacion,
  puedeVerCronograma,
  tonoBarra,
} from '@/programacion/reglas';
import { rutaPermitida, type Rol } from '@/shell/navegacion';

const ROLES: readonly Rol[] = ['residente', 'supervisor', 'control_obra', 'super_intendente'];

function enRuta(parcial: Partial<ActividadEnRutaRespuesta> = {}): ActividadEnRutaRespuesta {
  return {
    actividad_id: 'a1',
    descripcion: 'Cimentación',
    frente_id: 'f-cim',
    duracion_dias: '5',
    dependencias: [],
    // Actividad continua: la lista vacía es el caso normal (§7.6). El contrato
    // la trae desde que existen los tramos, y sin ella el tipo no cierra.
    tramos: [],
    inicio_temprano: '2026-04-06',
    fin_temprano: '2026-04-10',
    inicio_tardio: '2026-04-06',
    fin_tardio: '2026-04-10',
    holgura: 0,
    desfase: 0,
    es_critica: true,
    bloqueada: false,
    avance_pct: '30',
    ...parcial,
  };
}

function programada(
  parcial: Partial<ActividadProgramadaRespuesta> = {},
): ActividadProgramadaRespuesta {
  return {
    id: 'a1',
    descripcion: 'Cimentación',
    frente_id: 'f-cim',
    etapa_id: 'e1',
    nivel_id: null,
    duracion_dias: '5',
    inicio_dias: null,
    dependencias: [],
    tramos: [],
    fecha_inicio: '2026-04-06',
    fecha_termino: '2026-04-10',
    avance_pct: '30',
    estatus: 'en_proceso',
    bloqueada: false,
    es_critica: true,
    holgura: '0',
    desfase: '0',
    ...parcial,
  };
}

const FRENTES: readonly FrenteRespuesta[] = [
  { id: 'f-cim', clave: 'CIM', nombre: 'Cimentación', etapa: 'Obra negra', orden: 2 },
  { id: 'f-pre', clave: 'PRE', nombre: 'Preliminares', etapa: 'Obra negra', orden: 1 },
];

describe('escala del Gantt (§12.10)', () => {
  it('convierte fechas puras de Postgres sin correrlas de día', () => {
    const dia = aDia('2026-04-06');
    expect(dia).not.toBeNull();
    expect(aIso(dia as number)).toBe('2026-04-06');
    expect(aDia('06/04/2026')).toBeNull();
    expect(aDia(null)).toBeNull();
  });

  it('ancla el lienzo al lunes anterior y mide un múltiplo de 7 días', () => {
    const escala = construirEscala([{ inicio: '2026-04-08', fin: '2026-04-15' }]);
    expect(escala).not.toBeNull();
    expect(escala?.semanas[0]?.inicio).toBe('2026-04-06');
    expect((escala?.dias ?? 0) % 7).toBe(0);
    expect(escala?.semanas.length).toBe(4); // mínimo legible
  });

  it('crece hasta cubrir el cronograma completo', () => {
    const escala = construirEscala([{ inicio: '2026-04-06', fin: '2026-06-30' }]);
    expect(escala?.dias).toBeGreaterThanOrEqual(86);
    expect((escala?.dias ?? 0) % 7).toBe(0);
  });

  it('sin ninguna fecha no hay escala que pintar', () => {
    expect(construirEscala([{ inicio: null, fin: null }])).toBeNull();
    expect(construirEscala([])).toBeNull();
  });

  it('marca la semana de la fecha de corte', () => {
    const escala = construirEscala([{ inicio: '2026-04-06', fin: '2026-05-01' }], '2026-04-15');
    const marcadas = escala?.semanas.filter((semana) => semana.esCorte) ?? [];
    expect(marcadas.length).toBe(1);
    expect(marcadas[0]?.inicio).toBe('2026-04-13');
  });

  it('la barra cubre el día de término completo', () => {
    const escala = construirEscala([{ inicio: '2026-04-06', fin: '2026-05-03' }]);
    const tramo = tramoDeBarra(escala!, '2026-04-06', '2026-04-12');
    // 7 de los 28 días del lienzo = un cuarto exacto.
    expect(tramo?.izquierda).toBeCloseTo(0);
    expect(tramo?.ancho).toBeCloseTo(25);
  });

  it('una actividad de un solo día ocupa ese día, no cero', () => {
    const escala = construirEscala([{ inicio: '2026-04-06', fin: '2026-05-03' }]);
    const tramo = tramoDeBarra(escala!, '2026-04-07', '2026-04-07');
    expect(tramo?.ancho).toBeCloseTo(100 / 28);
  });

  it('sin fechas no hay barra', () => {
    const escala = construirEscala([{ inicio: '2026-04-06', fin: '2026-05-03' }]);
    expect(tramoDeBarra(escala!, null, '2026-04-10')).toBeNull();
    expect(tramoDeBarra(escala!, '2026-04-10', null)).toBeNull();
  });

  it('la holgura arranca al día siguiente del fin y solo existe si es positiva', () => {
    const escala = construirEscala([{ inicio: '2026-04-06', fin: '2026-05-03' }]);
    const tramo = tramoDeHolgura(escala!, '2026-04-12', 7);
    expect(tramo?.izquierda).toBeCloseTo(25);
    expect(tramo?.ancho).toBeCloseTo(25);
    expect(tramoDeHolgura(escala!, '2026-04-12', 0)).toBeNull();
    expect(tramoDeHolgura(escala!, '2026-04-12', null)).toBeNull();
  });

  it('una fecha fuera del lienzo no se posiciona', () => {
    const escala = construirEscala([{ inicio: '2026-04-06', fin: '2026-05-03' }]);
    expect(posicionDeFecha(escala!, '2026-04-06')).toBeCloseTo(0);
    expect(posicionDeFecha(escala!, '2026-01-01')).toBeNull();
    expect(posicionDeFecha(escala!, null)).toBeNull();
  });
});

describe('filas del Gantt (§7.5, §7.6)', () => {
  it('sin programa se dibuja con lo que devolvió la ruta crítica', () => {
    const ruta = { actividades: [enRuta()] } as RutaCriticaRespuesta;
    const filas = construirFilas(null, ruta);

    expect(filas.length).toBe(1);
    expect(filas[0]?.inicio).toBe('2026-04-06');
    expect(filas[0]?.origenFechas).toBe('cpm');
    expect(filas[0]?.esCritica).toBe(true);
    expect(filas[0]?.holguraDias).toBe(0);
    expect(filas[0]?.finTardio).toBe('2026-04-10');
  });

  it('con programa manda la programación capturada y la ruta aporta las fechas tardías', () => {
    const programa = {
      actividades: [programada({ fecha_inicio: '2026-04-08', fecha_termino: '2026-04-14' })],
    } as ProgramaObraRespuesta;
    const ruta = { actividades: [enRuta()] } as RutaCriticaRespuesta;

    const filas = construirFilas(programa, ruta);
    expect(filas.length).toBe(1);
    expect(filas[0]?.inicio).toBe('2026-04-08');
    expect(filas[0]?.origenFechas).toBe('programa');
    expect(filas[0]?.etapaId).toBe('e1');
    expect(filas[0]?.finTardio).toBe('2026-04-10');
  });

  it('una actividad sin programación toma las fechas que calculó el motor', () => {
    const programa = {
      actividades: [programada({ fecha_inicio: null, fecha_termino: null })],
    } as ProgramaObraRespuesta;
    const ruta = { actividades: [enRuta()] } as RutaCriticaRespuesta;

    const filas = construirFilas(programa, ruta);
    expect(filas[0]?.inicio).toBe('2026-04-06');
    expect(filas[0]?.origenFechas).toBe('cpm');
  });

  it('no pierde las actividades que solo conoce el motor', () => {
    const programa = { actividades: [programada()] } as ProgramaObraRespuesta;
    const ruta = {
      actividades: [enRuta(), enRuta({ actividad_id: 'a2', descripcion: 'Firmes' })],
    } as RutaCriticaRespuesta;

    const filas = construirFilas(programa, ruta);
    expect(filas.map((fila) => fila.actividadId)).toEqual(['a1', 'a2']);
  });

  it('agrupa por frente en el orden del catálogo y deja al final lo que no lo tiene', () => {
    const ruta = {
      actividades: [
        enRuta({ actividad_id: 'a1', frente_id: 'f-cim' }),
        enRuta({ actividad_id: 'a2', frente_id: 'f-pre', es_critica: false }),
        enRuta({ actividad_id: 'a3', frente_id: null, es_critica: false }),
      ],
    } as RutaCriticaRespuesta;

    const grupos = agruparPorFrente(construirFilas(null, ruta), FRENTES);
    expect(grupos.map((grupo) => grupo.titulo)).toEqual([
      'Obra negra · Preliminares',
      'Obra negra · Cimentación',
      'Sin frente asignado',
    ]);
    expect(grupos[1]?.nCriticas).toBe(1);
  });

  it('filtra por texto y por ruta crítica sobre lo que ya llegó', () => {
    const ruta = {
      actividades: [
        enRuta({ actividad_id: 'a1', descripcion: 'Cimentación' }),
        enRuta({ actividad_id: 'a2', descripcion: 'Firmes', es_critica: false }),
      ],
    } as RutaCriticaRespuesta;
    const filas = construirFilas(null, ruta);

    expect(filtrarPorTexto(filas, 'firm').map((fila) => fila.actividadId)).toEqual(['a2']);
    expect(filtrarPorTexto(filas, '  ').length).toBe(2);
    expect(soloCriticas(filas).map((fila) => fila.actividadId)).toEqual(['a1']);
  });

  it('el resumen solo cuenta lo recibido', () => {
    const ruta = {
      actividades: [
        enRuta({ actividad_id: 'a1' }),
        enRuta({ actividad_id: 'a2', es_critica: false, desfase: 3 }),
      ],
    } as RutaCriticaRespuesta;

    const resumen = resumirPrograma(construirFilas(null, ruta));
    expect(resumen).toEqual({
      nActividades: 2,
      nCriticas: 1,
      nConDesfase: 1,
      nSinFecha: 0,
    });
  });
});

describe('tono de la barra (§6, mapeo de presentación)', () => {
  const base = { esCritica: false, bloqueada: false, desfaseDias: 0, avancePct: 40 };

  it('la ruta crítica manda sobre cualquier otro estado', () => {
    expect(tonoBarra({ ...base, esCritica: true, desfaseDias: 9, avancePct: 100 })).toBe(
      'critica',
    );
    expect(claseBarra('critica')).toBe('gantt__bar--danger');
  });

  it('el desfase y el bloqueo pintan advertencia', () => {
    expect(tonoBarra({ ...base, desfaseDias: 2 })).toBe('retrasada');
    expect(tonoBarra({ ...base, bloqueada: true })).toBe('retrasada');
  });

  it('al 100% queda concluida y el resto neutro', () => {
    expect(tonoBarra({ ...base, avancePct: 100 })).toBe('concluida');
    expect(tonoBarra(base)).toBe('normal');
    expect(claseBarra('normal')).toBe('');
  });

  it('solo etiqueta los tipos de dependencia que el contrato documenta', () => {
    // El contrato documentaba dos; hoy documenta los cuatro de MS Project
    // (`DependenciaDTO.tipo`, §7.5) y `FF` dejó de ser un valor sin nombre.
    expect(etiquetaTipoDependencia('FS')).toBe('Fin → inicio');
    expect(etiquetaTipoDependencia(undefined)).toBe('Fin → inicio');
    expect(etiquetaTipoDependencia('SS')).toBe('Inicio → inicio');
    expect(etiquetaTipoDependencia('FF')).toBe('Fin → fin');
    expect(etiquetaTipoDependencia('SF')).toBe('Inicio → fin');
    // Uno que el contrato no documenta se sigue mostrando tal cual, sin
    // inventarle nombre.
    expect(etiquetaTipoDependencia('XX')).toBe('XX');
  });
});

describe('permisos reflejados del §11.2', () => {
  it('los programas base son de Control de obra', () => {
    expect(ROLES.filter(puedeAdministrarProgramasBase)).toEqual(['control_obra']);
  });

  it('el cronograma completo lo leen Supervisor y Control de obra', () => {
    expect(ROLES.filter(puedeVerCronograma)).toEqual(['supervisor', 'control_obra']);
  });

  it('ajustar la programación es de Supervisor y Control de obra', () => {
    expect(ROLES.filter(puedeEditarProgramacion)).toEqual(['supervisor', 'control_obra']);
  });
});

describe('rutas donde se monta la feature (§5.1)', () => {
  it('los cuatro roles llegan a la ruta crítica desde su sidebar', () => {
    for (const rol of ROLES) {
      expect(rutaPermitida(rol, '/ruta-critica')).toBe(true);
    }
  });

  it('"Programas de obra" es la entrada del Super intendente', () => {
    expect(ROLES.filter((rol) => rutaPermitida(rol, '/programas'))).toEqual([
      'super_intendente',
    ]);
  });

  it('los programas base solo cuelgan del sidebar de Control de obra', () => {
    expect(ROLES.filter((rol) => rutaPermitida(rol, '/config/programas-base'))).toEqual([
      'control_obra',
    ]);
  });
});

describe('diff del PATCH de programación (§11.2)', () => {
  const fila: FilaGantt = {
    actividadId: 'a1',
    descripcion: 'Cimentación',
    frenteId: 'f-cim',
    etapaId: null,
    nivelId: null,
    inicio: '2026-04-06',
    fin: '2026-04-10',
    origenFechas: 'programa',
    duracionDias: 5,
    holguraDias: 0,
    desfaseDias: 0,
    esCritica: true,
    bloqueada: false,
    avancePct: 30,
    estatus: 'en_proceso',
    dependencias: [{ ref: 'a0', tipo: 'FS', lag_dias: 0 }],
    inicioTardio: null,
    finTardio: null,
  };

  it('sin tocar nada no manda nada', () => {
    const cambios = cambiosDeProgramacion(fila, formularioDeFila(fila));
    expect(hayCambios(cambios)).toBe(false);
  });

  it('manda solo el campo que cambió', () => {
    const formulario = { ...formularioDeFila(fila), duracionDias: '8' };
    expect(cambiosDeProgramacion(fila, formulario)).toEqual({ duracion_dias: 8 });
  });

  it('vaciar una fecha la limpia con null, no la omite', () => {
    const formulario = { ...formularioDeFila(fila), fechaTermino: '' };
    expect(cambiosDeProgramacion(fila, formulario)).toEqual({ fecha_termino: null });
  });

  it('quitar todas las predecesoras es un cambio, no una omisión', () => {
    const formulario = { ...formularioDeFila(fila), dependencias: [] };
    expect(cambiosDeProgramacion(fila, formulario)).toEqual({ dependencias: [] });
  });

  it('cambiar el lag de una predecesora se detecta', () => {
    const formulario = {
      ...formularioDeFila(fila),
      dependencias: [{ ref: 'a0', tipo: 'FS', lagDias: '2' }],
    };
    expect(cambiosDeProgramacion(fila, formulario)).toEqual({
      dependencias: [{ ref: 'a0', tipo: 'FS', lag_dias: 2 }],
    });
  });

  it('los renglones de dependencia a medio llenar no se envían', () => {
    expect(
      dependenciasDelFormulario([
        { ref: '  ', tipo: 'FS', lagDias: '0' },
        { ref: 'a0', tipo: '', lagDias: '' },
      ]),
    ).toEqual([{ ref: 'a0', tipo: 'FS', lag_dias: 0 }]);
  });

  it('avisa de las refs que el motor va a ignorar y de la autorreferencia', () => {
    const dependencias = [
      { ref: 'a0', tipo: 'FS', lagDias: '0' },
      { ref: 'fantasma', tipo: 'FS', lagDias: '0' },
    ];
    expect(refsDesconocidas(dependencias, new Set(['a0']))).toEqual(['fantasma']);
    expect(dependeDeSiMisma('a1', dependencias)).toBe(false);
    expect(dependeDeSiMisma('a0', dependencias)).toBe(true);
  });
});
