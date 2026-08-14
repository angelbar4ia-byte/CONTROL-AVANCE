/**
 * Captura de avance — Residente (§5.2, §6, §12.5).
 *
 * Offline-first: lee y escribe directo contra la réplica SQLite local de
 * PowerSync (`usePowerSync`/`useQuery`), nunca contra la API HTTP. El sync
 * hacia Postgres lo hace PowerSync solo, en background, cuando hay
 * conexión (`src/sync/db.ts`).
 *
 * Los topes de §6 se validan aquí mismo, antes de escribir a SQLite, con
 * las mismas fórmulas que el backend
 * (`backend/src/obractrl/domain/avance/reglas.py`), portadas en
 * `src/lib/reglasAvance.ts`. Un rechazo de regla se muestra en la UI, nunca
 * falla en silencio.
 */

import { useState } from 'react';
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

import { obtenerDeviceId } from '@/lib/dispositivo';
import { generarId } from '@/lib/id';
import {
  aplicarCaptura,
  ErrorDeCaptura,
  type EstatusActividad,
} from '@/lib/reglasAvance';
import { useSesion } from '@/lib/sesion';
import { TOKENS } from '@/lib/tabs';

interface FilaActividad {
  id: string;
  descripcion: string;
  cant_base: number;
  cant_programada: number;
  cant_ejecutada: number;
  avance_pct: number;
  estatus: string;
  org_id: string;
  obra_clave: string | null;
}

const ETIQUETA_ESTATUS: Record<string, string> = {
  programada: 'Programada',
  en_proceso: 'En proceso',
  casi: 'Casi lista',
  pendiente_cierre: 'Cierre pendiente',
  concluida: 'Concluida',
  retrasada: 'Retrasada',
  extra_catalogo: 'Extra-catálogo',
};

/** Color por estatus, reusando los tokens del sistema de diseño (§12.10). */
function estiloEstatus(estatus: string): { bg: string; texto: string } {
  switch (estatus) {
    case 'concluida':
      return { bg: 'bg-ok-soft', texto: 'text-ok' };
    case 'retrasada':
      return { bg: 'bg-danger-soft', texto: 'text-danger' };
    case 'casi':
      return { bg: 'bg-warn-soft', texto: 'text-warn' };
    case 'pendiente_cierre':
      return { bg: 'bg-info-soft', texto: 'text-info' };
    case 'en_proceso':
      return { bg: 'bg-accent-soft', texto: 'text-accent' };
    default:
      return { bg: 'bg-elev', texto: 'text-text-mute' };
  }
}

export default function Pantalla() {
  const { sesion } = useSesion();
  const db = usePowerSync();

  const { data: actividades, isLoading } = useQuery<FilaActividad>(
    `SELECT a.id, a.descripcion, a.cant_base, a.cant_programada, a.cant_ejecutada,
            a.avance_pct, a.estatus, a.org_id, o.clave AS obra_clave
       FROM actividad a
       LEFT JOIN obra o ON o.id = a.obra_id
      WHERE a.estatus != 'concluida'
      ORDER BY (a.estatus = 'retrasada') DESC, a.fecha_inicio ASC`,
  );

  const [seleccionada, setSeleccionada] = useState<FilaActividad | null>(null);
  const [delta, setDelta] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  function abrirCaptura(actividad: FilaActividad) {
    setSeleccionada(actividad);
    setDelta('');
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
            '',
            '',
            'pendiente',
            deviceId,
            ahora,
          ],
        );

        // Reflejo local optimista: el total canónico lo recalcula el
        // servidor sumando los deltas (estatus "servidor-manda" en
        // sync/powersync.ts); esto solo evita que la pantalla se vea
        // desactualizada mientras no ha sincronizado.
        await tx.execute(
          `UPDATE actividad
              SET cant_ejecutada = ?, avance_pct = ?, estatus = ?
            WHERE id = ?`,
          [resultado.cantEjecutada, resultado.avancePct, resultado.estatus, seleccionada.id],
        );
      });

      setSeleccionada(null);
    } catch {
      setError('No se pudo guardar la captura en el dispositivo. Intenta de nuevo.');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Text className="text-2xl text-text">Avances</Text>
      <Text className="mt-2 text-md text-text-mute">Captura offline; se sincroniza al reconectar (§12.5).</Text>

      {isLoading ? (
        <View className="mt-10 items-center">
          <ActivityIndicator color={TOKENS.accent} />
        </View>
      ) : (
        <FlatList
          className="mt-4"
          data={actividades}
          keyExtractor={(item) => item.id}
          ListEmptyComponent={
            <Text className="mt-8 text-md text-text-mute">No hay actividades pendientes de captura.</Text>
          }
          renderItem={({ item }) => {
            const estilo = estiloEstatus(item.estatus);
            return (
              <Pressable
                onPress={() => abrirCaptura(item)}
                className="mb-3 rounded-lg border border-line bg-surface p-4 active:opacity-70"
              >
                <View className="flex-row items-start justify-between">
                  <View className="flex-1 pr-3">
                    {item.obra_clave ? (
                      <Text className="text-xs text-text-faint">{item.obra_clave}</Text>
                    ) : null}
                    <Text className="text-base text-text">{item.descripcion}</Text>
                  </View>
                  <View className={`rounded-full px-2 py-1 ${estilo.bg}`}>
                    <Text className={`text-xs ${estilo.texto}`}>
                      {ETIQUETA_ESTATUS[item.estatus] ?? item.estatus}
                    </Text>
                  </View>
                </View>

                <View className="mt-3 flex-row items-center justify-between">
                  <Text className="text-sm text-text-mute">
                    {item.cant_ejecutada} / {item.cant_programada} (base {item.cant_base})
                  </Text>
                  <Text className="text-sm font-medium text-text">{item.avance_pct}%</Text>
                </View>
              </Pressable>
            );
          }}
        />
      )}

      <Modal visible={seleccionada !== null} transparent animationType="fade" onRequestClose={cerrarCaptura}>
        <View className="flex-1 items-center justify-center bg-black/40 px-6">
          <View className="w-full rounded-lg bg-surface p-5">
            {seleccionada ? (
              <>
                <Text className="text-lg text-text">{seleccionada.descripcion}</Text>
                <Text className="mt-1 text-sm text-text-mute">
                  Ejecutado: {seleccionada.cant_ejecutada} · Programado: {seleccionada.cant_programada} · Base:{' '}
                  {seleccionada.cant_base}
                </Text>

                <Text className="mb-1 mt-4 text-sm text-text-soft">Cantidad ejecutada hoy</Text>
                <TextInput
                  value={delta}
                  onChangeText={setDelta}
                  keyboardType="decimal-pad"
                  placeholder="0"
                  placeholderTextColor={TOKENS.textMute}
                  editable={!guardando}
                  autoFocus
                  className="h-fila rounded-md border border-line bg-bg px-3 text-base text-text"
                />

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
