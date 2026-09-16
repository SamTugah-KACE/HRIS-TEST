FROM quay.io/keycloak/keycloak:26.5.4 AS builder
ENV KC_DB=postgres KC_HEALTH_ENABLED=true
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.5.4
COPY --from=builder /opt/keycloak/ /opt/keycloak/
COPY themes/hris-platform /opt/keycloak/themes/hris-platform
ENV KC_DB=postgres KC_HEALTH_ENABLED=true
# Stock Keycloak SMTP provider. Deliberately no custom HTTPS provider jar or SPI.
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized", "--import-realm"]
