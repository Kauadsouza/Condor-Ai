import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import { serverEnv } from "@/lib/env";

const VERSION = "v1";

function key(): Buffer {
  const raw = Buffer.from(serverEnv().CONDOR_CLOUD_ENCRYPTION_KEY, "base64");
  if (raw.length !== 32) throw new Error("CONDOR_CLOUD_ENCRYPTION_KEY precisa conter exatamente 32 bytes em base64.");
  return raw;
}

export function seal(value: string): string {
  const nonce = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key(), nonce);
  const encrypted = Buffer.concat([cipher.update(value, "utf8"), cipher.final()]);
  return [VERSION, nonce.toString("base64url"), cipher.getAuthTag().toString("base64url"), encrypted.toString("base64url")].join(".");
}

export function unseal(value: string): string {
  const [version, nonceRaw, tagRaw, encryptedRaw] = String(value || "").split(".");
  if (version !== VERSION || !nonceRaw || !tagRaw || !encryptedRaw) throw new Error("conteudo cifrado invalido");
  const decipher = createDecipheriv("aes-256-gcm", key(), Buffer.from(nonceRaw, "base64url"));
  decipher.setAuthTag(Buffer.from(tagRaw, "base64url"));
  return Buffer.concat([decipher.update(Buffer.from(encryptedRaw, "base64url")), decipher.final()]).toString("utf8");
}

export function sealJson(value: unknown): string {
  return seal(JSON.stringify(value));
}

export function unsealJson<T>(value: string): T {
  return JSON.parse(unseal(value)) as T;
}
