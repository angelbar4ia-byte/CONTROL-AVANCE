import { Text, View } from 'react-native';

export default function Pantalla() {
  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Text className="text-2xl text-text">Incidencias</Text>
      <Text className="mt-2 text-md text-text-mute">Programar y atender incidencias (§6).</Text>
    </View>
  );
}
