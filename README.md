# GovScheme Assistant — WhatsApp Chatbot for Government Schemes

A **WhatsApp chatbot** that helps Indian citizens discover, understand, compare, and check eligibility for **4,000+ government schemes** from [myscheme.gov.in](https://www.myscheme.gov.in).

Built with **FastAPI**, **OpenWA**, **Chroma**, **LangGraph**, **LangChain**, and **OpenAI**.

---

## Features

- Search schemes by need, state, category, or ministry
- Numbered results — reply `1`, `2`, `3` for full scheme details
- Eligibility checks against user profile (age, state, category, occupation)
- Side-by-side scheme comparison
- Application steps and documents required
- Instant status messages while search / LLM runs (`🔍 Searching…`, `📋 Loading details…`)
- Answers **grounded only in scraped data** — no invented scheme names, amounts, or URLs
- Per-user conversation memory (history, active scheme, last search list, profile)

---

## What Users Can Ask

| Area | Examples |
|------|----------|
| Education | *"scholarship for SC students in Karnataka"* |
| Agriculture | *"agricultural schemes in Gujarat"* |
| Business | *"loan for women entrepreneurs"* |
| Details | *"tell me about Stand-Up India"* |
| Eligibility | *"am I eligible? I am 22, SC, Karnataka"* |
| Compare | *"compare Stand-Up India vs MUDRA"* |
| Apply | *"how to apply for PM-KISAN?"* |
| Select | Reply `1` / `2` / `3` after a search list |

**Scheme categories covered:** Education, Agriculture, Business, Skills & Jobs, Women & Child, Social Welfare, Loans & Finance, Health & Housing.

---

## Architecture

```
WhatsApp message
      │
      ▼
OpenWA webhook  →  FastAPI handler  →  orchestrator.process()
      │
      ▼
LangGraph StateGraph (gov_graph)
      │
      ├── load          Load conversation from JSON
      ├── route         Router agent — intent + filters
      ├── retrieve      Chroma semantic search
      └── specialist    Eligibility / Compare / Search list / Detail / Select
      │
      ▼
finalize  →  save conversation  →  WhatsApp reply
```

### Why Multi-Agent RAG (not plain RAG)?

A single retrieve-and-answer pipeline cannot handle every WhatsApp interaction well. This project uses **specialist agents** coordinated by **LangGraph**:

| User intent | Agent | Why separate? |
|-------------|-------|---------------|
| Search | Response + Retrieval | Numbered list, saves slug order for `1/2/3` |
| Select `1` | Response + Retrieval | Loads exact scheme — never searches the digit `"1"` |
| Eligibility | Eligibility | Uses only eligibility chunks + user profile |
| Compare | Comparison | Side-by-side layout for 2–3 schemes |
| Detail / Apply | Response | Full answer or application steps |

Each agent has its own prompt, retrieval strategy, and LangGraph node.

### LangGraph flow

```
START → load → route
  ├─ welcome_first / welcome_back / help / feedback
  ├─ select → finalize
  └─ first_query → check_index → retrieve
         ├─ eligibility
         ├─ compare
         ├─ search_list
         ├─ detail_branch
         └─ default_branch → finalize → END
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI + Uvicorn |
| WhatsApp | OpenWA webhooks |
| Orchestration | **LangGraph** (`StateGraph`) |
| LLM | **LangChain** `ChatOpenAI` (gpt-4o-mini) |
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector DB | **Chroma** (persistent, `data/chroma/`) |
| Data | 4,112 schemes → 24,036 chunks |

---

## Project Structure

```
app/
├── main.py                     # FastAPI app + RAG startup
├── core/config.py              # Settings from .env
├── api/
│   ├── webhook.py              # POST /webhook (OpenWA events)
│   ├── whatsapp.py             # Send message, register webhook
│   └── health.py
├── whatsapp/
│   ├── handler.py              # Webhook → orchestrator → send reply
│   ├── client.py               # OpenWA HTTP client
│   ├── formatting.py           # Markdown → WhatsApp-friendly text
│   └── dedup.py                # Duplicate message guard
├── agents/                     # ★ LangGraph multi-agent system
│   ├── graph.py                # Wires nodes + edges, compiles gov_graph
│   ├── graph_state.py          # GovGraphState (shared state)
│   ├── graph_edges.py          # Conditional routing
│   ├── graph_utils.py          # split_reply, agent_context, helpers
│   ├── orchestrator.py         # Entry: orchestrator.process()
│   ├── router.py               # route() + route_node
│   ├── retrieval.py            # retrieve() + retrieve_node
│   ├── response.py             # search_list_node, select_node, detail_node
│   ├── eligibility.py          # eligibility_node
│   ├── comparison.py           # comparison_node
│   ├── llm.py                  # LangChain ChatOpenAI wrapper
│   ├── prompts.py              # System prompts, welcome, status messages
│   ├── scheme_list.py          # Ordered slug list for 1/2/3 selection
│   ├── types.py                # Intent, RouterResult, AgentContext
│   └── nodes/
│       ├── load.py             # load, check_index, finalize
│       └── static.py           # welcome, help, feedback
├── rag/                        # ★ RAG foundation
│   ├── chunker.py              # 6 sections per scheme
│   ├── embeddings.py           # OpenAI embeddings
│   ├── vector_store.py         # Chroma search
│   ├── filters.py              # State / category pre-filter
│   ├── indexer.py              # CLI: build index
│   └── models.py
├── knowledge/
│   └── scheme_loader.py        # Load 4000_data.csv
└── storage/
    └── conversations.py        # Per-user memory (JSON)

data/
├── chroma/                     # Vector index (auto-created)
└── conversations.json          # Chat history per user

web-scraping/
└── 4000_data.csv               # 4,112 schemes from myscheme.gov.in
```

---

## Data

| Stat | Value |
|------|-------|
| Schemes | 4,112 |
| Chunks (6 per scheme) | 24,036 |
| Source | [myscheme.gov.in](https://www.myscheme.gov.in) |

**Chunk sections:** description, benefits, eligibility, documents_required, application_process, faqs.

**Top categories:** Social Welfare (1,437), Education (1,096), Agriculture (843), Business (757), Women & Child (467), Skills (399).

---

## Setup & Run

### Prerequisites

- Python 3.9+
- OpenAI API key
- [OpenWA](https://github.com/open-wa) session running locally
- Scheme CSV at `web-scraping/4000_data.csv`

### 1. Clone and install

```bash
cd Whatsapp-Chatbot-Gov
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Create `.env` in the project root:

```env
# WhatsApp / OpenWA
OPENWA_BASE_URL=http://localhost:2785
WHATSAPP_HEADERS_X_API_KEY=your-openwa-api-key
SESSION_DETAILS_SESSION_ID=your-session-uuid
BOT_PHONE_NUMBER=your-bot-number
WEBHOOK_URL=http://127.0.0.1:8000/webhook

# OpenAI
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Chroma / RAG
CHROMA_PERSIST_PATH=data/chroma
RAG_TOP_K=8
BUILD_INDEX_IF_MISSING=true
REBUILD_INDEX_ON_STARTUP=false
```

### 3. Build the search index (one-time, ~5–10 min)

```bash
python3 -m app.rag.indexer --build
```

### 4. Start the server

```bash
python3 -m app.main
```

### 5. Register the webhook

```bash
curl -X POST http://127.0.0.1:8000/api/webhooks/register
```

Send a WhatsApp message to your bot number — you should get a reply.

---

## Example Conversations

```
User: hi
Bot:  Welcome message with scheme topics and examples

User: schemes about education
Bot:  ✅ Found 4 schemes — numbered list with links
      👆 Reply 1, 2, 3, 4 for full details

User: 1
Bot:  📋 Loading full details…
      Full scheme: benefits, eligibility, documents, how to apply

User: am I eligible? I am 22, SC, Karnataka
Bot:  ✅ Checking eligibility…
      Eligible / Possibly Eligible / Not Eligible + reasons

User: compare Stand-Up India vs MUDRA
Bot:  ⚖️ Comparing schemes…
      Side-by-side comparison
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENWA_BASE_URL` | `http://localhost:2785` | OpenWA server URL |
| `WHATSAPP_HEADERS_X_API_KEY` | — | OpenWA API key |
| `SESSION_DETAILS_SESSION_ID` | — | WhatsApp session UUID |
| `BOT_PHONE_NUMBER` | — | Bot phone (for filtering webhooks) |
| `WEBHOOK_URL` | `http://127.0.0.1:8000/webhook` | Where OpenWA sends events |
| `OPENAI_API_KEY` | — | Required for LLM + embeddings |
| `OPENAI_MODEL` | `gpt-4o-mini` | Chat model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `CHROMA_PERSIST_PATH` | `data/chroma` | Chroma storage path |
| `RAG_TOP_K` | `8` | Chunks retrieved per query |
| `BUILD_INDEX_IF_MISSING` | `true` | Auto-build index on startup |
| `REBUILD_INDEX_ON_STARTUP` | `false` | Force rebuild every start |

---

## Which File to Edit

| I want to… | File |
|------------|------|
| Change welcome / help / status text | `app/agents/prompts.py` |
| Change intent detection | `app/agents/router.py` |
| Add or reorder graph nodes | `app/agents/graph.py` + `graph_edges.py` |
| Change search / Chroma behaviour | `app/rag/vector_store.py` |
| Change chunking | `app/rag/chunker.py` |
| Change eligibility logic | `app/agents/eligibility.py` |
| Change WhatsApp formatting | `app/whatsapp/formatting.py` |
| Update scheme data | Replace CSV → `python3 -m app.rag.indexer --build` |
| Debug a user conversation | `data/conversations.json` |

---

## Visualize the LangGraph

```python
from app.agents.graph import gov_graph
print(gov_graph.get_graph().draw_mermaid())
```

Paste the output into [mermaid.live](https://mermaid.live) to view the graph.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook` | OpenWA incoming events |
| `POST` | `/api/webhooks/register` | Register webhook with OpenWA |
| `POST` | `/api/whatsapp/send-text` | Send a test message |
| `GET` | `/api/health` | Health check |

---

## License

This project is for educational and civic-tech purposes. Scheme data belongs to the Government of India via [myscheme.gov.in](https://www.myscheme.gov.in). Verify all eligibility and benefit information on official websites before applying.
