package com.gikace.hris.email;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;
import org.keycloak.email.EmailException;
import org.keycloak.email.EmailSenderProvider;
import org.keycloak.models.UserModel;

public final class HttpEmailSenderProvider implements EmailSenderProvider {
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(20)).build();

    @Override
    public void send(Map<String, String> config, UserModel user, String subject,
                     String textBody, String htmlBody) throws EmailException {
        if (user == null || user.getEmail() == null || user.getEmail().isBlank()) {
            throw new EmailException("No email address configured for the user");
        }
        send(config, user.getEmail(), subject, textBody, htmlBody);
    }

    @Override
    public void send(Map<String, String> config, String address, String subject,
                     String textBody, String htmlBody) throws EmailException {
        String provider = env("EMAIL_HTTP_PROVIDER", "resend");
        if (!"resend".equalsIgnoreCase(provider)) throw new EmailException("Unsupported HTTPS email provider");
        String apiKey = env("EMAIL_HTTP_API_KEY", "");
        String apiUrl = env("EMAIL_HTTP_API_URL", "https://api.resend.com/emails");
        String from = env("SMTP_FROM_EMAIL", config == null ? "" : config.getOrDefault("from", ""));
        if (apiKey.isBlank() || from.isBlank() || !apiUrl.startsWith("https://")) {
            throw new EmailException("HTTPS email provider configuration is incomplete");
        }
        String payload = "{\"from\":\"" + json(from) + "\",\"to\":[\"" + json(address)
            + "\"],\"subject\":\"" + json(subject) + "\",\"text\":\"" + json(textBody)
            + "\",\"html\":\"" + json(htmlBody == null ? "" : htmlBody) + "\"}";
        HttpRequest request = HttpRequest.newBuilder(URI.create(apiUrl)).timeout(Duration.ofSeconds(20))
            .header("Authorization", "Bearer " + apiKey).header("Content-Type", "application/json")
            .header("User-Agent", "GI-KACE-HRIS-Keycloak/1.0")
            .POST(HttpRequest.BodyPublishers.ofString(payload)).build();
        try {
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new EmailException("HTTPS email provider rejected delivery with status " + response.statusCode());
            }
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw new EmailException("HTTPS email delivery was interrupted", exc);
        } catch (EmailException exc) {
            throw exc;
        } catch (Exception exc) {
            throw new EmailException("HTTPS email delivery failed", exc);
        }
    }

    @Override
    public void validate(Map config) throws EmailException {
        String apiKey = env("EMAIL_HTTP_API_KEY", "");
        String apiUrl = env("EMAIL_HTTP_API_URL", "https://api.resend.com/emails");
        String from = env("SMTP_FROM_EMAIL", config == null ? "" : String.valueOf(config.get("from")));
        if (apiKey.isBlank()) throw new EmailException("EMAIL_HTTP_API_KEY is required");
        if (from.isBlank() || "null".equals(from)) throw new EmailException("SMTP_FROM_EMAIL is required");
        if (!apiUrl.startsWith("https://")) throw new EmailException("EMAIL_HTTP_API_URL must use HTTPS");
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? (fallback == null ? "" : fallback) : value.trim();
    }

    private static String json(String value) {
        if (value == null) return "";
        StringBuilder out = new StringBuilder(value.length() + 16);
        for (char c : value.toCharArray()) {
            switch (c) {
                case '\\': out.append("\\\\"); break;
                case '"': out.append("\\\""); break;
                case '\n': out.append("\\n"); break;
                case '\r': out.append("\\r"); break;
                case '\t': out.append("\\t"); break;
                default:
                    if (c < 0x20) out.append(String.format("\\u%04x", (int)c)); else out.append(c);
            }
        }
        return out.toString();
    }

    @Override public void close() { }
}
