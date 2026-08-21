/**
 * Captura de avance — Residente (§5.2, §6, §12.5).
 *
 * Offline-first: lee y escribe directo contra la réplica SQLite local de
 * PowerSync (`usePowerSync`/`useQuery`), nunca contra la API HTTP. El sync
 * hacia Postgres lo hace PowerSync solo, en background, cuando hay
 * conexión (`src/sync/conector.ts`).
 *
 * Las fotos no se escriben aquí: se encolan aparte y sus claves de R2 se
 * cosen sobre `registro_avance.evidencias` cuando suben (§12.5,
 * `src/evidencias/cola.ts`). El avance queda guardado al instante aunque la
 * evidencia tarde: el número es el dato, la foto es su respaldo.
 *
 * Los topes de §6 se validan aquí mismo, antes de escribir a SQLite, con
 * las mismas fórmulas que el backend
 * (`backend/src/obractrl/domain/avance/reglas.py`), portadas en
 * `src/lib/reglasAvance.ts`. Es un **reflejo para UX**: la autoridad sigue
 * siendo el servidor cuando el registro sincroniza (§11.1). Un rechazo de
 * regla se muestra en la UI, nunca falla en silencio.
 */

import { useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  Text,
  TextInput,
  View,
} from 'react-native';
import { usePowerSync, useQuery } from '@powersync/react-native';

import type { FotoTomada } from '@/evidencias/captura';
import { encolar as encolarFoto } from '@/evidencias/cola';
import { obtenerDeviceId } from '@/lib/dispositivo';
import { generarId } from '@/lib/id';
import {
  aplicarCaptura,
  ErrorDeCaptura,
  type EstatusActividad,
} from '@/lib/reglasAvance';
import { useSesion } from '@/lib/sesion';
import { TOKENS } from '@/lib/tabs';
import { useEmpujarSalida } from '@/salida/ProveedorSalida';
import { Barra } from '@/ui/Barra';
import { Encabezado } from '@/ui/Encabezado';
import { Estatus } from '@/ui/Estatus';
import { Fotos } from '@/ui/Fotos';

interface FilaActividad {
  id: string;
  obra_id: string;
  descripcion: string;
  cant_base: number;
  cant_programada: number;
  cant_ejecutada: number;
  avance_pct: number;
  estatus: string;
  bloqueada: number | null;
  org_id: string;
  obra_clave: string | null;
  sin_subir: number;
}

/**
 * `(? IS NULL OR ...)` con el mismo valor dos veces: SQLite posicional no
 * reusa parámetros, y así la pantalla sirve igual filtrada por obra que
 * completa, sin dos consultas distintas.
 */
const CONSULTA = `
  SELECT a.id, a.obra_id, a.descripcion, a.cant_base, a.cant_programada, a.cant_ejecutada,
         a.avance_pct, a.estatus, a.bloqueada, a.org_id, o.clave AS obra_clave,
         (SELECT COUNT(*) FROM registro_avance r
           WHERE r.actividad_id = a.id AND r.sync_status = 'pendiente') AS sin_subir
    FROM actividad a
    LEFT JOIN obra o ON o.id = a.obra_id
   WHERE a.estatus != 'concluida'
     AND (? IS NULL OR a.obra_id = ?)
   ORDER BY (a.estatus = 'retrasada') DESC, a.fecha_inicio ASC
`;

