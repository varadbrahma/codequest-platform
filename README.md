# CodeQuest platform — backend foundation

This folder starts the transition from the standalone HTML prototype to a frontend backed by an API.

## Current stage

- FastAPI service with liveness and readiness endpoints.
- Explicit local CORS allowlist and frontend API indicator.
- Supabase Google OAuth client wiring, server-side Supabase session verification, and profile/preference API routes.
- Profile and learning-preference migrations with row-level policies that restrict reads/writes to `auth.uid()`.
- Cursed Lab story campaign, local relics and debugging challenges.
- Public GitHub repository browsing with rule-based file explanations, repository summaries, heuristic issue scans, generated quizzes, and sandboxed HTML previews.
- Global top-50 leaderboard with pseudonymous display names and scores from server-verified mission submissions only.
- AI Code Mentor chat for programming and general questions, using a configured server-side OpenAI-compatible API key.
- Playground language selection for Python, JavaScript, TypeScript, Java, and C++. Python uses the authenticated server-side runner; Java and C++ use the same Judge0-compatible isolated runner for the sum mission. JavaScript and TypeScript checks run locally in the browser (not a security boundary).
- Google OAuth and email/password sign-in/sign-up UI using Supabase Auth. Actual sign-in requires a configured Supabase project and enabled auth providers; account profile sync also requires the hosted API.
- Guild Hall practice features include local clubs, solo timed mission duels, daily quests, practice badges, and quiz-style boss battles. Progress is browser-local; live teams, matchmaking, and verified awards require a hosted multiplayer service and are not simulated.
- The Cursed Lab includes an eight-chapter narrative campaign and a locally saved field journal. Story answers and practice rewards are not server-verified credentials.
- No Supabase project is configured by default. Authentication and database access stay unavailable until you configure the project and apply the migrations.
- A Judge0-compatible isolated runner adapter is included, but it is unavailable until you configure its server-side URL/key. Browser-based JavaScript and TypeScript runners are not hardened security sandboxes.

Repository analysis is static and heuristic: it uses the repository description/README/manifest and traces recognizable imports from loaded entry files to available local files. It is not a full code review or proof of safety. The optional GitHub token is used by the browser only for GitHub API rate limits; only import public repositories and avoid pasting a token on shared devices. HTML previews run in a sandboxed iframe and may not reproduce all project behavior. The built-in task tracker can be opened as an editable StackBlitz project; imported public GitHub repositories open using StackBlitz's GitHub import route.

## Run locally on Windows

Open PowerShell in this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --app-dir backend --reload --env-file .env --host 127.0.0.1 --port 8001
```

Serve the frontend from another PowerShell window in this folder:

```powershell
py -m http.server 8000 --directory frontend
```

Open `http://localhost:8000`. The API health check is available at `http://localhost:8001/health/ready`; interactive API documentation is at `http://localhost:8001/docs`.

## Deploy to Vercel

This repository is a monorepo with two separate Vercel projects. Import the same GitHub repository for each project, and set each project's **Root Directory** to its application folder:

| Vercel project | Root Directory | Framework / build |
| --- | --- | --- |
| Frontend | `frontend` | Other; no build or install command required. Vercel serves `index.html` and `config.js` as static files. |
| API | `backend` | FastAPI; keep the detected Python build settings. The ASGI application is `app/main.py`, with dependencies in `requirements.txt`. |

Do not deploy the repository root as a third project: it contains neither app's runtime root. The FastAPI backend needs its own deployment and environment variables. Set `CODEQUEST_API_BASE` in `frontend/config.js` to the API deployment URL, and configure `CODEQUEST_CORS_ORIGINS` on the API to include the exact frontend production origin. Supabase authentication and isolated Java/C++ execution additionally require their project and runner settings.

The CORS setting must list exact frontend origins. Do not set it to `*`. The sample `.env` is development configuration, not production secrets. Start Uvicorn with `--env-file .env` so it loads the file.

## Configure Supabase, Google sign-in, and email/password accounts

