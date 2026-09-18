# Cloud Computing — Activity 4

**Object storage and caching for HTTP services using Redis and S3**

Author: Maria Antonella Galli de Sasiain

This delivery continues the Week 3 result. Two FastAPI services —
`authentication` and `files`— keep the same HTTP contracts and the same
domain logic, while two storage backends are replaced through dependency
injection:

| Data | Was | Now | Why |
|---|---|---|---|
| Session tokens | PostgreSQL table | **Redis** | Small, read on every request, expected to expire on their own, shared by every worker |
| File content | Local volume | **S3** (MinIO) | Large, immutable, never joined; belongs outside the relational database |

User accounts, file metadata and audit events stay in PostgreSQL, because
those are exactly the data that need transactions and queries.

## The point: the backends are interchangeable

Neither the domain services nor the routers nor the domain tests know which
backend is in use. Every adapter satisfies a `Protocol` declared by the
domain, and the choice is made in a single place per app:

```python
# app/authentication/dependency_injection/container.py
return RedisSessions(settings.redis_url, settings.auth_session_idle_seconds)
#      ^^^^^^^^^^^^^ swap for PostgresSessions() and the app still works

# app/files/dependency_injection/container.py
return S3ContentStorage(...)
#      ^^^^^^^^^^^^^^^^ swap for LocalContentStorage(settings.content_root)
```

This is not a claim in a document: it is enforced by
`tests/test_interchangeability.py`, which checks that every adapter
implements its port with matching signatures, that the domain never imports
a concrete adapter, and that only the composition roots name one. The domain
suite itself is the live proof — it runs against PostgreSQL and a temporary
directory while production runs Redis and S3, with no change to the services.

## Layout

Each app follows the four required folders:

```
app/<app>/
├── api/                     routers: HTTP in, HTTP out, nothing else
├── domain/                  business objects, ports (Protocol) and services
├── persistence/             one adapter per backend
│   ├── repositories.py      PostgreSQL
│   ├── redis_sessions.py    Redis            (authentication)
│   ├── content.py           local volume     (files)
│   └── s3.py                S3 / MinIO       (files)
└── dependency_injection/    composition root: the only place naming adapters
```

## Design notes

**Redis stores the idle timeout as a TTL.** The session key carries an
expiry and `touch()` simply pushes it forward with `EXPIRE`. Expiry stops
being application logic, expired sessions cost nothing, and several workers
share one session store. The absolute limit stays in the payload, because
that one must *not* move.

**One active session per user** was a unique constraint in PostgreSQL. A
key-value store has no constraints, so the adapter maintains a second key
(`user:<id>` → digest) and writes both in one pipeline.

**The port carries the owner's email.** Redis cannot join, so the session
has to be denormalised; the relational adapter ignores the argument. Putting
it in the port is what keeps the two swappable.

**Blobs are deleted after the metadata transaction commits.** Object storage
cannot take part in a database transaction, so one failure mode must be
chosen. Deleting the blob first would let a rollback leave metadata pointing
at nothing — permanently unreadable. Deleting after leaves, at worst, an
unreferenced object that costs storage and nothing else.

**`GET /files/{id}` returns a signed URL.** The client can download straight
from object storage instead of streaming through an API worker. The link
expires on its own and carries no long-lived credentials. The local adapter
returns `None` for it: a volume has no address, and that is a capability
difference rather than a failure.

## Running it

```bash
python scripts/configure.py      # generates .env with random credentials
docker compose up --build --wait authentication-api files-api
```

| | |
|---|---|
| Authentication | http://localhost:8101/docs |
| Files | http://localhost:8102/docs |
| MinIO console | http://localhost:9090 |

`/healthcheck` reports that the process is alive; `/ready` additionally
proves that PostgreSQL and the service's own backend (Redis or S3) answer.

## Tests

```bash
docker compose --profile test run --rm --build test          # everything
docker compose --profile quality run --rm quality            # Black + Ruff
docker compose --profile security run --rm security          # pip-audit
```

| Suite | Needs |
|---|---|
| `test_interchangeability.py` | nothing — structural checks |
| `test_redis_sessions.py` | Redis; skips itself when unreachable |
| `test_s3_storage.py` | MinIO; skips itself when unreachable |
| the rest (domain, API, persistence) | PostgreSQL only |

## CI/CD

| Workflow | Trigger | Does |
|---|---|---|
| `format.yml` | every pull request | Black and Ruff — seconds, no Docker |
| `ci.yml` | push to main, pull requests | build, quality, tests, live HTTP, dependency audit |
| `docker-publish.yml` | push to main and `v*` tags | builds the production image and pushes it to Docker Hub |

Publishing needs two repository secrets: `DOCKERHUB_USERNAME` and
`DOCKERHUB_TOKEN` (an access token with write scope, not the account
password — a token can be revoked on its own). Images are tagged `latest` on
the default branch, with the version on a tag, and always with the commit
sha so any deployment traces back to the code that produced it.

## Security

Credentials are generated locally by `scripts/configure.py`, which never
prints them and never overwrites an existing `.env`; that file is git-ignored.
The production image runs as a non-root user with a read-only filesystem and
all capabilities dropped. Redis publishes no port and is reachable only from
the internal network. Object keys are opaque UUIDs, never derived from
user-supplied filenames.
