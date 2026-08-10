# AI Database Agent 🚀 (Hackathon Project)

An enterprise-grade, multi-tenant **Text-to-SQL platform** built for modern database interactions. It safely translates natural language prompts into dialect-specific SQL, validates execution, executes queries against isolated read-only replicas, and streams live progress, dataset tables, and visualization specs to a responsive React frontend via Server-Sent Events (SSE).

## 💡 What it Does & Key Features

Our platform is separated into a "Brain vs. Hands" architecture using the **Model Context Protocol (MCP)**:
- **🧠 Orchestration Brain**: A LangGraph deterministic state machine that handles planning, reflecting, and summarizing.
- **🛠️ Execution Hands**: An MCP tool server that safely executes SQL with strict AST parsing, EXPLAIN cost gates, and dynamic schema retrieval.
- **⚡ Real-Time SSE Streaming**: Live updates for reasoning phases, tabular data grids, and declarative Chart.js configurations streamed directly to the frontend.
- **🔒 Enterprise Security**: Row-Level Security (RLS) multi-tenant isolation and strict cost gates for safe SQL execution.

## 🛠️ Technology Stack

**Backend:**
- **FastAPI**: API Gateway, Authentication, and SSE Streaming.
- **LangGraph**: Single-Agent orchestrator.
- **PostgreSQL & Redis**: Persistence layer, RLS isolation, and Semantic Vector Caching.
- **Model Context Protocol (MCP)**: For secure database interaction tooling.
- **Python 3.11+ & Poetry**: Dependency management and environment.

**Frontend:**
- **React 18 & Vite**: Lightning-fast, modern UI.
- **TypeScript**: Type-safe development.
- **Tailwind CSS & Lucide React**: Utility-first styling and beautiful icons.
- **Chart.js (`react-chartjs-2`)**: Dynamic visual data representations generated on the fly.

---

## ⚙️ Local Setup Instructions

### Prerequisites
- Python 3.11+ and [Poetry](https://python-poetry.org/)
- Node.js (v18+) and npm
- Docker & Docker Compose (for DB and cache)

### 1. Backend Setup

Open a terminal and navigate to the project root:
```bash
# Install Python dependencies
poetry install

# Configure environment variables (update credentials as needed)
cp .env.example .env

# Start local PostgreSQL and Redis infrastructure
docker-compose up -d

# Start the FastAPI development server
poetry run uvicorn main:app --reload
```
*(Note: The MCP server process runs in the background and is managed by the FastAPI client).*

### 2. Frontend Setup

Open a **new terminal window** and navigate to the `frontend` directory:
```bash
cd frontend

# Install Node dependencies
npm install

# Start the Vite development server (HMR enabled)
npm run dev
```
The frontend will be available at `http://localhost:5173/`. Ensure the backend is running simultaneously so the frontend can successfully connect to the SSE endpoint.

---

## 👥 Team Information

Developed and maintained by the **Engineering Team** during the hackathon.
For questions, support, or feedback, please contact: [dev@company.com](mailto:dev@company.com)
