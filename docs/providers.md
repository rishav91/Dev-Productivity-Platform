# Provider Configuration

LLM and embedding providers are configured via environment variables. Switching providers requires no code changes.

## LLM providers

Set `LLM_PROVIDER` (default: `anthropic`):

| `LLM_PROVIDER` | Default model | Notes |
|---|---|---|
| `anthropic` | `claude-sonnet-4-20250514` | Best reasoning; required for evals |
| `openai` | `gpt-4o-mini` | ~20× cheaper for high-volume runs |
| `groq` | `llama-3.3-70b-versatile` | Free tier, rate-limited; good for local dev |
| `ollama` | `llama3.2` | Fully local; needs Ollama running |

Override the model directly: `LLM_MODEL=claude-opus-4-7`.

### Tool use compatibility

The `synthesize_and_gate` node requires the model to call a tool with a specific schema. Not all open-source models reliably honor `tool_choice`. If you see `RuntimeError: Model did not call tool`, fall back to `anthropic` or `openai`.

---

## Embedding providers

Set `EMBED_PROVIDER` (default: `openai`):

| `EMBED_PROVIDER` | Default model | Dimensions | Notes |
|---|---|---|---|
| `openai` | `text-embedding-3-small` | 1536 | Recommended default |
| `ollama` | `nomic-embed-text` | 768 | Free local |
| `local` | `all-MiniLM-L6-v2` | 384 | No API key; `pip install sentence-transformers` |

**Important:** Switching `EMBED_PROVIDER` changes the vector dimension and requires re-seeding the database:

```bash
python fixtures/seed_db.py
```

---

## Recommended configurations

**Cheap eval runs (no API cost):**
```env
LLM_PROVIDER=groq
EMBED_PROVIDER=local
```

**Local-only (fully offline):**
```env
LLM_PROVIDER=ollama
EMBED_PROVIDER=ollama
```

**Production / eval baseline:**
```env
LLM_PROVIDER=anthropic
EMBED_PROVIDER=openai
```
