# Requirement coverage and explicit decisions

Source: the four-page Subscription_Management_System.pdf supplied by the user. It specifies the product scenarios, but contains no organizer rules about frameworks or external services. Document content was used as requirements, not as authorization to contact people or provision external accounts.

| Scenario | Implementation | Where to demonstrate |
|---|---|---|
| Unique accounts and password rules | Case-insensitive unique email; 9+ characters, uppercase, lowercase, special; hashes | Signup |
| Forgotten password | 30-minute one-use reset token, digest stored, email transport | Forgot password + local outbox |
| Admin, staff, customer roles | Server-side role and record-ownership checks | Three demo accounts |
| Admin-only staff creation | Customer signup cannot request staff/admin role | Team members |
| Product attributes and variants | Type, sales/cost prices, notes, tax, extra variant price | Catalog products/variants |
| Plan policies | Four intervals, recurring fee, minimum quantity, enrollment dates, auto-close/pause/close/renew flags | Catalog plans |
| Quote templates | Plan, up to five product lines/variants, quantities and validity | Catalog templates → new subscription |
| Subscription records/stages | IDs, customer, dates, payment terms, line snapshots; validated transitions | Subscription detail |
| Recurring billing | Due-date catch-up, unique cycle invoice, atomic discount/invoice/date updates | Run due billing / scheduler |
| Invoice actions | Draft, confirmation, paid, cancellation, SMTP/outbox sending, print/PDF via browser | Invoice detail |
| Taxes and discounts | Rule-based tax, fixed/percent discounts, thresholds, dates, usage, product/subscription scopes | Catalog + generated invoice |
| Payments | Partial/full receipts, date/method/note, balance, duplicate request key | Invoice detail |
| Customer self-service | Own subscriptions/invoices, request quote, pause/resume/close/renew, update future add-ons, billing address | Customer login |
| Finance reporting | Current active/outstanding/overdue, payment date/customer filters, sales, MRR estimate, CSV | Overview + Reports |
| Thousands of records / two seconds | Pagination/indexes + reproducible 5,000+ record local benchmark | `tests/benchmark.py` |

## Business policies chosen where the statement is ambiguous

1. **Currency:** INR only. All stored money uses integer paise; percentages use hundredths of one percent (18% = 1800).
2. **Plan price:** a recurring base fee charged once per cycle, plus product unit prices multiplied by quantities. This is stated on the creation/setup screens.
3. **Minimum quantity:** sum of product units, excluding the plan fee. No product-free subscriptions.
4. **Availability versus term:** the start date must fall inside the plan's enrollment window. The subscription may continue beyond that availability window until its own expiry.
5. **Billing periods:** issue a bill at each scheduled cycle start that is on or before expiry. No proration for a final short period. An expiry equal to a billing date includes that date.
6. **Activation:** staff/admin confirm and activate. Customers can request a quotation but cannot activate it themselves. Future-start active subscriptions wait until their date to bill.
7. **Quote validity:** counted from creation using server-local calendar dates. Expired quotations require a new quotation with current pricing.
8. **Discount scope:** blank product/subscription means global; specifying both requires both to match. A product-scoped rule never discounts the plan fee.
9. **Discount thresholds:** evaluated on eligible lines before discount/tax. Product quantity excludes plan fees. Largest eligible discount wins; equal savings prefer the older rule (lower ID). Rules do not stack.
10. **Discount dates and uses:** evaluated against each invoice's billing date, including catch-up periods. A use is reserved when the invoice is generated, not when paid. Cancellation does not restore that use. Fixed discounts cannot make a line negative.
11. **Rounding:** proportional allocation of discounts to eligible lines, then per-line tax rounded half up to the nearest paise. The last allocation absorbs any rounding remainder.
12. **Snapshots:** subscription product prices are copied when chosen; invoice amounts/customer details are copied at billing. Existing invoice totals cannot be edited. Renewals copy existing product prices but use the selected plan's current fee; product replacement explicitly reprices the selected lines.
13. **Pause and close:** first finish billing already due active periods. Paused subscriptions create no new invoices. On resume, a fresh cycle starts at the later of today or the old next date. No retroactive paused-period bills, refunds or automatic term extensions.
14. **End of term:** billing never runs beyond expiry. Auto-close happens after earlier earned periods are billed. A non-auto-close plan remains visibly Active but expired until handled; it is excluded from current active/MRR totals.
15. **Renewal:** after term end, create one new Draft from the old subscription; the new term must start after the previous expiry and today or later. Staff review it before activation. Old invoices remain with the old term.
16. **Cancellation:** only unpaid Draft/Confirmed invoices may be cancelled. The invoice stays in history and its billing period is not recreated. Refunds, credit notes and replacement invoices are future work.
17. **Payments:** record already received funds; do not charge financial accounts. Positive amounts only, no future payment dates, no overpayment. A zero-total invoice becomes Paid on confirmation without a payment record.
18. **Reports:** collections use payment dates; invoiced sales use invoice billing dates and exclude tax; draft/cancelled invoices are excluded. Outstanding/overdue/active/MRR are current snapshots. MRR is a before-tax, before-discount estimate (monthly ×1, annual ÷12, weekly ×52/12, daily ×365/12), not statutory accounting.
19. **Scope and pagination:** main lists have 20 rows per page. Reports display the latest 100 matching payments; CSV exports up to 5,000. Catalog displays the latest 100 entries, and relevant admin selectors display up to 500 records. These bounds are visible/documented; a production catalog would need searchable selectors.
20. **Time:** business dates use the host's local calendar; SQLite activity timestamps are UTC and labeled as such. Use one consistent timezone for web and scheduler processes.
21. **Tax examples:** seeded 18% tax is a configurable illustrative rule, not jurisdiction-specific tax compliance or a complete statutory invoice format.

## Operational boundaries

The local app is complete for the implemented hackathon workflows. Actual external email requires SMTP credentials, and public hosting requires a Python-capable host with persistent disk and HTTPS. Those were not provisioned or live-tested. There is no production payment gateway, multi-currency accounting, refund processing, customer notification queue, or rich catalog migration/editing workflow.

The SQLite unique key and transaction make billing reliable locally, but benchmarks do not establish multi-region scaling, high write concurrency or a universal two-second browser-load SLA.
