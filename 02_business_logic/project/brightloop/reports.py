"""Dashboard totals and date-filtered finance reports, calculated with SQL."""
import csv
import io
from datetime import date, timedelta
from flask import Blueprint, Response, flash, g, render_template, request
from brightloop.database import get_db
from brightloop.helpers import require_login, require_team, today, date_range

reports = Blueprint('reports', __name__)


def summary(customer_id=None, start=None, end=None):
    db = get_db()
    values = []
    invoice_where = '1=1'
    subscription_where = '1=1'
    if customer_id:
        invoice_where += ' AND i.customer_id=?'
        subscription_where += ' AND s.customer_id=?'
        values.append(customer_id)
    # Active count and outstanding are current snapshots, not date-window totals.
    active = db.execute(f"SELECT COUNT(*) FROM subscriptions s WHERE {subscription_where} AND status='Active' AND start_date<=? AND expiry_date>=?", values+[today(), today()]).fetchone()[0]
    rows = db.execute(f'''SELECT i.total,i.due_date,COALESCE((SELECT SUM(amount) FROM payments WHERE invoice_id=i.id),0) AS paid
        FROM invoices i WHERE {invoice_where} AND i.status='Confirmed' ''', values).fetchall()
    outstanding = sum(row['total']-row['paid'] for row in rows)
    overdue = sum(row['total']-row['paid'] for row in rows if row['due_date'] < today())
    overdue_count = sum(1 for row in rows if row['due_date'] < today())
    payment_where, payment_values = invoice_where, values.copy()
    if start and end:
        payment_where += ' AND p.payment_date BETWEEN ? AND ?'
        payment_values.extend([start, end])
    collected = db.execute(f'''SELECT COALESCE(SUM(p.amount),0) FROM payments p
        JOIN invoices i ON i.id=p.invoice_id WHERE {payment_where}''', payment_values).fetchone()[0]
    sales_where, sales_values = invoice_where, values.copy()
    if start and end:
        sales_where += ' AND i.billing_date BETWEEN ? AND ?'
        sales_values.extend([start, end])
    sales = db.execute(f'''SELECT COALESCE(SUM(i.total-i.tax),0) FROM invoices i
        WHERE {sales_where} AND i.status IN ('Confirmed','Paid')''', sales_values).fetchone()[0]
    # MRR is an estimate: normalize each current contract to one average month.
    mrr = db.execute(f'''SELECT COALESCE(ROUND(SUM((s.plan_price + COALESCE(
        (SELECT SUM(quantity*unit_price) FROM subscription_lines WHERE subscription_id=s.id),0)) *
        CASE s.interval WHEN 'yearly' THEN 1.0/12 WHEN 'weekly' THEN 52.0/12
        WHEN 'daily' THEN 365.0/12 ELSE 1 END)),0)
        FROM subscriptions s WHERE {subscription_where} AND s.status='Active'
        AND s.start_date<=? AND s.expiry_date>=?''', values+[today(),today()]).fetchone()[0]
    return {'active': active, 'collected': collected, 'outstanding': outstanding,
            'overdue': overdue, 'overdue_count': overdue_count, 'sales': sales, 'mrr': int(mrr)}


@reports.get('/')
@require_login
def dashboard():
    db = get_db()
    customer_id = g.user['id'] if g.user['role'] == 'customer' else None
    month_start = date.today().replace(day=1).isoformat()
    stats = summary(customer_id, month_start, today())
    clause = 'AND i.customer_id=?' if customer_id else ''
    values = [customer_id] if customer_id else []
    bills = db.execute(f'''SELECT i.*,COALESCE((SELECT SUM(amount) FROM payments WHERE invoice_id=i.id),0) AS paid
        FROM invoices i WHERE i.status='Confirmed' {clause} ORDER BY i.due_date LIMIT 5''', values).fetchall()
    sub_clause = 'AND s.customer_id=?' if customer_id else ''
    upcoming = db.execute(f'''SELECT s.*,u.name AS customer_name FROM subscriptions s JOIN users u ON u.id=s.customer_id
        WHERE s.status='Active' AND s.next_billing<=s.expiry_date {sub_clause} ORDER BY s.next_billing LIMIT 4''', values).fetchall()
    chart = []
    for offset in range(5, -1, -1):
        month_index = date.today().year*12 + date.today().month-1-offset
        year, month = divmod(month_index, 12)
        key = f'{year}-{month+1:02d}'
        value = db.execute(f'''SELECT COALESCE(SUM(p.amount),0) FROM payments p JOIN invoices i ON i.id=p.invoice_id
            WHERE substr(p.payment_date,1,7)=? {clause}''', [key]+values).fetchone()[0]
        chart.append({'label': date(year, month+1, 1).strftime('%b'), 'value': value})
    maximum = max([point['value'] for point in chart]+[1])
    for point in chart:
        point['height'] = max(2, int(point['value']/maximum*100))
    events = [] if customer_id else db.execute('SELECT * FROM activity ORDER BY id DESC LIMIT 4').fetchall()
    return render_template('dashboard.html', title='Overview', stats=stats, bills=bills, upcoming=upcoming,
                           chart=chart, events=events, month_name=date.today().strftime('%B %Y'))


def report_data():
    start = request.args.get('start', date.today().replace(day=1).isoformat())
    end = request.args.get('end', today())
    try:
        start, end = date_range(start, end)
    except ValueError as error:
        flash(str(error), 'error')
        start, end = date.today().replace(day=1).isoformat(), today()
    customer_id = request.args.get('customer_id') or None
    if customer_id and not get_db().execute("SELECT id FROM users WHERE id=? AND role='customer'", (customer_id,)).fetchone():
        customer_id = None
    where, values = 'p.payment_date BETWEEN ? AND ?', [start, end]
    if customer_id:
        where += ' AND i.customer_id=?'
        values.append(customer_id)
    rows = get_db().execute(f'''SELECT p.*,i.customer_name FROM payments p JOIN invoices i ON i.id=p.invoice_id
        WHERE {where} ORDER BY p.payment_date DESC,p.id DESC LIMIT 5000''', values).fetchall()
    return start, end, customer_id, rows


@reports.get('/reports')
@require_login
def finance():
    require_team()
    start, end, customer_id, rows = report_data()
    customers = get_db().execute("SELECT id,name FROM users WHERE role='customer' ORDER BY name").fetchall()
    stats = summary(customer_id, start, end)
    return render_template('reports.html', title='Reports', stats=stats, rows=rows[:100], start=start, end=end,
                           customer_id=customer_id, customers=customers)


@reports.get('/reports/export.csv')
@require_login
def export():
    require_team()
    start, end, customer_id, rows = report_data()
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['Payment', 'Invoice', 'Customer', 'Amount (INR)', 'Method', 'Date', 'Note'])
    for row in rows:
        values = [row['id'], f"INV-{row['invoice_id']:04d}", row['customer_name'], f"{row['amount']/100:.2f}", row['method'], row['payment_date'], row['note']]
        # Prevent text beginning with '=' from becoming a spreadsheet formula.
        safe = []
        for value in values:
            value = str(value)
            if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
                value = "'" + value
            safe.append(value)
        writer.writerow(safe)
    return Response('\ufeff' + stream.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=brightloop-payments.csv'})