1. Create a Supabase project. In `frontend/config.js`, set `CODEQUEST_SUPABASE_URL` and `CODEQUEST_SUPABASE_PUBLISHABLE_KEY` from the project API settings. If the API is hosted elsewhere, set `CODEQUEST_API_BASE` to its URL.
2. Set the same project URL and publishable key in `.env` as `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. Never use a service-role key in the frontend or this API.
3. Apply `supabase/migrations/001_profiles.sql` and `supabase/migrations/002_global_leaderboard.sql` in the Supabase SQL editor.
4. Create a Google OAuth client. Configure its authorized redirect URI as `https://<project-ref>.supabase.co/auth/v1/callback`, then enter the Google client ID and secret only in Supabase Authentication provider settings. Add the local frontend URL (for example `http://localhost:8000/`) to Supabase's allowed redirect URLs.
5. Restart the API with `uvicorn app.main:app --app-dir backend --reload --env-file .env --host 127.0.0.1 --port 8001`.
6. In Supabase Authentication, enable Google and configure its Google OAuth client ID and secret. Enable email/password sign-in and decide whether email confirmation is required.
7. Add the deployed website origin and the local frontend URL to Supabase's allowed redirect URLs. Set `CODEQUEST_API_BASE` in `frontend/config.js` to the deployed API URL for persistent account profiles and learning preferences. Keep CORS restricted to the exact deployed frontend origin.
8. Open the frontend and choose **Sign in / sign up** for Google OAuth, email/password login, or account creation. Supabase validates authentication; a matching configured CodeQuest API is additionally required for server-backed profiles/preferences, the AI Mentor, isolated mission execution, and leaderboard access. Users who need email confirmation must confirm before their first password login.

Do not paste OAuth client secrets or Supabase service-role keys into chat or frontend files. Keep provider secrets in Supabase's configuration and backend secrets in an environment/secret manager. The service-role key is required for leaderboard writes and must only be configured on the backend.

## Configure the AI Code Mentor

Set `OPENAI_API_KEY` in the backend environment and optionally set `OPENAI_MODEL` (default: `gpt-4o-mini`). The key is used only by the FastAPI service and must never be placed in frontend configuration. The mentor endpoint requires a verified Supabase sign-in and answers general as well as programming questions. The UI can optionally include the current playground code; submitted conversation text is sent to the configured AI provider and is not stored by this app. Configure provider billing and usage controls before public deployment.

## Isolated mission runner

The authenticated mission endpoint dispatches Python, Java, and C++ code to a server-configured Judge0-compatible runner. Configure the runner only in the backend environment; never place its URL credentials or API key in `frontend/config.js`.

```dotenv
RUNNER_API_URL=https://your-private-judge0.example
RUNNER_API_KEY=your-server-side-runner-key
RUNNER_PYTHON_LANGUAGE_ID=71
RUNNER_JAVA_LANGUAGE_ID=62
RUNNER_CPP_LANGUAGE_ID=54
```

The selected runner must support these Judge0 language IDs (or configure the IDs for your provider) and honor bounded CPU, wall-clock, memory, process, and network-disabled execution settings. The API currently provides automated Java and C++ checks for the sum-of-two-numbers mission: either define `add_numbers(a, b)` in a class/global scope using the editor's starter signature, or provide a `main` program that reads two numbers from standard input and prints their sum. For Java function solutions, keep the solution class package-private and named something other than `Main` (the starter uses `Solution`); the API generates the `Main` entry point. Java programs with their own `main` method must use the Judge0-compatible `Main` class/file convention. Other missions in Java/C++ return an explicit unsupported-language/mission response. Python continues to run the existing mission harness server-side; JavaScript and TypeScript continue to run in the browser and are not hardened security sandboxes.

The public frontend also needs a hosted API URL, Supabase project configuration, and a signed-in user before server-side submissions can run. Leaderboard reads additionally require migration `002_global_leaderboard.sql`; verified completion writes require `SUPABASE_SERVICE_ROLE_KEY` on the backend. The board exposes display names and XP only, not email addresses. JavaScript/TypeScript browser checks and local-only completions do not affect rankings. Without the deployment settings, the site explains why the service is unavailable rather than sending source code to an unconfigured third party. Do not send private code to public compilation services.

## Remaining stages

Move mission tests and XP to a separate, resource-limited execution service; then persist submissions and learning history with ownership policies. Add AI debugging, scheduler, monitoring, backups, and production deployment only after those foundations are tested.
