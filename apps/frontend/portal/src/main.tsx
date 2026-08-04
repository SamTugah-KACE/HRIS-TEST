import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import { App } from './App';
import { AuthProvider } from './auth/AuthProvider';

const enterpriseFaviconIcoUrl = new URL('../hris_enterprise_favicon.ico', import.meta.url).href;
const enterpriseAppIconUrl = new URL('../hris_enterprise_app_icon_512.png', import.meta.url).href;

function applyBrandingIcons() {
  const iconLink = document.querySelector<HTMLLinkElement>("link[rel='icon']") ?? document.createElement('link');
  iconLink.setAttribute('rel', 'icon');
  iconLink.setAttribute('type', 'image/x-icon');
  iconLink.setAttribute('href', enterpriseFaviconIcoUrl);
  if (!iconLink.parentNode) document.head.appendChild(iconLink);

  const appleLink = document.querySelector<HTMLLinkElement>("link[rel='apple-touch-icon']") ?? document.createElement('link');
  appleLink.setAttribute('rel', 'apple-touch-icon');
  appleLink.setAttribute('href', enterpriseAppIconUrl);
  if (!appleLink.parentNode) document.head.appendChild(appleLink);
}

applyBrandingIcons();

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </React.StrictMode>
);