export default function Pantalla() {
  const { sesion } = useSesion();
  const db = usePowerSync();
  const empujar = useEmpujarSalida();

  const { obraId, obraClave } = useLocalSearchParams<{
    obraId?: string;
    obraClave?: string;
  }>();
  const filtroObra = obraId ?? null;

  const { data: actividades, isLoading } = useQuery<FilaActividad>(CONSULTA, [
    filtroObra,
    filtroObra,
  ]);

  const [seleccionada, setSeleccionada] = useState<FilaActividad | null>(null);
  const [delta, setDelta] = useState('');
  const [comentario, setComentario] = useState('');
  const [fotos, setFotos] = useState<FotoTomada[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  function abrirCaptura(actividad: FilaActividad) {
    setSeleccionada(actividad);
    setDelta('');
    setComentario('');
    setFotos([]);
    setError(null);
  }

  function cerrarCaptura() {
    if (guardando) return;
    setSeleccionada(null);
    setError(null);
  }

  async function guardarCaptura() {
    if (!seleccionada || !sesion) return;

    const deltaNum = Number(delta.replace(',', '.'));
    if (!Number.isFinite(deltaNum) || deltaNum <= 0) {
      setError('Ingresa una cantidad ejecutada mayor a 0.');
      return;
    }

    const nuevaCantEjecutada = seleccionada.cant_ejecutada + deltaNum;

    let resultado;
    try {
      resultado = aplicarCaptura({
        cantBase: seleccionada.cant_base,
        cantProgramada: seleccionada.cant_programada,
        cantEjecutada: nuevaCantEjecutada,
        estatusActual: seleccionada.estatus as EstatusActividad,
      });
    } catch (e) {
      setError(e instanceof ErrorDeCaptura ? e.message : 'No se pudo validar la captura.');
      return;
    }

    setGuardando(true);
    setError(null);

    try {
      const deviceId = await obtenerDeviceId();
      const ahora = new Date().toISOString();
      const idRegistro = generarId();

      await db.writeTransaction(async (tx) => {
        // Bitácora: guarda el delta, no el total (§12.5) — así dos capturas
        // del mismo día desde dispositivos distintos se suman en vez de
        // pisarse (estrategia "acumular-deltas" de sync/powersync.ts).
        await tx.execute(
          `INSERT INTO registro_avance
             (id, org_id, actividad_id, fecha, delta_ejecutado, usuario_id,
              evidencias, comentario, sync_status, device_id, capturado_en)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          [
            idRegistro,
            seleccionada.org_id,
            seleccionada.id,
            ahora.slice(0, 10),
            deltaNum,
            sesion.usuarioId,
            '[]',
            comentario.trim(),
            'pendiente',
            deviceId,
            ahora,
          ],
        );

        // Reflejo local optimista: el total canónico lo recalcula el
        // servidor (estatus "servidor-manda" en sync/powersync.ts, y por eso
        // `actividad` no se sube en sync/conector.ts); esto solo evita que
        // la pantalla se vea desactualizada mientras no ha sincronizado.
        await tx.execute(
          `UPDATE actividad
              SET cant_ejecutada = ?, avance_pct = ?, estatus = ?
            WHERE id = ?`,
          [resultado.cantEjecutada, resultado.avancePct, resultado.estatus, seleccionada.id],
        );
      });

      // Fuera de la transacción a propósito: la cola de fotos es local-only y
      // no participa de la escritura que va a subir por PowerSync. Si el
      // encolado fallara, el avance ya está guardado — que es lo que no se
      // puede perder.
      for (const foto of fotos) {
        await encolarFoto(db, {
          entidad: 'registro_avance',
          entidadId: idRegistro,
          obraId: seleccionada.obra_id,
          uri: foto.uri,
          nombre: foto.nombre,
          contentType: foto.contentType,
        });
      }

      setSeleccionada(null);
      empujar();
    } catch {
      setError('No se pudo guardar la captura en el dispositivo. Intenta de nuevo.');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow={obraClave ? `Obra ${obraClave}` : 'Todas mis obras'}
        titulo="Avances"
        descripcion="Captura sin señal; se sincroniza al reconectar (§12.5)."
      />

      {filtroObra ? (
        <Pressable
          onPress={() => router.replace('/(residente)/avances')}
          className="mb-3 self-start rounded-full border border-line bg-surface px-3 py-1 active:opacity-70"
        >
          <Text className="text-xs text-text-soft">Quitar filtro de obra</Text>
        </Pressable>
      ) : null}

      {isLoading ? (
        <View className="mt-10 items-center">
          <ActivityIndicator color={TOKENS.accent} />
        </View>
      ) : (
        <FlatList
          data={actividades}
          keyExtractor={(item) => item.id}
          ListEmptyComponent={
            <Text className="mt-8 text-md text-text-mute">No hay actividades pendientes de captura.</Text>
          }
          renderItem={({ item }) => (
            <Pressable
              testID="actividad"
              onPress={() => abrirCaptura(item)}
              disabled={item.bloqueada === 1}
              className="mb-3 rounded-lg border border-line bg-surface p-4 active:opacity-70 disabled:opacity-50"
            >
              <View className="flex-row items-start justify-between">
                <View className="flex-1 pr-3">
                  {item.obra_clave ? (
                    <Text className="font-mono text-xs text-text-faint">{item.obra_clave}</Text>
                  ) : null}
                  <Text className="text-base text-text">{item.descripcion}</Text>
                </View>
                <Estatus valor={item.estatus} />
              </View>

              <View className="mt-3">
                <Barra pct={item.avance_pct} />
              </View>

              <View className="mt-2 flex-row items-center justify-between">
                <Text className="font-mono text-sm text-text-mute">
                  {item.cant_ejecutada} / {item.cant_programada} (base {item.cant_base})
                </Text>
                <Text className="font-mono text-sm text-text">{item.avance_pct}%</Text>
              </View>

              {item.bloqueada === 1 ? (
                <Text className="mt-2 text-xs text-danger">
                  Bloqueada por una incidencia que detiene la obra (§6).
                </Text>
              ) : null}

              {item.sin_subir > 0 ? (
                <Text className="mt-2 text-xs text-warn">
                  {item.sin_subir} captura{item.sin_subir === 1 ? '' : 's'} sin subir
                </Text>
              ) : null}
            </Pressable>
          )}
        />
      )}

      <Modal visible={seleccionada !== null} transparent animationType="fade" onRequestClose={cerrarCaptura}>
        <View className="flex-1 items-center justify-center bg-scrim px-6">
          <View className="w-full rounded-lg bg-surface p-5">
            {seleccionada ? (
              <>
                <Text className="text-lg text-text">{seleccionada.descripcion}</Text>
                <Text className="mt-1 font-mono text-sm text-text-mute">
                  Ejecutado: {seleccionada.cant_ejecutada} · Programado: {seleccionada.cant_programada} · Base:{' '}
                  {seleccionada.cant_base}
                </Text>

                <Text className="mb-1 mt-4 text-sm text-text-soft">Cantidad ejecutada hoy</Text>
                <TextInput
                  testID="delta"
                  value={delta}
                  onChangeText={setDelta}
                  keyboardType="decimal-pad"
                  placeholder="0"
                  placeholderTextColor={TOKENS.textMute}
                  editable={!guardando}
                  autoFocus
                  className="h-fila rounded-md border border-line bg-bg px-3 font-mono text-base text-text"
                />

                <Text className="mb-1 mt-3 text-sm text-text-soft">Comentario (opcional)</Text>
                <TextInput
                  testID="comentario"
                  value={comentario}
                  onChangeText={setComentario}
                  placeholder="Nota para la bitácora"
                  placeholderTextColor={TOKENS.textMute}
                  editable={!guardando}
                  multiline
                  numberOfLines={3}
                  className="rounded-md border border-line bg-bg px-3 py-3 text-base text-text"
                />

                <Text className="mb-1 mt-3 text-sm text-text-soft">Evidencia (opcional)</Text>
                <Fotos fotos={fotos} onCambio={setFotos} deshabilitado={guardando} maximo={5} />

                {error ? <Text className="mt-2 text-sm text-danger">{error}</Text> : null}

                <View className="mt-5 flex-row gap-3">
                  <Pressable
                    onPress={cerrarCaptura}
                    disabled={guardando}
                    className="h-fila flex-1 items-center justify-center rounded-md border border-line"
                  >
                    <Text className="text-base text-text-soft">Cancelar</Text>
                  </Pressable>
                  <Pressable
                    onPress={guardarCaptura}
                    disabled={guardando}
                    className="h-fila flex-1 items-center justify-center rounded-md bg-accent disabled:opacity-60"
                  >
                    {guardando ? (
                      <ActivityIndicator color={TOKENS.surface} />
                    ) : (
                      <Text className="text-base font-medium text-accent-fg">Guardar</Text>
                    )}
                  </Pressable>
                </View>
              </>
            ) : null}
          </View>
        </View>
      </Modal>
    </View>
  );
}
