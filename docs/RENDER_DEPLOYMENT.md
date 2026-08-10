# 🚀 Deploying FastAPI Backend on Render Free Tier

This guide walks you through deploying **only the FastAPI Backend** service of the **AI Database Agent** on **Render's Free Tier**.

---

## ⚡ Quick Blueprint Deployment (Backend Only)

The project includes a streamlined [`render.yaml`](../render.yaml) configured specifically for the backend service.

### Step-by-Step Blueprint Instructions:

1. **Push your repository to GitHub / GitLab**.
2. Log in to your [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** $\rightarrow$ **Blueprint**.
4. Select your repository.
5. Render will automatically detect [`render.yaml`](../render.yaml) and configure the `ai-agent-backend` Web Service.
6. Enter your environment variables when prompted:
   - `DATABASE_URL`: Your PostgreSQL connection string (e.g. from Render PostgreSQL, Neon.tech, or Supabase).
   - `REDIS_URL`: Your Redis connection string (e.g. from Upstash Redis or Render Redis).
   - `GEMINI_API_KEY`: Your Google Gemini API Key.
7. Click **Apply**. Render will install dependencies, initialize database tables (`python scripts/init_and_seed_db.py`), and deploy your FastAPI app on the Free Web Service tier!

---

## 🛠️ Manual Web Service Deployment (Render Dashboard)

If you prefer creating the Web Service manually via Render UI:

1. Go to [Render Dashboard](https://dashboard.render.com/) $\rightarrow$ Click **New +** $\rightarrow$ **Web Service**.
2. Connect your Git repository.
3. Configure the following settings:
   - **Name**: `ai-agent-backend`
   - **Language / Environment**: `Python 3`
   - **Region**: Select nearest region (e.g., `Singapore`, `Oregon`, `Frankfurt`)
   - **Branch**: `main`
   - **Build Command**: 
     ```bash
     pip install --upgrade pip && pip install -r requirements.txt
     ```
   - **Start Command**: 
     ```bash
     python scripts/init_and_seed_db.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir src
     ```
   - **Instance Type**: **Free**

4. **Environment Variables**:
   Under **Environment Variables**, click **Add Environment Variable** for each:

   | Variable Name | Example Value / Description |
   | :--- | :--- |
   | `PYTHON_VERSION` | `3.11.8` |
   | `DATABASE_URL` | `postgresql://user:pass@ep-xyz.neon.tech/enterprise_db?sslmode=require` |
   | `REDIS_URL` | `rediss://default:password@xyz.upstash.io:6379` |
   | `GEMINI_API_KEY` | `AIzaSy...` *(Your Gemini API Key)* |
   | `GEMINI_MODEL` | `gemini-1.5-flash` |
   | `GEMINI_EMBEDDING_MODEL` | `text-embedding-004` |
   | `ENABLE_SEMANTIC_CACHE` | `true` |

5. Click **Create Web Service**.

---

## 💡 Free Tier Tips & Best Practices

1. **Cold Starts**: Render's free web services automatically spin down after 15 minutes of inactivity. The first request after spin-down takes ~30-50 seconds to warm up.
2. **PostgreSQL & Redis Connections**: You can use free hosted databases like [Neon.tech](https://neon.tech) / [Supabase](https://supabase.com) for PostgreSQL (with `pgvector`), and [Upstash Redis](https://upstash.com) for Redis caching.
3. **Health Check Verification**: Once deployed, verify your service by navigating to `https://<your-render-app-name>.onrender.com/health`.
