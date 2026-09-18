import { describe, expect, it } from "vitest";
import { handleImmediateCommand } from "../src/commands";
import { shouldDeferCommand } from "../src/index";
import type { DiscordInteraction, Env } from "../src/types";

describe("Worker commands", () => {
  it("status labels scraper mode as unauthenticated public data", async () => {
    const env = {
      ENVIRONMENT: "production",
      X_PROVIDER_MODE: "scraper",
      DB: {
        prepare: () => ({
          first: async () => ({ count: 2 })
        })
      }
    } as unknown as Env;
    const interaction = { data: { name: "status" } } as DiscordInteraction;

    const content = await handleImmediateCommand(interaction, env);

    expect(content).toContain("X Data Provider: Public Scraper");
    expect(content).toContain("Authentication: None");
    expect(content).toContain("Tracked Accounts: 2");
  });

  it("defers every command that can perform scraper or network work", () => {
    expect(shouldDeferCommand("twitter")).toBe(true);
    expect(shouldDeferCommand("track")).toBe(true);
    expect(shouldDeferCommand("refresh")).toBe(true);
    expect(shouldDeferCommand("collectnow")).toBe(true);
    expect(shouldDeferCommand("status")).toBe(false);
  });
});
