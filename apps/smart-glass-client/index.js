import { registerRootComponent } from 'expo';
import { Platform } from 'react-native';
import AppNative from './App';
import AppWeb from './App.web';

const App = Platform.OS === 'web' ? AppWeb : AppNative;

registerRootComponent(App);
