import React, { useEffect } from 'react';
import { IonApp, IonRouterOutlet, IonTabs, IonTabBar, IonTabButton, IonIcon, IonLabel, setupIonicReact } from '@ionic/react';
import { IonReactRouter } from '@ionic/react-router';
import { Route, Redirect } from 'react-router-dom';
import { carOutline, leafOutline, chatbubblesOutline, personOutline } from 'ionicons/icons';
import { StatusBar, Style } from '@capacitor/status-bar';
import { App as CapApp } from '@capacitor/app';
import { PushNotifications } from '@capacitor/push-notifications';
import { Capacitor } from '@capacitor/core';

import HomePage      from './pages/HomePage';
import SearchPage    from './pages/SearchPage';
import RidesPage     from './pages/RidesPage';
import BookingPage   from './pages/BookingPage';
import ChatPage      from './pages/ChatPage';
import CarbonPage    from './pages/CarbonPage';
import ProfilePage   from './pages/ProfilePage';

import '@ionic/react/css/core.css';
import '@ionic/react/css/normalize.css';
import '@ionic/react/css/structure.css';
import '@ionic/react/css/typography.css';
import './theme/variables.css';

setupIonicReact({ mode: 'ios', animated: true });

const App: React.FC = () => {
  useEffect(() => {
    if (Capacitor.isNativePlatform()) {
      StatusBar.setStyle({ style: Style.Dark });
      StatusBar.setBackgroundColor({ color: '#03080a' });
    }

    // Register push notifications
    if (Capacitor.isPluginAvailable('PushNotifications')) {
      PushNotifications.requestPermissions().then(result => {
        if (result.receive === 'granted') {
          PushNotifications.register();
        }
      });

      PushNotifications.addListener('pushNotificationReceived', notification => {
        console.log('Push received:', notification);
      });
    }

    // Handle back button on Android
    CapApp.addListener('backButton', ({ canGoBack }) => {
      if (!canGoBack) CapApp.exitApp();
    });
  }, []);

  return (
    <IonApp>
      <IonReactRouter>
        <IonTabs>
          <IonRouterOutlet>
            <Route exact path="/home"    component={HomePage}    />
            <Route exact path="/search"  component={SearchPage}  />
            <Route exact path="/rides"   component={RidesPage}   />
            <Route exact path="/booking" component={BookingPage} />
            <Route exact path="/chat"    component={ChatPage}    />
            <Route exact path="/carbon"  component={CarbonPage}  />
            <Route exact path="/profile" component={ProfilePage} />
            <Redirect exact from="/" to="/home" />
          </IonRouterOutlet>

          <IonTabBar slot="bottom">
            <IonTabButton tab="home" href="/home">
              <IonIcon icon={carOutline} />
              <IonLabel>Rides</IonLabel>
            </IonTabButton>
            <IonTabButton tab="chat" href="/chat">
              <IonIcon icon={chatbubblesOutline} />
              <IonLabel>Chat</IonLabel>
            </IonTabButton>
            <IonTabButton tab="carbon" href="/carbon">
              <IonIcon icon={leafOutline} />
              <IonLabel>Carbon</IonLabel>
            </IonTabButton>
            <IonTabButton tab="profile" href="/profile">
              <IonIcon icon={personOutline} />
              <IonLabel>Profile</IonLabel>
            </IonTabButton>
          </IonTabBar>
        </IonTabs>
      </IonReactRouter>
    </IonApp>
  );
};

export default App;
