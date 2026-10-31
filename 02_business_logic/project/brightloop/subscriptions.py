"""Create quotations and move subscriptions through their allowed stages."""
from datetime import date, timedelta
from flask import Blueprint, flash, g, render_template, request, redirect, url_for, abort
from brightloop.database import get_db
from brightloop.helpers import require_login, require_team, owned_row, number, date_range, today, log_event, page_number

subscriptions = Blueprint('subscriptions', __name__)


def read_product_lines(form):
    """The form has five optional rows. Empty rows are simply ignored."""
    lines = []
    db = get_db()
    for index in range(5):
        product_id = form.get(f'product_{index}')
        if not product_id:
            continue
        product = db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
        if not product:
            raise ValueError('Choose a valid product.')
        variant_id = form.get(f'variant_{index}') or None
        extra_price = 0
        description = product['name']
        if variant_id:
            variant = db.execute('SELECT * FROM variants WHERE id=? AND product_id=?', (variant_id, product['id'])).fetchone()
            if not variant:
                raise ValueError('The variant must belong to the selected product.')
            extra_price = variant['extra_price']
            description += ' / ' + variant['name']
        lines.append({'product_id': product['id'], 'variant_id': variant_id,
                      'quantity': number(form.get(f'quantity_{index}'), 'Quantity', 1, 10000),
                      'description': description, 'unit_price': product['sales_price'] + extra_price,
                      'tax_id': product['tax_id']})
    return lines


