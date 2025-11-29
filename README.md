# llm-quiz-solver

FastAPI + Playwright service to solve timed data quizzes (IITM assignment).

## Features
- Validates incoming POST with secret
- Renders JS pages with Playwright
- Downloads & parses CSV/XLSX/PDF (basic heuristics)
- Posts answers to discovered submit endpoints
- Follows next-URL sequences while keeping within 3-minute window

## Setup (local)
1. Clone repo
2. Create virtual env and activate
3. pip install -r requirements.txt
4. python -m playwright install
5. Set environment variables:
   - STUDENT_EMAIL
   - STUDENT_SECRET
   - (optional) MAX_PROCESS_SECONDS
6. Run:
   uvicorn main:app --reload --port 5000

## Test with demo payload
Use the provided demo endpoint by the instructors:




## Deployment
See `deploy_instructions.md` for Cloud Run. You can also deploy to Render/Fly/Railway. Make sure to set env vars and allow sufficient CPU/memory for Playwright.

## Security
- Do not commit your `STUDENT_SECRET` or any secrets.
- Store secrets in environment variables or your platform's secret store.
