/**
 * Navegación por rol.
 *
 * Spec §5.1 (sidebar por rol) · §5.3 (pantallas compartidas) · §4 (alcance).
 *
 * Las pantallas compartidas —Torre, Incidencias, Ruta crítica, Cierres,
 * Estimación, Evaluación, Expediente, Presupuesto, Rendimientos, Avance— se
 * implementan **una sola vez** y cambian comportamiento por rol y alcance
 * (§5.3). Por eso este archivo mapea rol → qué se muestra, y no existe una
 * copia de cada pantalla por rol.
 */

import type { LucideIcon } from 'lucide-react';
import {
  Building2,
  ClipboardCheck,
  ClipboardList,
  FileSpreadsheet,
  FileText,
  FolderTree,
  GitBranch,
  Home,
  Layers,
  LineChart,
  Package,
  Settings,
  ShieldCheck,
  Star,
  Truck,
  Upload,
  Users,
} from 'lucide-react';

export type Rol = 'residente' | 'supervisor' | 'control_obra' | 'super_intendente';

export interface ItemNav {
  /** Ruta de React Router. */
  readonly a: string;
  readonly etiqueta: string;
  readonly icono: LucideIcon;
  /** Solo lectura para este rol (ej. Control de materiales para el Residente). */
  readonly soloLectura?: boolean;
}

export interface SeccionNav {
  readonly titulo: string;
  readonly items: readonly ItemNav[];
}

/** Etiqueta legible del rol, para la barra superior. */
export const NOMBRE_ROL: Record<Rol, string> = {
  residente: 'Residente de obra',
  supervisor: 'Supervisor de obra',
  control_obra: 'Control de obra',
  super_intendente: 'Super intendente de obra',
};

/** Alcance del rol, tal como lo impone RLS (§4). Se muestra como contexto. */
export const ALCANCE_ROL: Record<Rol, string> = {
  residente: 'Sus obras',
  supervisor: 'Sus clusters',
  control_obra: 'Proyectos asignados',
  super_intendente: 'Todos los proyectos',
};

const RESIDENTE: readonly SeccionNav[] = [
  {
    titulo: 'Mi trabajo',
    items: [
      { a: '/obras', etiqueta: 'Mis obras', icono: Home },
      { a: '/frentes', etiqueta: 'Frentes de obra', icono: Layers },
      { a: '/avances', etiqueta: 'Avances', icono: LineChart },
      { a: '/incidencias', etiqueta: 'Mis incidencias', icono: ClipboardList },
      { a: '/extra-catalogo', etiqueta: 'Extra-catálogo', icono: FolderTree },
      { a: '/ruta-critica', etiqueta: 'Mi ruta crítica', icono: GitBranch },
      {
        a: '/materiales',
        etiqueta: 'Control de materiales',
        icono: Package,
        soloLectura: true,
      },
    ],
  },
  {
    titulo: 'Reportes',
    items: [
      { a: '/evaluaciones', etiqueta: 'Autoevaluación', icono: Star },
      { a: '/estimacion', etiqueta: 'Guía de estimación', icono: FileSpreadsheet },
      { a: '/expediente', etiqueta: 'Expediente técnico', icono: FileText },
    ],
  },
];

const SUPERVISOR: readonly SeccionNav[] = [
  {
    titulo: 'Control supervisión',
    items: [
      { a: '/torre', etiqueta: 'Torre de control', icono: Building2 },
      { a: '/incidencias', etiqueta: 'Incidencias', icono: ClipboardList },
      { a: '/cierres', etiqueta: 'Solicitudes de cierre', icono: ClipboardCheck },
      { a: '/ruta-critica', etiqueta: 'Ruta crítica', icono: GitBranch },
    ],
  },
  {
    titulo: 'Equipo',
    // Asignaciones es solo web: no aparece en el móvil (§5.2)
    items: [{ a: '/asignaciones', etiqueta: 'Asignaciones', icono: Users }],
  },
  {
    titulo: 'Obras',
    items: [{ a: '/obras', etiqueta: 'Obras supervisadas', icono: Home }],
  },
];