def create_subscription(form, customer_id):
    db = get_db()
    template_id = form.get('template_id')
    plan_id = form.get('plan_id')
    valid_days = 14
    lines = read_product_lines(form)
    if template_id:
        template = db.execute('SELECT * FROM quote_templates WHERE id=?', (template_id,)).fetchone()
        if not template:
            raise ValueError('Choose a valid template.')
        plan_id, valid_days = template['plan_id'], template['valid_days']
        template_form = {}
        rows = db.execute('SELECT * FROM template_lines WHERE template_id=? ORDER BY id', (template_id,)).fetchall()
        for index, row in enumerate(rows):
            template_form[f'product_{index}'] = row['product_id']
            template_form[f'variant_{index}'] = row['variant_id']
            template_form[f'quantity_{index}'] = row['quantity']
        lines = read_product_lines(template_form)
    plan = db.execute('SELECT * FROM plans WHERE id=?', (plan_id,)).fetchone()
    if not plan:
        raise ValueError('Choose a plan or quotation template.')
    start, end = date_range(form.get('start_date'), form.get('expiry_date'))
    if not plan['available_from'] <= start <= plan['available_to']:
        raise ValueError('This plan is not available on the selected start date.')
    if sum(line['quantity'] for line in lines) < plan['min_quantity']:
        raise ValueError(f"This plan needs at least {plan['min_quantity']} product units.")
    customer = db.execute("SELECT id FROM users WHERE id=? AND role='customer'", (customer_id,)).fetchone()
    if not customer:
        raise ValueError('Choose a customer account.')
    payment_days = number(form.get('payment_days', 14), 'Payment terms', 0, 365)
    quote_until = (date.today() + timedelta(days=valid_days)).isoformat()
    cursor = db.execute('''INSERT INTO subscriptions(customer_id,plan_id,start_date,expiry_date,payment_days,
        quote_until,next_billing,billing_anchor,plan_price,plan_name,interval) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (customer_id, plan['id'], start, end, payment_days, quote_until, start, start,
         plan['price'], plan['name'], plan['interval']))
    subscription_id = cursor.lastrowid
    for line in lines:
        db.execute('''INSERT INTO subscription_lines(subscription_id,product_id,description,quantity,unit_price,tax_id)
            VALUES (?,?,?,?,?,?)''', (subscription_id, line['product_id'], line['description'],
                                    line['quantity'], line['unit_price'], line['tax_id']))
    log_event(f'Created subscription SUB-{subscription_id:04d}.')
    return subscription_id


@subscriptions.get('/subscriptions')
@require_login
def list_subscriptions():
    db = get_db()
    conditions, values = ['1=1'], []
    if g.user['role'] == 'customer':
        conditions.append('s.customer_id=?')
        values.append(g.user['id'])
    status = request.args.get('status', '')
    query = request.args.get('q', '').strip()[:100]
    if status:
        conditions.append('s.status=?')
        values.append(status)
    if query:
        conditions.append('(u.name LIKE ? OR s.plan_name LIKE ? OR CAST(s.id AS TEXT)=?)')
        values.extend([f'%{query}%', f'%{query}%', query.removeprefix('SUB-').lstrip('0')])
    where = ' AND '.join(conditions)
    page = page_number(request.args.get('page'))
    total = db.execute(f'SELECT COUNT(*) FROM subscriptions s JOIN users u ON u.id=s.customer_id WHERE {where}', values).fetchone()[0]
    rows = db.execute(f'''SELECT s.*,u.name AS customer_name FROM subscriptions s JOIN users u ON u.id=s.customer_id
        WHERE {where} ORDER BY s.id DESC LIMIT 20 OFFSET ?''', values + [(page-1)*20]).fetchall()
    return render_template('subscriptions.html', title='Subscriptions', rows=rows, total=total, page=page, status=status, query=query)


@subscriptions.route('/subscriptions/new', methods=['GET', 'POST'])
@require_login
def new_subscription():
    db = get_db()
    if request.method == 'POST':
        try:
            customer_id = g.user['id'] if g.user['role'] == 'customer' else request.form.get('customer_id')
            # Customers can request a quotation; staff still approve and activate it.
            subscription_id = create_subscription(request.form, customer_id)
            if g.user['role'] == 'customer':
                db.execute("UPDATE subscriptions SET status='Quotation' WHERE id=?", (subscription_id,))
            db.commit()
            flash('Subscription created. Review the details below.', 'success')
            return redirect(url_for('subscriptions.detail', subscription_id=subscription_id))
        except ValueError as error:
            db.rollback()
            flash(str(error), 'error')
    choices = {}
    for table in ['plans', 'products', 'variants']:
        choices[table] = db.execute(f'SELECT * FROM {table} ORDER BY name').fetchall()
    choices['templates'] = db.execute('SELECT * FROM quote_templates ORDER BY name').fetchall()
    choices['customers'] = db.execute("SELECT id,name,email FROM users WHERE role='customer' ORDER BY name").fetchall() if g.user['role'] != 'customer' else []
    return render_template('subscription_form.html', title='New subscription', choices=choices,
                           next_year=(date.today() + timedelta(days=365)).isoformat())


@subscriptions.get('/subscriptions/<int:subscription_id>')
@require_login
def detail(subscription_id):
    sub = owned_row('subscriptions', subscription_id)
    db = get_db()
    plan = db.execute('SELECT * FROM plans WHERE id=?', (sub['plan_id'],)).fetchone()
    customer = db.execute('SELECT * FROM users WHERE id=?', (sub['customer_id'],)).fetchone()
    lines = db.execute('''SELECT l.*,COALESCE(t.rate,0) AS rate FROM subscription_lines l
        LEFT JOIN taxes t ON t.id=l.tax_id WHERE subscription_id=?''', (subscription_id,)).fetchall()
    bills = db.execute('SELECT * FROM invoices WHERE subscription_id=? ORDER BY id DESC LIMIT 50', (subscription_id,)).fetchall()
    return render_template('subscription_detail.html', title=f'SUB-{subscription_id:04d}', sub=sub, plan=plan,
                           customer=customer, lines=lines, bills=bills)


def change_status(subscription_id, action):
    """Validate each transition on the server, even if someone changes the HTML."""
    db = get_db()
    db.execute('BEGIN IMMEDIATE')
    sub = owned_row('subscriptions', subscription_id)
    plan = db.execute('SELECT * FROM plans WHERE id=?', (sub['plan_id'],)).fetchone()
    status = sub['status']
    team = g.user['role'] in ('admin', 'staff')
    new_status = None
    if action == 'quote' and team and status == 'Draft':
        new_status = 'Quotation'
    elif action == 'confirm' and team and status == 'Quotation':
        if sub['quote_until'] < today():
            raise ValueError('The quotation expired. Create a new quotation with current pricing.')
        new_status = 'Confirmed'
    elif action == 'activate' and team and status == 'Confirmed':
        if sub['expiry_date'] < today():
            raise ValueError('This subscription already expired.')
        new_status = 'Active'
    elif action == 'pause' and status == 'Active' and plan['allow_pause']:
        new_status = 'Paused'
    elif action == 'resume' and status == 'Paused' and plan['allow_pause']:
        if sub['expiry_date'] < today():
            raise ValueError('This subscription expired. Renew it instead.')
        new_status = 'Active'
        anchor = max(today(), sub['next_billing'])
        db.execute('UPDATE subscriptions SET next_billing=?,billing_anchor=?,cycle_number=0 WHERE id=?', (anchor, anchor, subscription_id))
    elif action == 'close' and status in ('Active', 'Paused', 'Confirmed', 'Quotation', 'Draft') and plan['allow_close']:
        new_status = 'Closed'
    if not new_status:
        raise ValueError('This action is not allowed for this plan, role or subscription stage.')
    if action in ('pause', 'close') and status == 'Active' and sub['next_billing'] <= min(today(), sub['expiry_date']):
        raise ValueError('Billing is due. Ask the team to run billing before pausing or closing.')
    db.execute('UPDATE subscriptions SET status=? WHERE id=?', (new_status, subscription_id))
    log_event(f'SUB-{subscription_id:04d}: {status} → {new_status}.')
    db.commit()


@subscriptions.post('/subscriptions/<int:subscription_id>/<action>')
@require_login
def action(subscription_id, action):
    try:
        if action == 'renew':
            new_id = renew_subscription(subscription_id)
            flash('Renewal copied into a new draft for team review.', 'success')
            return redirect(url_for('subscriptions.detail', subscription_id=new_id))
        change_status(subscription_id, action)
        flash('Subscription updated.', 'success')
    except ValueError as error:
        get_db().rollback()
        flash(str(error), 'error')
    return redirect(url_for('subscriptions.detail', subscription_id=subscription_id))


def renew_subscription(subscription_id):
    db = get_db()
    db.execute('BEGIN IMMEDIATE')
    sub = owned_row('subscriptions', subscription_id)
    plan = db.execute('SELECT * FROM plans WHERE id=?', (sub['plan_id'],)).fetchone()
    if not plan['allow_renew'] or sub['status'] not in ('Active', 'Paused', 'Closed'):
        raise ValueError('This subscription cannot be renewed at this stage.')
    if sub['expiry_date'] >= today() and sub['status'] != 'Closed':
        raise ValueError('Renewal is available when the current term ends.')
    existing = db.execute("SELECT id FROM activity WHERE message=?", (f'Renewed SUB-{subscription_id:04d}.',)).fetchone()
    if existing:
        raise ValueError('This term was already renewed. Open the new subscription.')
    if sub['status'] == 'Active' and sub['next_billing'] <= sub['expiry_date']:
        raise ValueError('Run billing for the ended term before renewing.')
    start, end = date_range(request.form.get('start_date'), request.form.get('expiry_date'))
    if start < today() or start <= sub['expiry_date']:
        raise ValueError('The new term must start today or later, after the old term ends.')
    if not plan['available_from'] <= start <= plan['available_to']:
        raise ValueError('The plan is not available for this new term.')
    cursor = db.execute('''INSERT INTO subscriptions(customer_id,plan_id,start_date,expiry_date,payment_days,quote_until,
        next_billing,billing_anchor,plan_price,plan_name,interval) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (sub['customer_id'], sub['plan_id'], start, end, sub['payment_days'],
         (date.today()+timedelta(days=14)).isoformat(), start, start, plan['price'], plan['name'], plan['interval']))
    new_id = cursor.lastrowid
    db.execute('''INSERT INTO subscription_lines(subscription_id,product_id,description,quantity,unit_price,tax_id)
        SELECT ?,product_id,description,quantity,unit_price,tax_id FROM subscription_lines WHERE subscription_id=?''', (new_id, subscription_id))
    db.execute("UPDATE subscriptions SET status='Closed' WHERE id=?", (subscription_id,))
    log_event(f'Renewed SUB-{subscription_id:04d}.')
    db.commit()
    return new_id


