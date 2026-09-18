import nacl from "tweetnacl";
import type { DiscordInteraction, Env } from "./types";

export const InteractionType = {
  Ping: 1,
  ApplicationCommand: 2
} as const;

export const InteractionResponseType = {
  Pong: 1,
  ChannelMessageWithSource: 4,
  DeferredChannelMessageWithSource: 5
} as const;

export async function verifyDiscordRequest(request: Request, publicKey: string): Promise<boolean> {
  const signature = request.headers.get("x-signature-ed25519");
  const timestamp = request.headers.get("x-signature-timestamp");
  if (!signature || !timestamp) {
    return false;
  }
  const body = await request.clone().text();
  return nacl.sign.detached.verify(
    new TextEncoder().encode(timestamp + body),
    hexToBytes(signature),
    hexToBytes(publicKey)
  );
}

export function jsonResponse(payload: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(payload), {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {})
    }
  });
}

export function message(content: string, ephemeral = false): Response {
  return jsonResponse({
    type: InteractionResponseType.ChannelMessageWithSource,
    data: {
      content,
      flags: ephemeral ? 64 : undefined
    }
  });
}

export function deferred(ephemeral = true): Response {
  return jsonResponse({
    type: InteractionResponseType.DeferredChannelMessageWithSource,
    data: { flags: ephemeral ? 64 : undefined }
  });
}

export async function sendFollowup(env: Env, interaction: DiscordInteraction, content: string) {
  if (!env.DISCORD_BOT_TOKEN) {
    console.log(JSON.stringify({ event: "missing_discord_bot_token_for_followup" }));
    return;
  }
  await fetch(
    `https://discord.com/api/v10/webhooks/${env.DISCORD_APPLICATION_ID}/${interaction.token}`,
    {
      method: "POST",
      headers: {
        authorization: `Bot ${env.DISCORD_BOT_TOKEN}`,
        "content-type": "application/json"
      },
      body: JSON.stringify({ content })
    }
  );
}

export function optionValue(interaction: DiscordInteraction, name: string): string | undefined {
  return interaction.data?.options?.find((option) => option.name === name)?.value;
}

export function isAdministrator(interaction: DiscordInteraction): boolean {
  const permissions = interaction.member?.permissions;
  if (!permissions) {
    return false;
  }
  const permissionBits = BigInt(permissions);
  return (permissionBits & 0x8n) === 0x8n;
}

function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let index = 0; index < out.length; index += 1) {
    out[index] = Number.parseInt(hex.slice(index * 2, index * 2 + 2), 16);
  }
  return out;
}

