# Verification results

Checked on 31 October 2026, using Python 3.13 on Windows.

## Automated checks

Command: `python -m pytest -q`

**61 tests passed in the final run (3.69 seconds).**

Coverage includes signup/password validation, unique email, hashed passwords, role/ownership boundaries, CSRF, login rate limits, one-use password reset and session invalidation, all main page templates, quotation transitions, expired quotations, plan restrictions, renewals, add-ons, calendar boundaries, variant prices, discount eligibility/limits, line tax rounding, zero-total invoices, partial payments, overpayments, payment replay, cancellation, duplicate/concurrent billing and transaction rollback.

## Repeatable local performance check

Command: `python tests/benchmark.py`

Dataset: **5,006 subscriptions and 5,036 invoices**, created in a disposable database. Each page was requested five times through Flask's test client.

| Page | Average server response | Maximum server response |
|---|---:|---:|
| Overview | 36.39 ms | 63.67 ms |
| Subscriptions | 5.19 ms | 9.48 ms |
| Invoices | 5.71 ms | 11.27 ms |
| Reports | 30.00 ms | 36.54 ms |

These measurements include server-side database queries and HTML generation. They exclude network transfer and browser layout and do not establish a universal two-second SLA or concurrent production capacity.

## Browser checks

The local server was opened in a browser, the demo administrator signed in, and the dashboard rendered successfully. Its navigation, summary cards and actual database values were inspected. Other primary pages were rendered through the automated test suite. Responsive and print styles are included; physical-phone testing and a complete visual check at every viewport were not performed.

## Limits

- The local email outbox and password-reset flow passed tests. Real SMTP delivery has not been tested with an external account.
- Payment recording is tested. No payment gateway or bank integration is implemented.
- Tests were run on assembled local source before staged repository integration. No cloud deployment was performed.
- Tests provide evidence for covered behaviour; they cannot prove the absence of every possible bug.