@subscriptions.route('/subscriptions/<int:subscription_id>/products', methods=['GET', 'POST'])
@require_login
def edit_products(subscription_id):
    db = get_db()
    sub = owned_row('subscriptions', subscription_id)
    if sub['status'] not in ('Draft', 'Quotation', 'Active', 'Paused'):
        abort(400, 'Product changes are unavailable at this subscription stage.')
    if request.method == 'POST':
        try:
            db.execute('BEGIN IMMEDIATE')
            sub = owned_row('subscriptions', subscription_id)
            if sub['status'] not in ('Draft', 'Quotation', 'Active', 'Paused'):
                raise ValueError('This subscription stage changed. Refresh and try again.')
            if sub['status'] == 'Active' and sub['next_billing'] <= min(today(), sub['expiry_date']):
                raise ValueError('Billing is due. Ask the team to run billing before changing products.')
            plan = db.execute('SELECT * FROM plans WHERE id=?', (sub['plan_id'],)).fetchone()
            lines = read_product_lines(request.form)
            if sum(line['quantity'] for line in lines) < plan['min_quantity']:
                raise ValueError(f"Choose at least {plan['min_quantity']} product units.")
            db.execute('DELETE FROM subscription_lines WHERE subscription_id=?', (subscription_id,))
            for line in lines:
                db.execute('''INSERT INTO subscription_lines(subscription_id,product_id,description,quantity,unit_price,tax_id)
                    VALUES (?,?,?,?,?,?)''', (subscription_id,line['product_id'],line['description'],line['quantity'],line['unit_price'],line['tax_id']))
            log_event(f'Updated product lines on SUB-{subscription_id:04d} for future billing.')
            db.commit()
            flash('Products updated for the next invoice.', 'success')
            return redirect(url_for('subscriptions.detail', subscription_id=subscription_id))
        except ValueError as error:
            db.rollback()
            flash(str(error), 'error')
    choices = {}
    for table in ['products','variants']:
        choices[table] = db.execute(f'SELECT * FROM {table} ORDER BY name').fetchall()
    lines = db.execute('SELECT * FROM subscription_lines WHERE subscription_id=?', (subscription_id,)).fetchall()
    return render_template('subscription_lines.html',title='Update products',sub=sub,choices=choices,lines=lines)
