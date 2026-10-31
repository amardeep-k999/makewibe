# Likely Q&A questions

Use these as study notes. Answer in your own words and practise explaining the functions assigned to you.

**1. What problem does this solve?**
It replaces scattered subscription spreadsheets, manual renewal tracking, manual invoices and payment matching with one connected record of the billing lifecycle.

**2. Why Python and Flask?**
Our team knows Python. Flask maps URLs to small Python functions, so we can separate features without a large framework. The browser uses standard HTML/CSS.

**3. Why SQLite instead of Supabase?**
SQLite is included with Python, stores data in one local file and works offline for the demo. It avoids cloud setup and helps us explain the database. A larger hosted system could migrate to PostgreSQL later.

**4. Does the app work without internet?**
Yes, after dependencies are installed. The sample database, pages and CSS are local. Real SMTP email requires a configured email server and network access.

**5. What are the main database relationships?**
A customer has subscriptions. A subscription uses a plan and has product lines. It generates invoices. Each invoice has lines and zero or more payments. Variants belong to products.

**6. How are admins, staff and customers separated?**
Each user has a role. Server-side functions check the role before an action. Customers also need ownership of the requested subscription or invoice; changing a URL cannot bypass that check. Only admins create staff or business rules.

**7. Are passwords stored directly?**
No. Werkzeug generates a salted password hash. Login verifies against that hash. The session stores a user ID and version, not the password.

**8. How does password reset work?**
We generate a random token, save only its SHA-256 digest and expiry in SQLite, and send the actual link to the registered email. The link expires after 30 minutes and is deleted after use. Changing the password invalidates previous login sessions.

**9. How do you prevent duplicate invoices?**
The database has a unique combination of subscription ID and billing date. The billing function also checks that combination and creates the invoice inside a transaction.

**10. What if the app crashes halfway through billing?**
SQLite rolls back the unfinished transaction, including invoice creation, discount counts and the next date. The scheduler can safely retry it.

**11. What if the scheduler was offline for a week?**
Billing begins at the subscription's saved next billing date and catches up each due cycle. It processes batches of up to 1,000 invoices, so later runs continue the backlog.

**12. Why integer paise?**
Money needs reliable arithmetic. ₹100.25 is stored as 10025. Decimal calculations round percentages to the nearest paise, half up.

**13. How are tax and discount calculated?**
Find the largest eligible discount, apply it to the matching line amounts, then calculate tax on each discounted line. Sum the line totals. Rules check dates, scope, quantities, purchase amount and usage limits.

**14. Can discounts stack?**
No. We chose the largest eligible saving because the statement does not specify stacking. The policy is visible on the admin form and documented.

**15. Does a product variant affect the bill?**
Yes. Its extra price is added to the product's unit price before multiplying by quantity. The example Odoo variant adds ₹560 per unit.

**16. What happens when a product price changes?**
Subscriptions keep a price snapshot. Existing invoices also keep their own immutable line and customer snapshots. Updating product selections explicitly uses current catalog prices for future invoices only.

**17. Can a customer pay half now and half later?**
Yes. We add the payments and calculate the remaining balance. The invoice stays Confirmed until the full total is recorded, then becomes Paid. Overpayments are rejected.

**18. Does clicking “Record payment” take money from a bank?**
No. It records an incoming payment already received by the business. This implementation does not connect to bank accounts or charge cards.

**19. How are invoices sent and printed?**
Sending uses the local email outbox for the offline demo or configured SMTP for actual delivery. Print view uses the browser's print dialog and print-specific CSS; the user can save it as a PDF.

**20. What happens when a subscription is paused?**
It stops generating new invoices. Any already due cycles must be billed first. On resume, the next cycle starts on the later of today and the previous scheduled date. No paused time is charged or prorated.

**21. How do renewals work?**
After a term ends, an allowed renewal copies the products into a new draft with new dates. It requires review and activation. The old term stays closed and can be renewed only once.

**22. What does your dashboard call revenue?**
It shows actual payments as collections. Reports separately show confirmed invoiced sales excluding tax and an estimated MRR. MRR normalizes active contract prices by their billing frequency, before tax/discounts. It is not a formal accounting revenue-recognition engine.

**23. Can it handle thousands of subscriptions in under two seconds?**
Our repeatable local benchmark creates over 5,000 subscriptions and invoices, and measures four major server-rendered pages. See TEST_RESULTS.md for measured timings. Pagination and indexes help. These timings do not guarantee every network, machine or concurrent production workload.

**24. What protects the forms?**
CSRF tokens reject cross-site form submissions; parameterized SQL protects query values; templates escape HTML; role and ownership checks run on the server. Login attempts have a basic rate limit. Real hosting also needs HTTPS and operational controls.

**25. How did you test it?**
Automated tests cover roles, ownership, invalid input, password resets, recurring dates, discount/tax calculations, duplicate/concurrent billing, transaction rollback, partial payments, renewals, page rendering and CSV safety. We also inspected the interface in a browser.

**26. What would you improve next?**
Hosted deployment with persistent PostgreSQL, real SMTP monitoring, payment gateway reconciliation, refunds/credit notes, richer catalog editing, proration and production backup/recovery. These should be described as future work, not as completed features.
