import { Text, View } from 'react-native';

export default function Pantalla() {
  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Text className="text-2xl text-text">Calidad</Text>
      <Text className="mt-2 text-md text-text-mute">Calificación de calidad de los trabajos (§7.8).</Text>
    </View>
  );
}
