import type { LocalContentConfig } from "./local_content_rag_types.js";

export type EmbeddingFetch = typeof fetch;

export class EmbeddingProvider {
    private provider: "ollama" | "openai";
    private ollamaUrl: string;
    private ollamaModel: string;
    private openaiApiKey?: string;
    private fetchImpl: EmbeddingFetch;

    constructor(config: Partial<LocalContentConfig>, fetchImpl: EmbeddingFetch = fetch) {
        this.provider = config.embeddingProvider || "ollama";
        this.ollamaUrl = config.ollamaUrl || "http://localhost:11434";
        this.ollamaModel = config.ollamaModel || "nomic-embed-text";
        this.openaiApiKey = config.openaiApiKey;
        this.fetchImpl = fetchImpl;
    }

    async generateEmbedding(text: string): Promise<number[]> {
        if (this.provider === "openai") {
            return this.embedOpenAI(text);
        }
        return this.embedOllama(text);
    }

    private async embedOllama(text: string): Promise<number[]> {
        const response = await this.fetchImpl(`${this.ollamaUrl}/api/embeddings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                model: this.ollamaModel,
                prompt: text.substring(0, 8000),
            }),
        });

        if (!response.ok) {
            throw new Error(`Ollama embedding failed: ${response.statusText}`);
        }

        const data = await response.json() as { embedding: number[] };
        return data.embedding;
    }

    private async embedOpenAI(text: string): Promise<number[]> {
        if (!this.openaiApiKey) {
            throw new Error("OpenAI API key not configured");
        }

        const response = await this.fetchImpl("https://api.openai.com/v1/embeddings", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${this.openaiApiKey}`,
            },
            body: JSON.stringify({
                model: "text-embedding-3-small",
                input: text.substring(0, 8000),
            }),
        });

        if (!response.ok) {
            throw new Error(`OpenAI embedding failed: ${response.statusText}`);
        }

        const data = await response.json() as { data: Array<{ embedding: number[] }> };
        return data.data[0].embedding;
    }
}
