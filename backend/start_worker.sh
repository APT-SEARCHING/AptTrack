#!/bin/sh
exec celery -A app.worker worker --loglevel=INFO --concurrency 2
