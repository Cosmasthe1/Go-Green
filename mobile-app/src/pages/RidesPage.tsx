import React from 'react';
import { IonPage, IonContent, IonHeader, IonToolbar, IonTitle } from '@ionic/react';
import { Redirect } from 'react-router-dom';

// RidesPage is a thin redirect shell — the real ride list is on SearchPage
const RidesPage: React.FC = () => <Redirect to="/home" />;
export default RidesPage;
