# main.py
import os
import time
import json
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from solver import QuizSolver

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("quiz-server")

app = FastAPI()

# Configuration: set these as environment variables in your deployment
STUDENT_EMAIL = os.getenv("STUDENT_EMAIL", "youremail@example.edu")
STUDENT_SECRET = os.getenv("STUDENT_SECRET", "s3cr3t-QuizKey-2025")
MAX_PROCESS_SECONDS = int(os.getenv("MAX_PROCESS_SECONDS", "180"))

# Background solver instance
solver = QuizSolver(
    email=STUDENT_EMAIL,
    secret=STUDENT_SECRET,
    max_seconds=MAX_PROCESS_SECONDS
)

class IncomingPayload(BaseModel):
    email: str
    secret: str
    url: str
    # may contain other fields; allow flexible handling

@app.post("/api/quiz")
async def quiz_endpoint(request: Request):
    # Validate JSON
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    email = body.get("email")
    secret = body.get("secret")
    url = body.get("url")

    if not (email and secret and url):
        return JSONResponse({"error": "Missing required fields: email, secret, url"}, status_code=400)

    if secret != STUDENT_SECRET:
        return JSONResponse({"error": "Invalid secret"}, status_code=403)

    # Accepted: spawn background task to solve
    logger.info(f"Accepted quiz request for {email} -> {url}")
    # Fire-and-forget, but solver enforces max time (do not rely on serverless timeouts)
    asyncio.create_task(solver.process_quiz_url(url, body))
    return JSONResponse({"status": "accepted"}, status_code=200)

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}
