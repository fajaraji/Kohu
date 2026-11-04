// Cloudflare Worker in front of the Kohu container (Cloudflare Containers).
// Every request goes to one container instance, so the in-memory rate
// limiter in public demo mode sees all traffic. Secrets come from
// `wrangler secret put` and are passed to the container as environment
// variables; nothing secret is stored in this repository.
import { Container, getContainer } from "@cloudflare/containers";

export class KohuContainer extends Container {
  defaultPort = 8000;
  sleepAfter = "20m";
  enableInternet = true; // Meta API and the Postgres host

  constructor(ctx, env) {
    super(ctx, env);
    this.envVars = {
      DATABASE_URL: env.DATABASE_URL,
      KOHU_ALLOW_REMOTE_DB: "1",
      KOHU_SESSION_SECRET: env.KOHU_SESSION_SECRET,
      META_API_KEY: env.META_API_KEY,
      KOHU_PUBLIC_DEMO: env.KOHU_PUBLIC_DEMO || "1",
      META_SPEND_LIMIT_USD: env.META_SPEND_LIMIT_USD || "10",
      KOHU_BEHIND_CLOUDFLARE: "1",
      // Seed once from your machine instead (see docs/deploy.md); seeding on
      // every cold start would slow the first request by about a minute.
      KOHU_SEED_ON_START: env.KOHU_SEED_ON_START || "0",
    };
  }
}

export default {
  async fetch(request, env) {
    return getContainer(env.KOHU, "kohu").fetch(request);
  },
};
