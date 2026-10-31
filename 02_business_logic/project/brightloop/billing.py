"""The billing engine: calculate a bill, then save it once per billing date."""
from datetime import date, timedelta
from brightloop.database import get_db
from brightloop.helpers import today, round_ratio, cycle_date, log_event


def get_bill_lines(sub):
    db = get_db()
    plan = db.execute('SELECT p.*,COALESCE(t.rate,0) AS rate FROM plans p LEFT JOIN taxes t ON t.id=p.tax_id WHERE p.id=?', (sub['plan_id'],)).fetchone()
    lines = []
    if sub['plan_price']:
        lines.append({'product_id': None, 'description': sub['plan_name'] + ' · plan fee',
                      'quantity': 1, 'unit_price': sub['plan_price'], 'rate': plan['rate']})
    rows = db.execute('''SELECT l.*,COALESCE(t.rate,0) AS rate FROM subscription_lines l
        LEFT JOIN taxes t ON t.id=l.tax_id WHERE subscription_id=? ORDER BY l.id''', (sub['id'],)).fetchall()
    for row in rows:
        lines.append(dict(row))
    for line in lines:
        line['subtotal'] = line['quantity'] * line['unit_price']
        line['discount'] = 0
    return lines


def choose_discount(sub, lines, billing_date):
    """Use the single eligible rule with the largest saving; rules do not stack."""
    rules = get_db().execute('''SELECT * FROM discounts WHERE starts<=? AND ends>=? AND uses<max_uses
        AND (subscription_id IS NULL OR subscription_id=?) ORDER BY id''',
        (billing_date, billing_date, sub['id'])).fetchall()
    best_rule, best_amount, best_indices = None, 0, []
    for rule in rules:
        indices = []
        for index, line in enumerate(lines):
            if rule['product_id'] is None or line['product_id'] == rule['product_id']:
                indices.append(index)
        subtotal = sum(lines[i]['subtotal'] for i in indices)
        # Plan fees are not product seats, so do not count them toward quantity.
        quantity = sum(lines[i]['quantity'] for i in indices if lines[i]['product_id'] is not None)
        if subtotal < rule['min_purchase'] or quantity < rule['min_quantity']:
            continue
        amount = rule['value'] if rule['kind'] == 'fixed' else round_ratio(subtotal, rule['value'], 10000)
        amount = min(amount, subtotal)
        if amount > best_amount:
            best_rule, best_amount, best_indices = rule, amount, indices
    if best_rule:
        # Distribute a fixed discount fairly, with the last line taking the remainder.
        remaining_discount = best_amount
        remaining_subtotal = sum(lines[i]['subtotal'] for i in best_indices)
        for index in best_indices:
            line = lines[index]
            share = 0 if remaining_subtotal == 0 else round_ratio(remaining_discount, line['subtotal'], remaining_subtotal)
            share = min(share, line['subtotal'])
            line['discount'] = share
            remaining_discount -= share
            remaining_subtotal -= line['subtotal']
    return best_rule


def create_invoice(sub, billing_date):
    """Caller owns the transaction so discounts and invoice creation are atomic."""
    db = get_db()
    if db.execute('SELECT id FROM invoices WHERE subscription_id=? AND billing_date=?', (sub['id'], billing_date)).fetchone():
        return False
    customer = db.execute('SELECT * FROM users WHERE id=?', (sub['customer_id'],)).fetchone()
    lines = get_bill_lines(sub)
    discount = choose_discount(sub, lines, billing_date)
    for line in lines:
        net = line['subtotal'] - line['discount']
        line['tax'] = round_ratio(net, line['rate'], 10000)
        line['total'] = net + line['tax']
    subtotal = sum(line['subtotal'] for line in lines)
    savings = sum(line['discount'] for line in lines)
    tax = sum(line['tax'] for line in lines)
    total = subtotal - savings + tax
    due = (date.fromisoformat(billing_date) + timedelta(days=sub['payment_days'])).isoformat()
    cursor = db.execute('''INSERT INTO invoices(subscription_id,customer_id,customer_name,customer_email,
        customer_address,billing_date,due_date,subtotal,discount,tax,total,discount_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (sub['id'], customer['id'], customer['name'], customer['email'], customer['address'], billing_date,
         due, subtotal, savings, tax, total, discount['name'] if discount else ''))
    invoice_id = cursor.lastrowid
    for line in lines:
        db.execute('''INSERT INTO invoice_lines(invoice_id,description,quantity,unit_price,discount,tax_rate,tax,total)
            VALUES (?,?,?,?,?,?,?,?)''', (invoice_id, line['description'], line['quantity'], line['unit_price'],
                                        line['discount'], line['rate'], line['tax'], line['total']))
    if discount:
        db.execute('UPDATE discounts SET uses=uses+1 WHERE id=?', (discount['id'],))
    return True


def run_billing(as_of=None, limit=1000):
    """Catch up missed cycles. A batch limit protects responsiveness without skipping dates."""
    as_of = as_of or today()
    db = get_db()
    count = 0
    try:
        db.execute('BEGIN IMMEDIATE')  # Only one writer may bill at a time.
        rows = db.execute("SELECT * FROM subscriptions WHERE status='Active' AND next_billing<=? ORDER BY next_billing,id LIMIT ?", (as_of, limit)).fetchall()
        for row in rows:
            sub = dict(row)
            while sub['next_billing'] <= min(as_of, sub['expiry_date']) and count < limit:
                if create_invoice(sub, sub['next_billing']):
                    count += 1
                sub['cycle_number'] += 1
                sub['next_billing'] = cycle_date(sub['billing_anchor'], sub['interval'], sub['cycle_number'])
            db.execute('UPDATE subscriptions SET next_billing=?,cycle_number=? WHERE id=?',
                       (sub['next_billing'], sub['cycle_number'], sub['id']))
            if count >= limit:
                break
        # End an auto-close term only after all earned billing periods were processed.
        db.execute('''UPDATE subscriptions SET status='Closed' WHERE expiry_date<?
            AND ((status='Active' AND next_billing>expiry_date) OR status='Paused')
            AND plan_id IN (SELECT id FROM plans WHERE auto_close=1)''', (as_of,))
        if count:
            log_event(f'Billing run created {count} invoices.')
        db.commit()
        return count
    except Exception:
        db.rollback()
        raise
