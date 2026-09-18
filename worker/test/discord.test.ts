import nacl from "tweetnacl";
import { describe, expect, it } from "vitest";
import { verifyDiscordRequest } from "../src/discord";

function bytesToHex(bytes: Uint8Array): string {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

describe("Discord verification", () => {
  it("accepts valid Ed25519 signatures", async () => {
    const keyPair = nacl.sign.keyPair();
    const body = JSON.stringify({ type: 1 });
    const timestamp = "1790000000";
    const signature = nacl.sign.detached(
      new TextEncoder().encode(timestamp + body),
      keyPair.secretKey
    );
    const request = new Request("https://example.com", {
      method: "POST",
      headers: {
        "x-signature-ed25519": bytesToHex(signature),
        "x-signature-timestamp": timestamp
      },
      body
    });

    await expect(verifyDiscordRequest(request, bytesToHex(keyPair.publicKey))).resolves.toBe(true);
  });

  it("rejects invalid signatures", async () => {
    const keyPair = nacl.sign.keyPair();
    const request = new Request("https://example.com", {
      method: "POST",
      headers: {
        "x-signature-ed25519": "00".repeat(64),
        "x-signature-timestamp": "1790000000"
      },
      body: JSON.stringify({ type: 1 })
    });

    await expect(verifyDiscordRequest(request, bytesToHex(keyPair.publicKey))).resolves.toBe(false);
  });
});

