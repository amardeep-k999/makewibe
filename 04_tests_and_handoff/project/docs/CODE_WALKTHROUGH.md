# Explain the program in plain Python

## The one-minute explanation

“The browser shows HTML forms. When someone submits a form, Flask calls a Python function. That function checks the user's role, validates the inputs, reads or updates SQLite, then returns an HTML page. The billing function creates invoices from active subscriptions. Payments update the remaining amount, and reports read those saved records.”

## Follow one request

1. Open `/subscriptions/new`. Flask matches the URL to `new_subscription()` in `subscriptions.py`.
2. For a GET request, it loads plans/products and shows `subscription_form.html`.
3. The person submits the form. The browser makes a POST request to the same URL.
4. `request.form` behaves like a dictionary: `request.form.get('plan_id')` reads one input.
5. `create_subscription()` validates the customer, plan, dates and product quantities.
6. It inserts the subscription row, then inserts its product lines.
7. `db.commit()` saves the changes together. On validation failure, `rollback()` discards them.
8. `redirect()` sends the browser to the new subscription page, preventing accidental refresh resubmission.

## The few Flask concepts you need

```python
@subscriptions.get('/subscriptions')
@require_login
def list_subscriptions():
    ...
```

- `def` defines an ordinary Python function.
- A decorator is a line starting with `@` that adds behaviour to a function. The route decorator says which URL calls it.
- `@require_login` checks whether the person signed in before running the function.
- A `Blueprint` is just a named group of related page functions. It allows separate files without putting every route in `app.py`.
- `session` remembers the signed-in user ID in a signed cookie. It never stores the password.
- `g` is temporary storage for one request; `g.user` is that request's signed-in account.
- `render_template()` fills an HTML file with Python data.
- `flash()` stores a short success/error message to show after a redirect.
- `create_app()` puts these parts together. Tests call it with a different database so test records cannot affect your demo.

`helpers.py` uses `wraps` inside the login decorator to keep the original function's name. It is standard plumbing, not a business calculation. In Q&A, explain its purpose; you do not need to pretend you invented Flask.

## Basic SQL in this project

```python
user = db.execute(
    'SELECT * FROM users WHERE email = ?',
    (email,)
).fetchone()
```

- `SELECT` reads data. `INSERT` creates it. `UPDATE` changes it. `DELETE` removes it.
- `?` means “put the supplied value here safely.” Do not build SQL by joining user input into strings.
- `(email,)` is a Python tuple containing one value; its trailing comma matters.
- `fetchone()` returns one record. `fetchall()` returns a list of records.
- `row['email']` gets a named column because the database uses `sqlite3.Row`.
- IDs connect records: `subscriptions.customer_id` points to `users.id`.
- A `JOIN` reads connected tables in one query.
- An index is like a book index: it helps the database find matching records without scanning everything.

The few SQL strings using an f-string use fixed column/table conditions built by the program. User-supplied values remain in parameter tuples/lists.

## How an invoice is calculated

Read `billing.py` in this order:

1. `get_bill_lines()` copies the saved plan fee and subscription product lines.
2. `choose_discount()` checks dates, scope, minimums and remaining uses. It chooses the largest saving.
3. `create_invoice()` calculates each line's tax and total and stores a snapshot.
4. `run_billing()` finds due subscriptions, creates every due period and advances the next billing date.

Example: two seats at ₹100 each, with a 10% discount and 18% tax:

```text
Subtotal = 2 × ₹100 = ₹200
Discount = ₹200 × 10% = ₹20
Taxable amount = ₹200 − ₹20 = ₹180
Tax = ₹180 × 18% = ₹32.40
Invoice total = ₹212.40
```

The database stores these as integer paise: `20000`, `2000`, `3240`, `21240`. This avoids floating-point surprises such as `0.1 + 0.2` not being exactly `0.3`.

## Why a repeated billing run is safe

`UNIQUE(subscription_id, billing_date)` prevents a second invoice for the same cycle. `BEGIN IMMEDIATE` reserves the SQLite write transaction before the billing operation starts. Invoice rows, discount use counts and the next billing date are committed together. A failure rolls all of them back. The next run can retry the same date.

## Dates without complicated scheduling

`cycle_date()` calculates dates from the original billing anchor. For January 31, the following dates are February 28/29 and March 31. Adding a month to February 28 repeatedly would incorrectly drift to the 28th forever, so we do not use that approach.

The scheduler simply runs a loop: call billing, wait 60 seconds, repeat. It does not need a complex task-queue framework.

## Payments and reports

`record_payment()` confirms that an invoice is payable and the payment is positive and no larger than the remaining balance. Multiple smaller payments are allowed. The invoice becomes Paid when payments exactly equal its total. A unique request key prevents the same submitted form from recording money twice.

Reports distinguish cash received, invoiced sales excluding tax, unpaid balances, overdue balances and an estimated normalized monthly recurring amount. Read the descriptions on the reports page before describing a number as “revenue.”

## What HTML and CSS do

HTML defines headings, tables and forms. CSS defines appearance and small-screen layout. Jinja inserts Python values into HTML, for example `{{ sub.plan_name }}`. `{% for line in lines %}` repeats a table row. Jinja escapes values by default so a customer name cannot become executable HTML.

There is no application JavaScript to learn. The visual chart is ordinary HTML/CSS with heights calculated by Python.

## Suggested study order

1. `helpers.py`: `money`, `cents`, `number`, `cycle_date`.
2. `schema.sql`: users → subscriptions → invoices → payments.
3. `subscriptions.py`: `read_product_lines` and `create_subscription`.
4. `billing.py`: all four functions.
5. `invoices.py`: `record_payment`.
6. Your assigned feature's route functions and templates.
7. `app.py` and authentication plumbing last.
