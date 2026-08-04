import Keycloak from 'keycloak-js';

const keycloakUrl = import.meta.env.VITE_KEYCLOAK_URL as string;
const realm = import.meta.env.VITE_KEYCLOAK_REALM as string;
const clientId = import.meta.env.VITE_KEYCLOAK_CLIENT_ID as string;

if (!keycloakUrl || !realm || !clientId) {
  // Fail fast in misconfigured deployments
  // eslint-disable-next-line no-console
  console.error('Keycloak configuration is missing. Check VITE_KEYCLOAK_* env variables.');
}

export const keycloak = new Keycloak({
  url: keycloakUrl,
  realm,
  clientId
});
