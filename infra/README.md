# infra

Deployment and infrastructure files.

- Local development: `docker-compose.yml` sits at the repo root so `docker compose up`
  works from there. It runs the core DB (PostGIS), the separate identity-vault DB,
  Redis, MinIO and Mailpit.
- Hosting (later): Oracle Cloud Always Free in an Indian region, Cloudflare R2 for
  photos, Brevo for email. Manifests will be added here when we deploy.
