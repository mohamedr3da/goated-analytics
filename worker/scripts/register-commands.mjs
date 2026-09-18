const token = process.env.DISCORD_TOKEN ?? process.env.DISCORD_BOT_TOKEN;
const applicationId = process.env.DISCORD_APPLICATION_ID;

if (!token || !applicationId) {
  console.error("DISCORD_TOKEN/DISCORD_BOT_TOKEN and DISCORD_APPLICATION_ID are required.");
  process.exit(1);
}

const commands = [
  {
    name: "track",
    description: "Track an X/Twitter account.",
    options: [{ name: "username", description: "X username", type: 3, required: true }]
  },
  {
    name: "untrack",
    description: "Stop tracking an X/Twitter account.",
    options: [{ name: "username", description: "X username", type: 3, required: true }]
  },
  { name: "tracked", description: "List tracked accounts." },
  {
    name: "twitter",
    description: "Show a current X/Twitter account overview.",
    options: [{ name: "username", description: "X username", type: 3, required: true }]
  },
  {
    name: "analytics",
    description: "Show analytics for a tracked account.",
    options: [
      { name: "username", description: "X username", type: 3, required: true },
      {
        name: "period",
        description: "Analytics period",
        type: 3,
        required: true,
        choices: [
          { name: "1d", value: "1d" },
          { name: "7d", value: "7d" },
          { name: "30d", value: "30d" }
        ]
      }
    ]
  },
  { name: "status", description: "Show production bot status." },
  {
    name: "refresh",
    description: "Refresh one tracked account now.",
    options: [{ name: "username", description: "X username", type: 3, required: true }]
  },
  { name: "collectnow", description: "Run one collection cycle now." }
];

const response = await fetch(
  `https://discord.com/api/v10/applications/${applicationId}/commands`,
  {
    method: "PUT",
    headers: {
      authorization: `Bot ${token}`,
      "content-type": "application/json"
    },
    body: JSON.stringify(commands)
  }
);

console.log(`Discord command registration HTTP ${response.status}`);
if (!response.ok) {
  console.error(await response.text());
  process.exit(1);
}