const CONTROL_OBRA: readonly SeccionNav[] = [
  {
    titulo: 'Control de obra',
    items: [
      { a: '/torre', etiqueta: 'Torre de control', icono: Building2 },
      { a: '/incidencias', etiqueta: 'Incidencias', icono: ClipboardList },
      // Control valida y comenta; NO autoriza (§4)
      { a: '/cierres', etiqueta: 'Cierres', icono: ClipboardCheck },
      { a: '/ruta-critica', etiqueta: 'Ruta crítica', icono: GitBranch },
    ],
  },
  {
    titulo: 'Control de materiales',
    items: [
      { a: '/materiales/salidas', etiqueta: 'Salidas de almacén', icono: Truck },
      { a: '/materiales/consumo', etiqueta: 'Consumo vs presupuesto', icono: Package },
    ],
  },
  {
    // El §11.2 la marca «móvil · Control de obra», pero el móvil es la Fase 15
    // y sin esta entrada el expediente llega al cierre de obra sin evidencia de
    // calidad (§11.3 D).
    titulo: 'Calidad',
    items: [{ a: '/revisiones', etiqueta: 'Revisión física', icono: ClipboardCheck }],
  },
  {
    titulo: 'Reportes',
    items: [
      { a: '/evaluaciones', etiqueta: 'Evaluaciones', icono: Star },
      { a: '/estimacion', etiqueta: 'Guía estimado', icono: FileSpreadsheet },
      { a: '/expediente', etiqueta: 'Expediente técnico', icono: FileText },
      { a: '/rendimientos', etiqueta: 'Rendimientos', icono: LineChart },
    ],
  },
  {
    // El §5.1 dice que el alta de usuarios la hace Control de obra; hasta la
    // Fase 7 esa promesa no tenía pantalla y había que insertar filas en SQL.
    titulo: 'Equipo',
    items: [
      { a: '/config/equipo', etiqueta: 'Usuarios', icono: Users },
      { a: '/asignaciones', etiqueta: 'Asignaciones', icono: Users },
    ],
  },
  {
    titulo: 'Configuración',
    items: [
      { a: '/config/programas-base', etiqueta: 'Programas base', icono: GitBranch },
      { a: '/config/presupuesto', etiqueta: 'Presupuesto', icono: FileSpreadsheet },
      { a: '/config/creador-obra', etiqueta: 'Creador de obra', icono: Building2 },
      { a: '/config/catalogos', etiqueta: 'Catálogos', icono: FolderTree },
      { a: '/config/cargas', etiqueta: 'Cargas de datos', icono: Upload },
    ],
  },
];

const SUPER_INTENDENTE: readonly SeccionNav[] = [
  {
    titulo: 'Control general',
    items: [
      { a: '/torre', etiqueta: 'Torre de control', icono: Building2 },
      // Cierre de obra final: participan todos los roles (§6)
      { a: '/cierres-obra', etiqueta: 'Cierres de obra', icono: ShieldCheck },
      { a: '/incidencias', etiqueta: 'Incidencias', icono: ClipboardList },
      { a: '/ruta-critica', etiqueta: 'Ruta crítica', icono: GitBranch },
      { a: '/avance-proyecto', etiqueta: 'Avance de proyecto', icono: LineChart },
    ],
  },
  {
    titulo: 'Equipo',
    items: [
      { a: '/equipo', etiqueta: 'Usuarios', icono: Users },
      { a: '/asignaciones', etiqueta: 'Asignaciones', icono: Users },
    ],
  },
  {
    titulo: 'Presupuesto',
    items: [
      { a: '/presupuesto', etiqueta: 'Presupuesto de obras', icono: FileSpreadsheet },
      { a: '/rendimientos', etiqueta: 'Rendimientos de obra', icono: LineChart },
      { a: '/bitacora', etiqueta: 'Bitácora de eventos', icono: FileText },
      { a: '/procesos', etiqueta: 'Mejora de procesos', icono: Settings },
    ],
  },
  {
    titulo: 'Reportes',
    items: [
      { a: '/evaluaciones', etiqueta: 'Evaluaciones finales', icono: Star },
      { a: '/estimacion', etiqueta: 'Estimado total', icono: FileSpreadsheet },
      { a: '/avance-total', etiqueta: 'Avance total', icono: LineChart },
      { a: '/programas', etiqueta: 'Programas de obra', icono: GitBranch },
      { a: '/expediente', etiqueta: 'Expediente técnico', icono: FileText },
    ],
  },
];

const POR_ROL: Record<Rol, readonly SeccionNav[]> = {
  residente: RESIDENTE,
  supervisor: SUPERVISOR,
  control_obra: CONTROL_OBRA,
  super_intendente: SUPER_INTENDENTE,
};

/** Secciones del sidebar para un rol (§5.1). */
export function navegacionDe(rol: Rol): readonly SeccionNav[] {
  return POR_ROL[rol];
}

/**
 * ¿Este rol puede entrar a esta ruta?
 *
 * Es una guarda de **UX**, no de seguridad: la frontera real son RLS (§12.4)
 * y el RBAC del backend. Sirve para no mostrar un 403 evitable.
 */
export function rutaPermitida(rol: Rol, ruta: string): boolean {
  return POR_ROL[rol].some((seccion) =>
    seccion.items.some((item) => ruta === item.a || ruta.startsWith(`${item.a}/`)),
  );
}
