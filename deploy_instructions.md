# Deploy instructions (Cloud Run example)

1. Build docker image locally:
   docker build -t gcr.io/<YOUR_PROJECT_ID>/llm-quiz-solver:latest .

2. Push:
   docker push gcr.io/<YOUR_PROJECT_ID>/llm-quiz-solver:latest

3. Deploy to Cloud Run:
   gcloud run deploy llm-quiz-solver \
      --image gcr.io/<YOUR_PROJECT_ID>/llm-quiz-solver:latest \
      --platform managed --region us-central1 \
      --allow-unauthenticated \
      --set-env-vars STUDENT_EMAIL=youremail@...,STUDENT_SECRET=your_secret,MAX_PROCESS_SECONDS=180

Alternate: Render / Fly / Railway; set env vars STUDENT_EMAIL, STUDENT_SECRET.

Important: ensure outbound network allowed and that Playwright browsers are available. Cloud Run standard should work with the Docker image.
