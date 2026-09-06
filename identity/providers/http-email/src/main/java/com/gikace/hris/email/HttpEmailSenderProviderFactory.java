package com.gikace.hris.email;

import org.keycloak.Config;
import org.keycloak.email.EmailSenderProvider;
import org.keycloak.email.EmailSenderProviderFactory;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;

public final class HttpEmailSenderProviderFactory implements EmailSenderProviderFactory {
    @Override public EmailSenderProvider create(KeycloakSession session) { return new HttpEmailSenderProvider(); }
    @Override public void init(Config.Scope config) { }
    @Override public void postInit(KeycloakSessionFactory factory) { }
    @Override public void close() { }
    @Override public String getId() { return "https"; }
}
