"""Invoice views, confirmation, cancellation, delivery and payment recording."""
import secrets
from flask import Blueprint, flash, g, render_template, request, redirect, url_for
from brightloop.database import get_db
from brightloop.helpers import require_login, require_team, owned_row, cents, valid_date, today, log_event, money, page_number
from brightloop.billing import run_billing
from brightloop.mailer import send_mail

invoices = Blueprint('invoices', __name__)


@invoices.get('/invoices')
@require_login
def list_invoices():
    db = get_db()
    conditions, values = ['1=1'], []
    if g.user['role'] == 'customer':
        conditions.extend(['i.customer_id=?', "i.status!='Draft'"])
        values.append(g.user['id'])
    status = request.args.get('status', '')
    if status == 'Overdue':
        conditions.append("i.status='Confirmed' AND i.due_date<?")
        values.append(today())
    elif status:
        conditions.append('i.status=?')
        values.append(status)
    query = request.args.get('q', '').strip()[:100]
    if query:
        conditions.append('(i.customer_name LIKE ? OR CAST(i.id AS TEXT)=?)')
        values.extend([f'%{query}%', query.removeprefix('INV-').lstrip('0')])
    where = ' AND '.join(conditions)
    page = page_number(request.args.get('page'))
    total = db.execute(f'SELECT COUNT(*) FROM invoices i WHERE {where}', values).fetchone()[0]
    rows = db.execute(f'''SELECT i.*,COALESCE((SELECT SUM(amount) FROM payments WHERE invoice_id=i.id),0) AS paid
        FROM invoices i WHERE {where} ORDER BY i.id DESC LIMIT 20 OFFSET ?''', values+[(page-1)*20]).fetchall()
    return render_template('invoices.html', title='Invoices', rows=rows, status=status, query=query, total=total, page=page)


@invoices.get('/invoices/<int:invoice_id>')
@require_login
def detail(invoice_id):
    invoice = owned_row('invoices', invoice_id)
    if g.user['role'] == 'customer' and invoice['status'] == 'Draft':
        from flask import abort
        abort(404)
    db = get_db()
    lines = db.execute('SELECT * FROM invoice_lines WHERE invoice_id=? ORDER BY id', (invoice_id,)).fetchall()
    payments = db.execute('SELECT * FROM payments WHERE invoice_id=? ORDER BY id DESC', (invoice_id,)).fetchall()
    balance = invoice['total'] - sum(payment['amount'] for payment in payments)
    return render_template('invoice_detail.html', title=f'INV-{invoice_id:04d}', invoice=invoice, lines=lines,
                           payments=payments, balance=balance, request_key=secrets.token_hex(24), printing=request.args.get('print') == '1')


def record_payment(invoice_id, form):
    db = get_db()
    amount = cents(form.get('amount'))
    if amount <= 0:
        raise ValueError('Payment must be greater than zero.')
    method = form.get('method')
    if method not in ('Bank transfer', 'UPI', 'Card', 'Cash', 'Other'):
        raise ValueError('Choose a valid payment method.')
    payment_date = valid_date(form.get('payment_date'))
    if payment_date > today():
        raise ValueError('A received payment cannot have a future date.')
    key = form.get('request_key', '')
    if len(key) < 20 or len(key) > 100:
        raise ValueError('Refresh this page and try again.')
    db.execute('BEGIN IMMEDIATE')
    if db.execute('SELECT id FROM payments WHERE request_key=?', (key,)).fetchone():
        db.rollback()
        return False
    invoice = owned_row('invoices', invoice_id)
    if invoice['status'] != 'Confirmed':
        raise ValueError('Payments can be recorded only on confirmed, unpaid invoices.')
    paid = db.execute('SELECT COALESCE(SUM(amount),0) FROM payments WHERE invoice_id=?', (invoice_id,)).fetchone()[0]
    if amount > invoice['total'] - paid:
        raise ValueError('Payment exceeds the remaining balance.')
    db.execute('INSERT INTO payments(invoice_id,amount,method,payment_date,note,request_key) VALUES (?,?,?,?,?,?)',
               (invoice_id, amount, method, payment_date, form.get('note', '')[:1000], key))
    if amount + paid == invoice['total']:
        db.execute("UPDATE invoices SET status='Paid' WHERE id=?", (invoice_id,))
    log_event(f'Recorded {money(amount)} against INV-{invoice_id:04d}.')
    db.commit()
    return True


@invoices.post('/invoices/<int:invoice_id>/<action>')
@require_login
def action(invoice_id, action):
    require_team()
    db = get_db()
    try:
        if action == 'payment':
            saved = record_payment(invoice_id, request.form)
            flash('Payment recorded.' if saved else 'This payment was already recorded.', 'success')
        elif action in ('confirm', 'cancel'):
            db.execute('BEGIN IMMEDIATE')
            invoice = owned_row('invoices', invoice_id)
            if action == 'confirm':
                if invoice['status'] != 'Draft':
                    raise ValueError('Only a draft invoice can be confirmed.')
                status = 'Paid' if invoice['total'] == 0 else 'Confirmed'
            else:
                paid = db.execute('SELECT COUNT(*) FROM payments WHERE invoice_id=?', (invoice_id,)).fetchone()[0]
                if paid or invoice['status'] not in ('Draft', 'Confirmed'):
                    raise ValueError('An invoice with payments cannot be cancelled.')
                status = 'Cancelled'
            db.execute('UPDATE invoices SET status=? WHERE id=?', (status, invoice_id))
            log_event(f'INV-{invoice_id:04d}: {status}.')
            db.commit()
            flash('Invoice updated.', 'success')
        elif action == 'send':
            invoice = owned_row('invoices', invoice_id)
            if invoice['status'] not in ('Confirmed', 'Paid'):
                raise ValueError('Confirm this invoice before sending it.')
            lines = db.execute('SELECT * FROM invoice_lines WHERE invoice_id=?', (invoice_id,)).fetchall()
            body = f"Hello {invoice['customer_name']},\n\nInvoice INV-{invoice_id:04d}\n"
            for line in lines:
                body += f"{line['description']} × {line['quantity']}: {money(line['total'])}\n"
            body += f"\nDiscount: {money(invoice['discount'])}\nTax: {money(invoice['tax'])}\nTotal: {money(invoice['total'])}\nDue: {invoice['due_date']}\n\nSign in to your Brightloop portal to view your invoice."
            message = send_mail(invoice['customer_email'], f'Brightloop invoice INV-{invoice_id:04d}', body)
            db.execute('UPDATE invoices SET sent_at=CURRENT_TIMESTAMP WHERE id=?', (invoice_id,))
            db.commit()
            flash(message, 'success')
        else:
            raise ValueError('Unknown invoice action.')
    except (ValueError, OSError) as error:
        db.rollback()
        flash(str(error), 'error')
    return redirect(url_for('invoices.detail', invoice_id=invoice_id))


@invoices.post('/billing/run')
@require_login
def billing_run():
    require_team()
    count = run_billing()
    flash(f'Billing complete: {count} new draft invoices. Runs are safe to repeat. Batches contain up to 1,000 invoices.', 'success')
    return redirect(url_for('invoices.list_invoices'))
