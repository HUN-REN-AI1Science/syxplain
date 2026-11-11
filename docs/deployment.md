# Production deployment

`docker-compose.prod.yml` runs the full stack on one host:

| Service | Role |
|---|---|
| `postgres` | PostgreSQL: application data and Keycloak's schema |
| `keycloak` | Login, users and roles; served under `/keycloak` |
| `backend` | FastAPI: API, orchestration, discovery agent |
| `frontend` | nginx: the web app, reverse proxy for `/api`, `/docs` and `/keycloak`, and TLS |

PySR searches run on a Slurm cluster. Set that up first with [slurm.md](slurm.md).

## 1. Images

The CI workflow `.github/workflows/deploy.yml` builds the images and pushes them to the
GitHub Container Registry. It runs only in the canonical repository. To build your own
images:

```bash
docker build -t <registry>/syxplain-backend:latest -f backend/Dockerfile .
docker build -t <registry>/syxplain-frontend:latest \
  --build-arg VITE_KEYCLOAK_URL=https://syxplain.example.org/keycloak \
  --build-arg VITE_KEYCLOAK_REALM=syxplain \
  --build-arg VITE_KEYCLOAK_CLIENT_ID=syxplain-frontend \
  frontend
```

The Keycloak URL is compiled into the frontend, so build it for your domain. Point
`BACKEND_IMAGE` and `FRONTEND_IMAGE` at your images.

## 2. Environment

On the server, copy the repository files the stack needs (`docker-compose.prod.yml`,
`keycloak/`, `db/`). Then create `.env` with at least the following:

```bash
OPENAI_API_KEY=sk-...
POSTGRES_PASSWORD=<strong-password>
KC_DB_PASSWORD=<strong-password>
KEYCLOAK_ADMIN_USERNAME=<admin>
KEYCLOAK_ADMIN_PASSWORD=<strong-password>
KC_HOSTNAME=syxplain.example.org
KEYCLOAK_ISSUER=https://syxplain.example.org/keycloak/realms/syxplain
SERVER_NAME=syxplain.example.org
CORS_ORIGINS=https://syxplain.example.org

SLURM_API_URL=http://slurm.example.org:6820
SLURM_AUTH_TOKEN=<jwt>
SLURM_USER_NAME=<cluster-user>
SLURM_STAGING_DIR=/storage/<cluster-user>/syxplain
SLURM_CONTAINER_PATH=/storage/<cluster-user>/syxplain/containers/syxplain-worker.sif
WORKER_CALLBACK_URL=https://syxplain.example.org/api/internal
WORKER_CALLBACK_TOKEN=<random-secret>
```

[configuration.md](configuration.md) lists every other setting.

`BACKEND_CPU_LIMIT` must not exceed the host's CPU count. If it does, Docker refuses to
start the backend.

## 3. TLS

The frontend container serves HTTPS when a Let's Encrypt certificate for `SERVER_NAME`
exists under `/etc/letsencrypt/live/$SERVER_NAME/`. Otherwise it serves plain HTTP.

nginx answers ACME challenges from the `certbot_webroot` volume, so certbot on the host
can issue and renew certificates while the stack is running:

```bash
WEBROOT=$(docker volume inspect -f '{{ .Mountpoint }}' syxplain_certbot_webroot)
sudo certbot certonly --webroot -w "$WEBROOT" -d syxplain.example.org \
  --deploy-hook "docker exec syxplain-frontend nginx -s reload"
docker compose -f docker-compose.prod.yml up -d frontend   # switch to HTTPS
```

Check the renewal setup with `sudo certbot renew --dry-run`. Don't use certbot's
`standalone` mode: the frontend container holds port 80, so standalone renewals fail.

## 4. Start

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps   # all services healthy
```

Database migrations (Alembic) run when the backend starts.

## 5. Keycloak

On the first start, Keycloak imports `keycloak/realm-export.json`. Existing realms are
never re-imported. In the admin console (`https://<domain>/keycloak/admin`):

1. **Clients → syxplain-frontend.** Add `https://<domain>/*` to *Valid redirect URIs* and
   *Valid post logout redirect URIs*, and add `https://<domain>` to *Web origins*. The
   export only allows `localhost`.
2. **Realm settings → Email.** Configure SMTP. Self-registration requires email
   verification.
3. **Users → Role mapping.** Assign roles:
   - `syxplain-admin`: admin panel and all endpoints
   - `server-llm-access` (or your `SERVER_KEYS_ROLE`): may run analyses on the server's
     LLM keys. Other users bring their own key.
4. **Technical clients (optional).** For a chat platform or another program that connects
   as itself, create a client with `dev/create-technical-client.sh` and list the accepted
   clients in `KEYCLOAK_ALLOWED_CLIENTS`. See [MCP server and technical access](mcp.md).

## Updating

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

Run one deployment at a time. Two concurrent `up` runs race on container names and can
leave the backend stopped. The CI workflow serializes its deploys with a concurrency
group.
