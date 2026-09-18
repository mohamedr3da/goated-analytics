export function periodStart(period: string, now = new Date()): Date {
  const normalized = period.toLowerCase();
  const days = normalized === "1d" || normalized === "24h" ? 1 : normalized === "7d" ? 7 : normalized === "30d" ? 30 : null;
  if (!days) {
    throw new Error("Supported periods are 1d, 7d, and 30d.");
  }
  return new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
}

