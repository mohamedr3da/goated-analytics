import { deferred, InteractionResponseType, InteractionType, jsonResponse, message, sendFollowup, verifyDiscordRequest } from "./discord";
import { handleImmediateCommand, refreshCommand, runCollection, trackCommand, twitterCommand } from "./commands";
import { fetchPublicXDiagnostics } from "./public-scraper";
import type { DiscordInteraction, Env } from "./types";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/__scraper-smoke/rawdogmoon") {
      if (env.SCRAPER_SMOKE_ENABLED !== "true") {
        return new Response("Not found", { status: 404 });
      }
      return jsonResponse(await fetchPublicXDiagnostics("rawdogmoon"));
    }
    if (request.method !== "POST") {
      return new Response("Not found", { status: 404 });
    }
    if (!(await verifyDiscordRequest(request, env.DISCORD_APPLICATION_PUBLIC_KEY))) {
      return new Response("Invalid signature", { status: 401 });
    }
    const interaction = (await request.json()) as DiscordInteraction;
    if (interaction.type === InteractionType.Ping) {
      return jsonResponse({ type: InteractionResponseType.Pong });
    }
    if (interaction.type !== InteractionType.ApplicationCommand) {
      return message("Unsupported interaction type.", true);
    }
    if (shouldDeferCommand(interaction.data?.name)) {
      ctx.waitUntil(
        deferredCommand(interaction, env)
          .then((content) => sendFollowup(env, interaction, content))
          .catch((error) => sendFollowup(env, interaction, `Command failed: ${String(error)}`))
      );
      return deferred(true);
    }
    const content = await handleImmediateCommand(interaction, env);
    return message(content, false);
  },

  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    await runCollection(env);
  }
};

export function shouldDeferCommand(name: string | undefined): boolean {
  return name === "twitter" || name === "track" || name === "refresh" || name === "collectnow";
}

async function deferredCommand(interaction: DiscordInteraction, env: Env): Promise<string> {
  if (interaction.data?.name === "twitter") {
    return twitterCommand(interaction, env);
  }
  if (interaction.data?.name === "track") {
    return trackCommand(interaction, env);
  }
  if (interaction.data?.name === "refresh") {
    return refreshCommand(interaction, env);
  }
  if (interaction.data?.name === "collectnow") {
    const result = await runCollection(env);
    return `Collection finished: ${result.successes} succeeded / ${result.failures} failed.`;
  }
  return "Unknown deferred command.";
}
