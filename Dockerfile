FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STACK_AGENT_STATE=/var/lib/stack-agent

RUN useradd --create-home --uid 10001 stackagent
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY stack_integration ./stack_integration
RUN pip install --no-cache-dir '.[api]'

RUN mkdir -p /var/lib/stack-agent && chown -R stackagent:stackagent /var/lib/stack-agent
USER stackagent
EXPOSE 8765
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health')"]
# Binds loopback inside the container by default, so a bare `docker run -p` exposes nothing.
# docker-compose.yml binds 0.0.0.0 in the container but publishes only 127.0.0.1 on the host.
CMD ["uvicorn", "stack_integration.api.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8765"]
