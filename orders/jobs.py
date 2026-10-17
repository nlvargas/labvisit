import json
import threading

from django.conf import settings
from django.db import close_old_connections


def _run(func, args):
    try:
        func(*args)
    finally:
        close_old_connections()


def enqueue(func, *args):
    """Runs func(*args) in the background. Arguments must be JSON-serializable, because the zappa backend sends them
    to another Lambda invocation; checking it for every backend keeps local runs honest."""
    json.dumps(args)
    backend = settings.JOBS_BACKEND
    if backend == "thread":
        threading.Thread(target=_run, args=(func, args), daemon=True).start()
    elif backend == "zappa":
        from zappa.asynchronous import run

        run(func, args=args)
    else:
        func(*args)
