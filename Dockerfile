FROM python:3.13-slim

WORKDIR /app

# Local Agents SDK dependency (sibling folder in this repo)
COPY openai-agents-python ./openai-agents-python
RUN pip install --no-cache-dir ./openai-agents-python

# Backend app
COPY "Fact Cookie Backend/requirements.txt" ./backend/
RUN pip install --no-cache-dir -r ./backend/requirements.txt

COPY "Fact Cookie Backend" ./backend/
WORKDIR /app/backend

EXPOSE 7860

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
