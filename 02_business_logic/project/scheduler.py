"""Run in a second terminal to bill automatically every 60 seconds."""
import time
from app import create_app
from brightloop.billing import run_billing

app = create_app()
print('Billing scheduler started. Press Ctrl+C to stop.', flush=True)
try:
    while True:
        with app.app_context():
            try:
                count = run_billing()
                print(f'Billing check: {count} invoices created.', flush=True)
            except Exception:
                app.logger.exception('Billing failed; the transaction was rolled back. The next run will retry.')
        time.sleep(60)
except KeyboardInterrupt:
    print('Scheduler stopped.')
