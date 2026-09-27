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
CMD ["uvicorn", "stack_integration.api.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8765"]
