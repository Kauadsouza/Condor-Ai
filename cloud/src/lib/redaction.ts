const SECRET_PATTERNS = [
  /\bsk-[A-Za-z0-9_-]{20,}\b/g,
  /\b(?:Bearer\s+)[A-Za-z0-9._~+/=-]{20,}/gi,
  /\b(?:api[_ -]?key|token|senha|password|secret)\s*[:=]\s*[^\s,;]{6,}/gi,
  /\b[A-Za-z0-9+/]{40,}={0,2}\b/g,
];

export function redactSecrets(input: string): { text: string; blocked: boolean } {
  let text = String(input || "").trim();
  let blocked = false;
  for (const pattern of SECRET_PATTERNS) {
    text = text.replace(pattern, () => {
      blocked = true;
      return "[SEGREDO OMITIDO]";
    });
  }
  return { text: text.slice(0, 8000), blocked };
}
