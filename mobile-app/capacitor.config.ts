import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId:    'co.ke.gogreen.rider',
  appName:  'Go Green',
  webDir:   'dist',
  bundledWebRuntime: false,
  server: {
    androidScheme: 'https',
    // For dev: point to your Go Green backend
    // url: 'http://192.168.x.x:5000',
    // cleartext: true,
  },
  plugins: {
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
    LocalNotifications: {
      smallIcon:     'ic_stat_gogreen',
      iconColor:     '#00e87a',
    },
    StatusBar: {
      style:           'DARK',
      backgroundColor: '#03080a',
    },
    Geolocation: {
      // iOS only — prompts user for location permission
    },
  },
};

export default config;
