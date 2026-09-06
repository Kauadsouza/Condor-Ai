import { createHash } from "node:crypto";
import OpenAI from "openai";
import { z } from "zod";
import { authFailure, requireCloudUser } from "@/lib/auth";
import {
  appendSyncEvent, createNote, ensureConversation, extractNoteIntent,
  insertMessage, listMessages, memoryContext,
} from "@/lib/cloud-data";
import { cloudInstructions, CONDOR_MIND_ID } from "@/lib/identity";
import { redactSecrets } from "@/lib/redaction";
import { serverEnv } from "@/lib/env";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

const requestSchema = z.object({
  message: z.string().trim().min(1).max(8000),
  conversationId: z.string().uuid().optional(),
  clientMessageId: z.string().min(8).max(160),
  deviceKey: z.string().min(4).max(160).default("cloud-web"),
});

function sse(controller: ReadableStreamDefaultController<Uint8Array>, event: string, data: unknown) {
  controller.enqueue(new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
}

export async function POST(request: Request) {
  let auth;
  try { auth = await requireCloudUser(request); }
  catch (error) { return authFailure(error) || new Response("nao autenticado", { status: 401 }); }

  const parsed = requestSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return Response.json({ error: "mensagem invalida" }, { status: 400 });

  const { user, supabase } = auth;
  const redacted = redactSecrets(parsed.data.message);
  const conversationId = await ensureConversation(supabase, user.id, parsed.data.conversationId, redacted.text);
  const userMessage = await insertMessage(supabase, user.id, conversationId, "user", redacted.text, parsed.data.clientMessageId);
  await appendSyncEvent(
    supabase, user.id, `message-${userMessage.id}`, parsed.data.deviceKey, "message",
    { id: userMessage.id, conversationId, role: "user", content: redacted.text, createdAt: userMessage.createdAt },
  );

  const noteIntent = extractNoteIntent(redacted.text);
  let noteCreated: { id: string; title: string; body: string; createdAt: string; updatedAt: string } | null = null;
  if (noteIntent) {
    noteCreated = await createNote(supabase, user.id, noteIntent.title, noteIntent.body, userMessage.id);
    await appendSyncEvent(supabase, user.id, `note-${noteCreated.id}`, parsed.data.deviceKey, "note", noteCreated);
  }

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        sse(controller, "meta", { mindId: CONDOR_MIND_ID, conversationId, userMessageId: userMessage.id, note: noteCreated });
        if (redacted.blocked) {
          const fixed = "Detectei uma credencial ou segredo e removi esse trecho antes de salvar ou enviar. Se precisar configurar uma chave, use o painel seguro do Condor.";
          const saved = await insertMessage(supabase, user.id, conversationId, "assistant", fixed);
          await appendSyncEvent(supabase, user.id, `message-${saved.id}`, "condor-cloud", "message", { id: saved.id, conversationId, role: "assistant", content: fixed, createdAt: saved.createdAt });
          sse(controller, "delta", { text: fixed });
          sse(controller, "done", { mindId: CONDOR_MIND_ID, messageId: saved.id });
          controller.close();
          return;
        }

        const [history, context] = await Promise.all([
          listMessages(supabase, user.id, conversationId, 30),
          memoryContext(supabase, user.id),
        ]);
        const env = serverEnv();
        const openai = new OpenAI({ apiKey: env.OPENAI_API_KEY });
        const response = await openai.responses.create({
          model: env.OPENAI_MODEL,
          instructions: cloudInstructions(context),
          input: history.map((item) => ({ role: item.role, content: item.content })),
          max_output_tokens: 1800,
          reasoning: { effort: "medium" },
          text: { verbosity: "medium" },
          store: false,
          stream: true,
          safety_identifier: createHash("sha256").update(`condor:${user.id}`).digest("hex").slice(0, 32),
        });

        let answer = "";
        for await (const event of response) {
          if (event.type === "response.output_text.delta") {
            answer += event.delta;
            sse(controller, "delta", { text: event.delta });
          }
          if (event.type === "response.failed") throw new Error(event.response.error?.message || "resposta falhou");
        }
        answer = answer.trim() || "Nao consegui concluir a resposta agora.";
        const saved = await insertMessage(supabase, user.id, conversationId, "assistant", answer);
        await appendSyncEvent(supabase, user.id, `message-${saved.id}`, "condor-cloud", "message", {
          id: saved.id, conversationId, role: "assistant", content: answer, createdAt: saved.createdAt,
        });
        sse(controller, "done", { mindId: CONDOR_MIND_ID, messageId: saved.id, conversationId });
        controller.close();
      } catch (error) {
        sse(controller, "error", { message: error instanceof Error ? error.message : "falha inesperada" });
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-store, must-revalidate",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
