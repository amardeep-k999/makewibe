# A six-minute demo

Run START.bat ahead of time. For a fully offline demo, finish installing dependencies before arriving.

1. **Overview, 30 seconds.** Sign in as `admin@brightloop.demo` / `Brightloop!2026`. Point to active subscriptions, collected payments, outstanding and overdue invoices. The chart comes from sample database payments.
2. **Admin setup, 45 seconds.** Open Catalog & rules. Show products, the Odoo variant adding ₹560, daily/weekly/monthly/yearly plan options, tax rules and discount conditions. Show Team members and explain that staff cannot open these admin pages.
3. **Create a subscription, 60 seconds.** Choose New subscription. Pick Amelia Harper and the “Small business launch” template. Use today's start date, an expiry next year, and 14-day payment terms. Submit. Explain that the template supplies Growth + five workspace seats + one Analytics add-on.
4. **Move the stages, 30 seconds.** Click Send to quotation → Confirm quotation → Activate subscription. Point to the subscription's number and product lines.
5. **Billing, 45 seconds.** Open Invoices → Run due billing. Open the newest draft. Explain subtotal, discount and tax, then confirm it. Run billing again: it should create zero duplicate invoices.
6. **Payment, 45 seconds.** Record a small payment, such as ₹100. Point to the remaining balance. Record exactly the remaining balance using the form's default amount. The invoice becomes Paid.
7. **Delivery and print, 30 seconds.** Click Send invoice. Explain that the demo writes an email file, not an external message. Click Print view; Ctrl+P shows a print/save-PDF version. Do not actually email real recipients during the demo.
8. **Customer portal, 40 seconds.** Sign out and sign in as `customer@brightloop.demo`, same password. Show only this customer's subscriptions/invoices. Open an active subscription to demonstrate pause/resume or future add-on changes. Run due billing first if the app requests it.
9. **Reports, 30 seconds.** Sign in as admin or staff. Filter Reports & payments by date/customer and export CSV. Explain collections versus invoiced sales versus estimated MRR.

## Password reset demonstration

Use Forgot password for the demo customer. The generated `.eml` file is under `instance/outbox/`. Open it in an email client and follow the link within 30 minutes. Resetting a demo account changes its password; remember the new one. Do this separately so it does not interrupt the main presentation.

## If something happens on stage

- “Port already in use”: the server is probably still running; open the existing URL.
- “Billing is due”: run billing before pausing, closing or replacing products.
- “No invoices created”: the subscription must be Active, its next date due, and the period not already invoiced.
- “Quotation expired”: create a new quotation; validity is deliberate.
- “Plan unavailable”: its enrollment dates must include the chosen start date.
- “Too many login attempts”: stop retrying; the login window resets after 15 minutes.
- No email in Gmail: demo mode uses the local outbox. External delivery requires SMTP.

Do not delete your database to fix a presentation problem. It contains all your saved records.
