FROM ghcr.io/astral-sh/uv:0.10.7@sha256:edd1fd89f3e5b005814cc8f777610445d7b7e3ed05361f9ddfae67bebfe8456a AS uv
FROM python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY datasets ./datasets
COPY rubrics ./rubrics
COPY policies ./policies
RUN uv sync --locked --no-dev --link-mode copy
RUN useradd --uid 10001 --create-home gates && mkdir -p /data/artifacts && chown -R gates:gates /app /data
ENV PATH="/app/.venv/bin:$PATH" GATES_ARTIFACT_ROOT="/data/artifacts"
USER 10001
EXPOSE 8000
CMD ["uvicorn", "agent_release_gates.settings:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
