# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-trixie AS base
RUN apt-get update && apt-get upgrade --yes && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements/base.txt requirements/base.txt
COPY requirements/runtime.lock requirements/runtime.lock
RUN pip install --no-cache-dir -r requirements/base.txt

FROM base AS development
COPY requirements/development.txt requirements/development.txt
RUN pip install --no-cache-dir -r requirements/development.txt
COPY . .

FROM development AS quality
CMD ["sh", "-c", "black --config .black --check app tests scripts && ruff check app tests scripts"]

FROM development AS test
COPY requirements/test.txt requirements/test.txt
RUN pip install --no-cache-dir -r requirements/test.txt
CMD ["pytest", "--maxfail=10"]

FROM base AS security
COPY requirements/security.txt requirements/security.txt
RUN pip install --no-cache-dir -r requirements/security.txt
CMD ["pip-audit", "--requirement", "requirements/base.txt"]

FROM base AS production
RUN apt-get purge --yes perl && rm -rf /var/lib/apt/lists/*
RUN python -m pip uninstall --yes pip
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app     && mkdir -p /data/content && chown app:app /data/content
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 migrations ./migrations
COPY --chown=10001:10001 pyproject.toml ./pyproject.toml
COPY --chown=10001:10001 scripts ./scripts
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.authentication.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
