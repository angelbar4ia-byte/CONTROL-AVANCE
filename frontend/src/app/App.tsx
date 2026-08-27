/**
 * Raíz de la aplicación: providers y rutas.
 *
 * Spec §5.1 (navegación por rol) · §5.3 (pantallas compartidas).
 *
 * Las pantallas compartidas se montan **una sola vez** y cambian
 * comportamiento por rol y alcance; no hay una copia por rol (§5.3).
 */

import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '@/shell/AppShell';
import { useAplicarDensidad } from '@/shell/SelectorDensidad';
import { useSesion } from '@/app/sesion';
import { Login } from '@/app/Login';
import { queryClient } from '@/app/queryClient';
import { supabase } from '@/lib/supabase';
import { useEnLinea } from '@/lib/useEnLinea';
import Avances from '@/avance/Avances';
import Cierres from '@/cierres/Cierres';
import Estimacion from '@/estimacion/Estimacion';
import Obras from '@/proyectos/Obras';
import Prototipos from '@/proyectos/Prototipos';
import Frentes from '@/proyectos/Frentes';
import Catalogos from '@/catalogos/Catalogos';
import Programacion from '@/programacion/Programacion';
import ProgramasBase from '@/programacion/ProgramasBase';
import Consumo from '@/materiales/Consumo';
import Salidas from '@/materiales/Salidas';
import Incidencias from '@/incidencias/Incidencias';
import Evaluaciones from '@/evaluaciones/Evaluaciones';
import Equipo from '@/equipo/Equipo';
import Asignaciones from '@/equipo/Asignaciones';
import Cargas from '@/cargas/Cargas';
import ReiniciarOrganizacion from '@/organizacion/ReiniciarOrganizacion';
import Expediente from '@/expediente/Expediente';
import Torre from '@/torre/Torre';
import ExtraCatalogo from '@/extras/ExtraCatalogo';
import Revisiones from '@/revisiones/Revisiones';
import CierresDeObra from '@/cierresObra/CierresDeObra';
import Presupuesto from '@/presupuesto/Presupuesto';
import Procesos from '@/procesos/Procesos';
import Bitacora from '@/bitacora/Bitacora';
import AvanceTotal from '@/reportes/AvanceTotal';

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Rutas />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

