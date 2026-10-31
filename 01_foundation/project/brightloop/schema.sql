-- Money is stored as integer paise: 199.50 rupees becomes 19950.
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','staff','customer')),
 address TEXT NOT NULL DEFAULT '', session_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS reset_tokens (
 digest TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_attempts (
 email TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS taxes (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, rate INTEGER NOT NULL CHECK(rate BETWEEN 0 AND 10000)
);
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
 sales_price INTEGER NOT NULL CHECK(sales_price >= 0), cost_price INTEGER NOT NULL CHECK(cost_price >= 0),
 notes TEXT NOT NULL DEFAULT '', tax_id INTEGER REFERENCES taxes(id)
);
CREATE TABLE IF NOT EXISTS variants (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
 name TEXT NOT NULL, extra_price INTEGER NOT NULL CHECK(extra_price >= 0)
);
CREATE TABLE IF NOT EXISTS plans (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, price INTEGER NOT NULL CHECK(price >= 0),
 interval TEXT NOT NULL CHECK(interval IN ('daily','weekly','monthly','yearly')),
 min_quantity INTEGER NOT NULL CHECK(min_quantity > 0), available_from TEXT NOT NULL, available_to TEXT NOT NULL,
 auto_close INTEGER NOT NULL DEFAULT 1, allow_close INTEGER NOT NULL DEFAULT 1,
 allow_pause INTEGER NOT NULL DEFAULT 1, allow_renew INTEGER NOT NULL DEFAULT 1,
 tax_id INTEGER REFERENCES taxes(id)
);
CREATE TABLE IF NOT EXISTS quote_templates (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, plan_id INTEGER NOT NULL REFERENCES plans(id),
 valid_days INTEGER NOT NULL CHECK(valid_days > 0)
);
CREATE TABLE IF NOT EXISTS template_lines (
 id INTEGER PRIMARY KEY, template_id INTEGER NOT NULL REFERENCES quote_templates(id),
 product_id INTEGER NOT NULL REFERENCES products(id), variant_id INTEGER REFERENCES variants(id),
 quantity INTEGER NOT NULL CHECK(quantity > 0)
);
CREATE TABLE IF NOT EXISTS subscriptions (
 id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES users(id), plan_id INTEGER NOT NULL REFERENCES plans(id),
 status TEXT NOT NULL DEFAULT 'Draft', start_date TEXT NOT NULL, expiry_date TEXT NOT NULL,
 payment_days INTEGER NOT NULL DEFAULT 14, quote_until TEXT NOT NULL,
 next_billing TEXT NOT NULL, billing_anchor TEXT NOT NULL, cycle_number INTEGER NOT NULL DEFAULT 0,
 plan_price INTEGER NOT NULL, plan_name TEXT NOT NULL, interval TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS subscription_lines (
 id INTEGER PRIMARY KEY, subscription_id INTEGER NOT NULL REFERENCES subscriptions(id),
 product_id INTEGER NOT NULL REFERENCES products(id), description TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity > 0), unit_price INTEGER NOT NULL CHECK(unit_price >= 0),
 tax_id INTEGER REFERENCES taxes(id)
);
CREATE TABLE IF NOT EXISTS discounts (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('fixed','percent')),
 value INTEGER NOT NULL CHECK(value > 0), min_purchase INTEGER NOT NULL DEFAULT 0,
 min_quantity INTEGER NOT NULL DEFAULT 1, starts TEXT NOT NULL, ends TEXT NOT NULL,
 max_uses INTEGER NOT NULL CHECK(max_uses > 0), uses INTEGER NOT NULL DEFAULT 0,
 product_id INTEGER REFERENCES products(id), subscription_id INTEGER REFERENCES subscriptions(id)
);
CREATE TABLE IF NOT EXISTS invoices (
 id INTEGER PRIMARY KEY, subscription_id INTEGER NOT NULL REFERENCES subscriptions(id),
 customer_id INTEGER NOT NULL REFERENCES users(id), customer_name TEXT NOT NULL,
 customer_email TEXT NOT NULL, customer_address TEXT NOT NULL,
 billing_date TEXT NOT NULL, due_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Draft',
 subtotal INTEGER NOT NULL, discount INTEGER NOT NULL, tax INTEGER NOT NULL, total INTEGER NOT NULL,
 discount_name TEXT NOT NULL DEFAULT '', sent_at TEXT,
 UNIQUE(subscription_id, billing_date)
);
CREATE TABLE IF NOT EXISTS invoice_lines (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id), description TEXT NOT NULL,
 quantity INTEGER NOT NULL, unit_price INTEGER NOT NULL, discount INTEGER NOT NULL,
 tax_rate INTEGER NOT NULL, tax INTEGER NOT NULL, total INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id), amount INTEGER NOT NULL CHECK(amount > 0),
 method TEXT NOT NULL, payment_date TEXT NOT NULL, note TEXT NOT NULL,
 request_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS activity (
 id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), message TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS subscriptions_customer ON subscriptions(customer_id, id);
CREATE INDEX IF NOT EXISTS subscriptions_due ON subscriptions(status, next_billing);
CREATE INDEX IF NOT EXISTS invoices_customer ON invoices(customer_id, id);
CREATE INDEX IF NOT EXISTS invoices_due ON invoices(status, due_date);
CREATE INDEX IF NOT EXISTS payments_invoice ON payments(invoice_id);
CREATE INDEX IF NOT EXISTS payments_date ON payments(payment_date);
CREATE INDEX IF NOT EXISTS subscription_lines_parent ON subscription_lines(subscription_id);
CREATE INDEX IF NOT EXISTS invoice_lines_parent ON invoice_lines(invoice_id);
