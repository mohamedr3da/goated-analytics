export function compactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "Unavailable";
  }
  const absolute = Math.abs(value);
  for (const [suffix, divisor] of [
    ["B", 1_000_000_000],
    ["M", 1_000_000],
    ["K", 1_000]
  ] as const) {
    if (absolute >= divisor) {
      return `${(value / divisor).toFixed(2).replace(/\.?0+$/, "")}${suffix}`;
    }
  }
  return value.toLocaleString("en-US");
}

export function safePreview(text: string, limit = 120): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) {
    return normalized;
  }
  return `${normalized.slice(0, limit - 3)}...`;
}

