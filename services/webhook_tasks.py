import threading
from queue import Queue, Full


_TASK_QUEUE = Queue(maxsize=100)
_START_LOCK = threading.Lock()
_WORKER_STARTED = False


def _webhook_worker(app):
    while True:
        task = _TASK_QUEUE.get()
        try:
            with app.app_context():
                task()
        except Exception as exc:
            print(f"Webhook background task failed: {exc}")
        finally:
            _TASK_QUEUE.task_done()


def start_webhook_worker(app):
    global _WORKER_STARTED
    with _START_LOCK:
        if _WORKER_STARTED:
            return
        worker = threading.Thread(
            target=_webhook_worker,
            args=(app,),
            daemon=True,
            name="webhook-task-worker",
        )
        worker.start()
        _WORKER_STARTED = True


def enqueue_webhook_task(task):
    try:
        _TASK_QUEUE.put_nowait(task)
        return True
    except Full:
        print("Webhook background queue full; dropping non-critical task.")
        return False


def write_paystack_log(raw_body, signature_verified, outcome):
    from models import db, PaystackWebhookLog

    db.session.add(PaystackWebhookLog(
        raw_body=raw_body,
        signature_verified=signature_verified,
        outcome=outcome,
    ))
    db.session.commit()