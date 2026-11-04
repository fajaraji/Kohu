# Deploying Kohu on Cloudflare

Kohu runs as a container on Cloudflare Containers. A small Worker (`cloudflare/worker.js`) sits in front of it and passes secrets to it as environment variables. Postgres runs outside Cloudflare.

- **What deploys:** `.github/workflows/deploy.yml` runs the tests on every push. On a push to `main` it then runs `wrangler deploy`, which builds `Dockerfile` and rolls out the container.
- **Address:** `https://kohu.<your-account-subdomain>.workers.dev`. Cloudflare picks the subdomain when the account is created (Workers & Pages > Overview). A custom domain can be added later under the Worker's Settings > Domains & Routes.
- **Status:** this setup has not been deployed. In the build environment `wrangler deploy --dry-run --containers-rollout=none` bundled the Worker and checked the bindings, and the image itself was built and run separately. No Cloudflare account or credential was used.
- **Cost note:** Cloudflare Containers needed the Workers Paid plan when this was written. Check Cloudflare's current pricing before you start.

## One-time setup

1. **Postgres.** Create a Postgres 16 database with the `pg_trgm` extension, for example on Neon or Supabase (both allow it). Copy its connection string with `sslmode=require`.
2. **Seed it once from your machine** (this makes no new Meta calls; results come from `corpus/spark-cache/`):

   ```bash
   DATABASE_URL='postgresql://...sslmode=require' KOHU_ALLOW_REMOTE_DB=1 ./seed.sh
   ```

3. **Cloudflare API token.** Dashboard > My Profile > API Tokens > Create Token. Start from the "Edit Cloudflare Workers" template and add Account > Containers > Edit. Note your Account ID (Workers & Pages > Overview).
4. **GitHub secrets.** Repository > Settings > Secrets and variables > Actions. Add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
5. **App secrets in Cloudflare.** On your machine run `npm install` and `npx wrangler login`, then deploy once and set the four secrets:

   ```bash
   npx wrangler deploy
   ```

   ```bash
   npx wrangler secret put DATABASE_URL
   ```

   ```bash
   npx wrangler secret put KOHU_SESSION_SECRET
   ```

   ```bash
   npx wrangler secret put META_API_KEY
   ```

   ```bash
   npx wrangler secret put META_SPEND_LIMIT_USD
   ```

   Use a long random value for `KOHU_SESSION_SECRET` (at least 16 characters) and `10` for the spend limit. `KOHU_PUBLIC_DEMO=1` and `KOHU_BEHIND_CLOUDFLARE=1` are already set in the Worker.

After this, every push or merge to `main` tests and deploys automatically. The first request after the container has been idle for 20 minutes takes a few seconds while it starts.

## Notes

- **One instance.** The container runs as a single instance (`max_instances: 1`), so the rate limiter sees all traffic.
- **Uploads are off.** Public demo mode disables video uploads, so the container needs no persistent disk.
- **Resetting the demo.** Run `DATABASE_URL=... KOHU_ALLOW_REMOTE_DB=1 python video/reset_demo.py` from your machine.
