/** Random UUID v4 as 32 lowercase hex characters, the core's request-key format. */
export function newKey(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

export const KEY_PATTERN = /^[a-f0-9]{32}$/;
