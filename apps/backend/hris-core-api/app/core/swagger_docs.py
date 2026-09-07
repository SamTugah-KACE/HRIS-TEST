"""Swagger UI with a per-response script nonce and a narrowly scoped CSP."""
import json
import secrets

from fastapi.openapi.docs import get_swagger_ui_html


def swagger_response(*, openapi_url: str, csrf_cookie: str, csrf_header: str):
    nonce = secrets.token_urlsafe(32)
    # Same-origin session cookies authenticate Try it out. Only attach CSRF to
    # same-origin requests; never forward it to another server selected in Swagger.
    interceptor = """(request) => {
      if (new URL(request.url, window.location.href).origin === window.location.origin) {
        request.credentials = 'same-origin';
        const prefix = COOKIE_NAME + '=';
        const cookie = document.cookie.split(';').map(x => x.trim()).find(x => x.startsWith(prefix));
        if (cookie) request.headers[HEADER_NAME] = decodeURIComponent(cookie.substring(prefix.length));
      }
      return request;
    }""".replace("COOKIE_NAME", json.dumps(csrf_cookie)).replace("HEADER_NAME", json.dumps(csrf_header))
    response = get_swagger_ui_html(
        openapi_url=openapi_url, title="HRIS Core API — Swagger",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css",
        swagger_favicon_url="data:,",
        swagger_ui_parameters={"persistAuthorization": False},
    )
    html = response.body.decode().replace("<script>", f'<script nonce="{nonce}">')
    html = html.replace("const ui = SwaggerUIBundle({", "const ui = SwaggerUIBundle({\nrequestInterceptor: " + interceptor + ",")
    response.body = html.encode()
    response.headers["content-length"] = str(len(response.body))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'self'"
    )
    return response