function Rutas() {
  useAplicarDensidad();

  const { sesion, cargando, error } = useSesion();
  const enLinea = useEnLinea();

  if (cargando) return <Cargando />;
  if (error) return <SesionSinVincular mensaje={error} />;
  if (!sesion) return <Login />;

  return (
    <Routes>
      <Route
        element={
          <AppShell
            rol={sesion.rol}
            usuario={sesion.nombre}
            semana={sesion.semanaActiva}
            enLinea={enLinea}
          />
        }
      >
        {/* La ruta inicial depende del rol (§5.1): el Residente entra a sus
            obras; los otros tres a la Torre de control, que es la primera
            entrada de su sidebar. */}
        <Route
          index
          element={
            <Navigate to={sesion.rol === 'residente' ? '/obras' : '/torre'} replace />
          }
        />
        {/* Torre de control: una sola implementación montada para los tres
            roles que la traen en su sidebar (§5.3). Lo que cambia es el
            alcance, que ya resolvió RLS. */}
        <Route path="/torre" element={<Torre />} />
        {/* Los huecos de una obra real (§11.2): el trabajo que no estaba en el
            prototipo y la evidencia de calidad. La revisión física es «móvil ·
            Control de obra» en el spec, pero el móvil es la Fase 15 y sin esta
            pantalla el expediente llega al cierre sin evidencia (§11.3 D). */}
        <Route path="/extra-catalogo" element={<ExtraCatalogo />} />
        <Route path="/revisiones" element={<Revisiones />} />
        {/* Cierre de obra final (§11.3 D): el SI abre el acta y los cuatro
            roles firman su parte, así que la bandeja es compartida aunque el
            sidebar solo la traiga en el suyo (§5.1). */}
        <Route path="/cierres-obra" element={<CierresDeObra />} />
        {/* Presupuesto y rendimientos (§5.1): una sola pantalla montada en las
            tres rutas que los sidebars de C y SI ya traían (§5.3). El detalle
            por concepto y por cuadrilla se abre desde su fila. */}
        <Route path="/presupuesto" element={<Presupuesto />} />
        <Route path="/config/presupuesto" element={<Presupuesto />} />
        <Route path="/rendimientos" element={<Presupuesto />} />
        {/* Las features se registran aquí conforme se implementan. */}
        {/* Proyecto → Cluster → Obra: una sola pantalla montada en la ruta
            que cada rol trae en su sidebar (§5.1, §5.3) — "Mis obras" y
            "Obras supervisadas" (R, S), "Creador de obra" (C) y "Avance de
            proyecto" (SI). */}
        <Route path="/obras" element={<Obras />} />
        <Route path="/config/creador-obra" element={<Obras />} />
        <Route path="/avance-proyecto" element={<Obras />} />
        <Route path="/frentes" element={<Frentes />} />
        {/* Catálogos · APU: el bloque es de Control de obra (§11.2) y su
            sidebar lo trae en Configuración → "Catálogos" (§5.1). El Super
            intendente puede leer el APU pero no tiene la entrada en su
            sidebar, así que no se monta una ruta que nada apunte. */}
        <Route path="/config/catalogos" element={<Catalogos />} />
        {/* Programación · CPM: el Gantt con la ruta crítica es pantalla
            compartida (§5.3) y los cuatro sidebars ya traen "Ruta crítica"
            (§5.1). El Super intendente además la alcanza desde Reportes →
            "Programas de obra". Los programas base son de Control de obra y
            su sidebar los trae en Configuración (§11.2, §5.1). */}
        <Route path="/ruta-critica" element={<Programacion />} />
        <Route path="/programas" element={<Programacion />} />
        <Route path="/config/programas-base" element={<ProgramasBase />} />
        <Route path="/avances" element={<Avances />} />
        <Route path="/cierres" element={<Cierres />} />
        {/* Control de materiales (§7.7, §11.2): Control de obra trae las dos
            entradas en su sidebar —"Salidas de almacén" y "Consumo vs
            presupuesto"—; el Residente trae una sola, "Control de materiales
            (lectura)" en /materiales, que apunta al consumo (§5.1). */}
        <Route path="/materiales" element={<Consumo />} />
        <Route path="/materiales/consumo" element={<Consumo />} />
        <Route path="/materiales/salidas" element={<Salidas />} />
        {/* Incidencias y Evaluación son pantallas compartidas (§5.3): una
            sola ruta que los cuatro sidebars ya traen con distinta etiqueta
            (§5.1). */}
        <Route path="/incidencias" element={<Incidencias />} />
        <Route path="/evaluaciones" element={<Evaluaciones />} />
        <Route path="/estimacion" element={<Estimacion />} />
        {/* Equipo (§5.1): «Usuarios» es de Control de obra y Super
            intendente; «Asignaciones» es compartida (§5.3) y el Supervisor la
            trae en su sidebar para ver los clusters que le tocaron. */}
        <Route path="/config/equipo" element={<Equipo />} />
        <Route path="/equipo" element={<Equipo />} />
        <Route path="/asignaciones" element={<Asignaciones />} />
        {/* Fase 5 cerrada en web: los endpoints de cargas y expediente
            existían desde entonces y ninguna pantalla los usaba. Cargas es de
            Control de obra (§5.1 Configuración); el expediente lo consultan C
            y SI desde Reportes (§5.3). */}
        <Route path="/config/cargas" element={<Cargas />} />
        <Route
          path="/config/reiniciar-organizacion"
          element={<ReiniciarOrganizacion />}
        />
        {/* Prototipos (§7.2): la carga masiva y el alta individual escriben
            la misma tabla; esta pantalla lista lo que cualquiera de las dos
            dejó, para Control de obra y Super intendente (§11.2). */}
        <Route path="/config/prototipos" element={<Prototipos />} />
        <Route path="/expediente" element={<Expediente />} />
        {/* Fase 16: las tres entradas del sidebar del Super intendente (§5.1)
            que caían en "en construcción" porque su endpoint no existía —
            procesos (§7.9), bitácora (§12.12) y el reporte por alcance
            (§11.2 `POST /reportes/{tipo}`). */}
        <Route path="/procesos" element={<Procesos />} />
        <Route path="/bitacora" element={<Bitacora />} />
        <Route path="/avance-total" element={<AvanceTotal />} />
        <Route path="*" element={<EnConstruccion />} />
      </Route>
    </Routes>
  );
}

function Cargando() {
  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
      <div className="text-mute text-sm">Cargando…</div>
    </div>
  );
}

/**
 * El usuario sí se autenticó en Supabase, pero su cuenta no tiene un
 * `usuario` de ObraCtrl vinculado (o está inactivo) — el Custom Access
 * Token Hook no encontró fila y el JWT salió sin `org_id`/`rol`
 * (`database/migrations/20260814000015_auth_hook.sql`). No es un error de
 * login: es una cuenta sin dar de alta en la organización.
 */
function SesionSinVincular({ mensaje }: { readonly mensaje: string }) {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div className="card" style={{ width: 360 }}>
        <div className="card__header" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
          <h1 className="card__title">Cuenta sin vincular</h1>
        </div>
        <div className="card__body col gap-12">
          <div className="badge badge--danger" role="alert">
            {mensaje}
          </div>
          <div className="field__hint">
            Pide a Control de obra que dé de alta tu usuario en la organización.
          </div>
          <button type="button" className="btn" onClick={() => void supabase.auth.signOut()}>
            Cerrar sesión
          </button>
        </div>
      </div>
    </div>
  );
}

function EnConstruccion() {
  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">ObraCtrl</div>
          <h1 className="page__title">Pantalla pendiente</h1>
        </div>
      </div>
      <div className="empty">
        <div className="empty-title">Aún no implementada</div>
        <div className="empty-sub">
          El shell, la navegación por rol y los tokens ya están listos.
          Las features se agregan una por una en <code>src/features/</code>.
        </div>
      </div>
    </div>
  );
}
