web: sh -c 'python -m uvicorn newton.main:app --host 0.0.0.0 --port ${PORT:-8080}'
# worker process is unused for now — the web service runs the streamer in-process
# (via newton.main lifespan). Re-enable when scaling out with a shared store.
# worker: python -m workers.streamer
