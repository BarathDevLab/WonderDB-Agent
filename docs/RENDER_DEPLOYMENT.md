# 🚀 Deploying AI Database Agent on Render

This guide walks you through deploying the complete **AI Database Agent** stack (FastAPI Backend, React Frontend, PostgreSQL with `pgvector`, and Redis) to [Render](https://render.com).

---

## 📑 Deployment Methods

You can deploy to Render using two methods:
1. **Method 1: One-Click Blueprint Deployment (Recommended)** – Uses [`render.yaml`](../render.yaml) to automatically provision and connect all 4 services.
2. **Method 2: Manual Dashboard Setup** – Step-by-step setup via the Render Web Dashboard.

---

## ⚡ Method 1: Blueprint Deployment (Fastest)

1. **Push your code to GitHub / GitLab**.
2. Log in to [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** $\rightarrow$ **Blueprint**.
4. Connect your GitHub repository containing this project.
5. Render will automatically detect [`render.yaml`](../render.yaml) and display 4 services to create:
   - **PostgreSQL Database** (`ai-agent-postgres`)
   - **Redis Instance** (`ai-agent-redis`)
   - **FastAPI Web Service** (`ai-agent-backend`)
   - **React Static Site** (`ai-agent-frontend`)
6. When prompted for environment variables, enter your **`GEMINI_API_KEY`**.
7. Click **Apply**. Render will automatically provision databases, install dependencies, run migrations, and deploy both frontend and backend services!

---

## 🛠️ Method 2: Manual Step-by-Step Setup

If you prefer provisioning services manually via the Render UI:

### Step 1: Create Managed PostgreSQL Database
1. Go to **New +** $\rightarrow$ **PostgreSQL**.
2. Name: `ai-agent-postgres`
3. Database Name: `enterprise_db`
4. User: `postgres`
5. Select Region and Plan (Free tier supported).
6. Click **Create Database**.
7. Once created, copy the **Internal Database URL** and credentials.
8. Enable `pgvector`: In Render PostgreSQL Shell or psql, run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

### Step 2: Create Managed Redis Cache
1. Go to **New +** $\rightarrow$ **Redis**.
2. Name: `ai-agent-redis`
3. Select Region and Plan.
4. Click **Create Redis**.
5. Copy the **Internal Redis URL** (`redis://...`).

### Step 3: Deploy FastAPI Backend Web Service
1. Go to **New +** $\rightarrow$ **Web Service**.
2. Connect your repository.
3. Settings:
   - **Name**: `ai-agent-backend`
   - **Environment**: `Python 3` (or `Docker`)
   - **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command**: `python scripts/init_and_seed_db.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir src`
4. Add **Environment Variables**:
   - `POSTGRES_HOST`: *(From PostgreSQL Host)*
   - `POSTGRES_PORT`: `5432`
   - `POSTGRES_USER`: `postgres`
   - `POSTGRES_PASSWORD`: *(From PostgreSQL Password)*
   - `POSTGRES_DB`: `enterprise_db`
   - `REDIS_URL`: *(From Redis Internal URL)*
   - `GEMINI_API_KEY`: `<Your-Google-Gemini-API-Key>`
   - `GEMINI_MODEL`: `gemini-1.5-flash`
   - `GEMINI_EMBEDDING_MODEL`: `text-embedding-004`
   - `ENABLE_SEMANTIC_CACHE`: `true`
5. Click **Create Web Service**.

### Step 4: Deploy React Frontend Static Site
1. Go to **New +** $\rightarrow$ **Static Site**.
2. Connect your repository.
3. Settings:
   - **Name**: `ai-agent-frontend`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm install && npm run build`
   - **Publish Directory**: `dist`
4. Set Redirects/Rewrites rule for single-page app (SPA):
   - **Source**: `/*`
   - **Destination**: `/index.html`
   - **Action**: `Rewrite`
5. Click **Create Static Site**.

---

## 🔍 Verification & Post-Deployment

1. Check backend health endpoint: `https://<your-backend-name>.onrender.com/health`
2. Open frontend URL: `https://<your-frontend-name>.onrender.com`
3. Submit a test query like: `"Show sales volume by category"` to test end-to-end SSE streaming and database access.
