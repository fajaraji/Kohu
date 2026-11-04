# Deploying Kohu on Cloudflare

Kohu runs as a container on Cloudflare Containers. A small Worker (`cloudflare/worker.js`) sits in front of it and passes secrets to it as environment variables. Postgres runs outside Cloudflare.

- **What deploys:** `.github/workflows/deploy.yml` runs the tests on every push. On a push to `main` or `kohu-v2`, once the repository secrets below exist, it seeds the database from the committed corpus and model cache, runs `wrangler deploy` (which builds `Dockerfile` on the GitHub runner and rolls out the container), and sets the app secrets on the Worker. Until the secrets exist, the deploy job is skipped with a notice instead of failing.
- **Address:** `https://kohu.<your-account-subdomain>.workers.dev`. You choose the subdomain once in the Cloudflare dashboard (Workers & Pages). The deploy log prints the address. A custom domain can be added later under the Worker's Settings > Domains & Routes.
- **Cost note:** Cloudflare Containers needed the Workers Paid plan when this was written. Check Cloudflare's current pricing before you start.

## One-time setup

Everything is set in the browser. You do not need wrangler or Python on your machine.

1. **Postgres.** Create a Postgres 16 database that allows the `pg_trgm` extension, for example on Neon or Supabase. Copy its connection string with `sslmode=require`.
2. **Cloudflare.** Subscribe the account to Workers Paid. Create an API token at My Profile > API Tokens > Create Token: start from the "Edit Cloudflare Workers" template and add Account > Containers > Edit. Copy your Account ID from Workers & Pages.
3. **GitHub secrets.** Repository > Settings > Secrets and variables > Actions > New repository secret:

   | Secret | Value |
   |---|---|
   | `CLOUDFLARE_API_TOKEN` | the token from step 2 |
   | `CLOUDFLARE_ACCOUNT_ID` | the Account ID from step 2 |
   | `KOHU_DATABASE_URL` | the connection string from step 1 |
   | `META_API_KEY` | your Meta Model API key |
   | `KOHU_SESSION_SECRET` | optional: a long random string. If unset, each deploy makes a new one, which only signs visitors out |

4. **Deploy.** Push to `kohu-v2` or `main`, or re-run the latest "Test and deploy" run from the Actions tab. The first deploy takes several minutes because the image is built and pushed.

The deploy sets `META_SPEND_LIMIT_USD=10`. `KOHU_PUBLIC_DEMO=1` and `KOHU_BEHIND_CLOUDFLARE=1` are fixed in the Worker. The seed step gets no Meta key, so it can never make a paid call. The first request after the container has been idle for 20 minutes takes a few seconds while it starts.

## Notes

- **One instance.** The container runs as a single instance (`max_instances: 1`), so the rate limiter sees all traffic.
- **Uploads are off.** Public demo mode disables video uploads, so the container needs no persistent disk.
- **Resetting the demo.** Re-run the latest deploy from the Actions tab (the seed reloads the corpus), or run `DATABASE_URL=... KOHU_ALLOW_REMOTE_DB=1 python video/reset_demo.py` from a machine with Python.
