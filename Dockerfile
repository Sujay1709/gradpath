FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GF_PATHS_DATA=/data/grafana \
    GF_PATHS_LOGS=/tmp/grafana-logs \
    GF_PATHS_PLUGINS=/data/grafana/plugins \
    GF_PATHS_PROVISIONING=/app/gradpath/grafana/provisioning \
    GF_SERVER_HTTP_ADDR=127.0.0.1 \
    GF_SERVER_HTTP_PORT=3000 \
    GF_SERVER_ROOT_URL=%(protocol)s://%(domain)s:%(http_port)s/grafana/ \
    GF_SERVER_SERVE_FROM_SUB_PATH=true \
    GF_SERVER_DOMAIN=localhost \
    GF_AUTH_ANONYMOUS_ENABLED=true \
    GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer \
    GF_AUTH_DISABLE_LOGIN_FORM=true \
    GF_USERS_DEFAULT_THEME=light \
    GF_INSTALL_PLUGINS=marcusolsson-json-datasource

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg supervisor \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://apt.grafana.com/gpg.key | gpg --dearmor -o /etc/apt/keyrings/grafana.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" > /etc/apt/sources.list.d/grafana.list \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends grafana caddy \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY gradpath/requirements.txt /app/gradpath/requirements.txt
RUN pip install --no-cache-dir -r /app/gradpath/requirements.txt
COPY gradpath /app/gradpath
COPY Caddyfile /app/Caddyfile
COPY deploy/supervisord.conf /etc/supervisor/conf.d/gradpath.conf

RUN sed -i 's|url: http://localhost:8000|url: http://127.0.0.1:8000|' \
      /app/gradpath/grafana/provisioning/datasources/gradpath.yaml \
    && sed -i 's|/Users/sujaygopal/Desktop/MyProjects/IBM_BOB/gradpath/grafana/dashboards/main|/app/gradpath/grafana/dashboards/main|' \
      /app/gradpath/grafana/provisioning/dashboards/gradpath.yaml \
    && sed -i 's|/Users/sujaygopal/Desktop/MyProjects/IBM_BOB/gradpath/grafana/dashboards/detail|/app/gradpath/grafana/dashboards/detail|' \
      /app/gradpath/grafana/provisioning/dashboards/gradpath.yaml \
    && sed -i 's|/Users/sujaygopal/Desktop/MyProjects/IBM_BOB/gradpath/grafana/dashboards/legacy|/app/gradpath/grafana/dashboards/legacy|' \
      /app/gradpath/grafana/provisioning/dashboards/gradpath.yaml

EXPOSE 8080
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
