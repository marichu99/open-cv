#!/bin/sh
set -e

if [ "$SERVICE_ROLE" = "api" ]; then
  exec gunicorn -w "${WEB_CONCURRENCY:-4}" --bind 0.0.0.0:8080 wsgi:app
else
  exec gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:8080 wsgi:app
fi
