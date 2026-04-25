#!/bin/sh
exec celery -A app.worker beat --loglevel=INFO
