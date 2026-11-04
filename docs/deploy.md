# Deploying Kohu

Two routes. Vercel is free and is the one to use for the demo. Cloudflare Containers works too but needs a paid Workers plan.

Both need a Postgres 16 database that allows the `pg_trgm` extension, and both seed it the same way: the `seed` job in `.github/workflows/deploy.yml` reloads the demo data from the committed corpus and model cache on every push to `main` or `kohu-v2`, once the `KOHU_DATABASE_URL` repository secret exists. It passes no Meta key, so it can never make a paid call.

## Vercel (free Hobby plan)

`index.py` is the entry point and `vercel.json` sends every request to it, so the API and the UI run as one Python function. On Vercel the app turns on public demo mode, reads the client IP from Vercel's `x-real-ip`, counts Meta usage in the database and stops at 10 USD.

1. **Import.** On vercel.com choose Add New, Project, and import `fajaraji/Kohu`. Keep the framework preset as Other; `vercel.json` decides the build. The very first build uses `main`, which may not have `vercel.json` yet; that is fine.
2. **Production branch.** Project Settings, Environments, Production: set the branch to `kohu-v2` (or merge `kohu-v2` into `main` and keep `main`). Preview deployments on other branches are private by default, so judges need the production address.
3. **Database.** Project, Storage, Create Database, Neon (free). Connect it to the project. This adds `DATABASE_URL` to the project's environment variables.
4. **Environment variables.** Project Settings, Environment Variables, for Production:

   | Name | Value |
   |---|---|
   | `META_API_KEY` | your Meta Model API key |
   | `KOHU_SESSION_SECRET` | a long random string (at least 16 characters) |

5. **Seed.** Copy the `DATABASE_URL` value from Vercel (Storage, your database, `.env.local` tab) into a GitHub repository secret named `KOHU_DATABASE_URL` (Repository Settings, Secrets and variables, Actions). Then re-run the latest "Test and deploy" run from the Actions tab, or push to `kohu-v2`.
6. **Deploy.** Redeploy from Vercel's Deployments tab, or push to the production branch. Every later push deploys by itself.

The address is `https://kohu.vercel.app` if that name is free, otherwise `https://kohu-<something>.vercel.app`; it is shown on the project page and can be changed under Settings, Domains. Answers take 10 to 40 seconds, well inside the Hobby function limit.

## Cloudflare Containers (paid Workers plan)

A small Worker (`cloudflare/worker.js`) fronts one container built from `Dockerfile`. The `deploy` job runs `wrangler deploy` and sets the Worker's secrets with `wrangler secret bulk` from stdin.

1. **Plan.** Subscribe the Cloudflare account to Workers Paid; Containers are not on the free plan.
2. **API token.** My Profile, API Tokens, Create Token: start from "Edit Cloudflare Workers" and add Account, Containers, Edit. Copy the Account ID from Workers & Pages.
3. **GitHub secrets:** `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `KOHU_DATABASE_URL`, `META_API_KEY`, and optionally `KOHU_SESSION_SECRET` (a new random one is made per deploy if unset, which only signs visitors out).
4. **Deploy.** Push to `kohu-v2` or `main`, or re-run the latest run. The address is `https://kohu.<your-account-subdomain>.workers.dev`.

## Notes

- **Rate limits.** On Cloudflare one container sees all traffic. On Vercel the per-visitor and per-IP limits are kept in memory per instance, so they are looser; the 10 USD Meta spend stop is counted in the database and holds on both.
- **Uploads are off.** Public demo mode disables video uploads, so no persistent disk is needed. New model results are cached under `/tmp` on Vercel.
- **Resetting the demo.** Re-run the latest deploy from the Actions tab (the seed reloads the corpus), or run `DATABASE_URL=... KOHU_ALLOW_REMOTE_DB=1 python video/reset_demo.py` from a machine with Python.
