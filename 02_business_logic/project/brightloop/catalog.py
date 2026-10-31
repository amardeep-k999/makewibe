"""Admin setup pages. Each save function handles one small kind of record."""
from flask import Blueprint, flash, render_template, request, redirect, url_for, abort
from brightloop.database import get_db
from brightloop.helpers import require_login, require_admin, cents, percentage, number, text, date_range, log_event
from brightloop.auth import add_user

catalog = Blueprint('catalog', __name__)
KINDS = ['products', 'variants', 'plans', 'taxes', 'discounts', 'templates', 'staff']


def optional_id(form, key, table):
    value = form.get(key)
    if not value:
        return None
    value = number(value, key, 1)
    if not get_db().execute(f'SELECT id FROM {table} WHERE id=?', (value,)).fetchone():
        raise ValueError(f'The selected {key} does not exist.')
    return value


def save_product(form):
    kind = form.get('type')
    if kind not in ('Software', 'Service', 'Add-on'):
        raise ValueError('Choose a valid product type.')
    get_db().execute('INSERT INTO products(name,type,sales_price,cost_price,notes,tax_id) VALUES (?,?,?,?,?,?)',
        (text(form.get('name'), 'Name'), kind, cents(form.get('sales_price')), cents(form.get('cost_price')),
         form.get('notes', '')[:2000], optional_id(form, 'tax_id', 'taxes')))


def save_variant(form):
    product = optional_id(form, 'product_id', 'products')
    if not product:
        raise ValueError('Choose a product.')
    get_db().execute('INSERT INTO variants(product_id,name,extra_price) VALUES (?,?,?)',
                     (product, text(form.get('name'), 'Variant name'), cents(form.get('extra_price'))))


def save_plan(form):
    interval = form.get('interval')
    if interval not in ('daily', 'weekly', 'monthly', 'yearly'):
        raise ValueError('Choose a valid billing interval.')
    start, end = date_range(form.get('available_from'), form.get('available_to'))
    get_db().execute('''INSERT INTO plans(name,price,interval,min_quantity,available_from,available_to,
        auto_close,allow_close,allow_pause,allow_renew,tax_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (text(form.get('name'), 'Name'), cents(form.get('price')), interval,
         number(form.get('min_quantity'), 'Minimum quantity', 1, 10000), start, end,
         int('auto_close' in form), int('allow_close' in form), int('allow_pause' in form),
         int('allow_renew' in form), optional_id(form, 'tax_id', 'taxes')))


def save_tax(form):
    get_db().execute('INSERT INTO taxes(name,rate) VALUES (?,?)',
                     (text(form.get('name'), 'Name'), percentage(form.get('rate'))))


def save_discount(form):
    kind = form.get('kind')
    if kind not in ('fixed', 'percent'):
        raise ValueError('Choose fixed or percent.')
    value = percentage(form.get('value')) if kind == 'percent' else cents(form.get('value'))
    if value == 0:
        raise ValueError('Discount must be greater than zero.')
    starts, ends = date_range(form.get('starts'), form.get('ends'))
    get_db().execute('''INSERT INTO discounts(name,kind,value,min_purchase,min_quantity,starts,ends,max_uses,
        product_id,subscription_id) VALUES (?,?,?,?,?,?,?,?,?,?)''',
        (text(form.get('name'), 'Name'), kind, value, cents(form.get('min_purchase')),
         number(form.get('min_quantity'), 'Minimum quantity', 1, 10000), starts, ends,
         number(form.get('max_uses'), 'Usage limit', 1), optional_id(form, 'product_id', 'products'),
         optional_id(form, 'subscription_id', 'subscriptions')))


def save_template(form):
    plan = optional_id(form, 'plan_id', 'plans')
    if not plan:
        raise ValueError('Choose a plan.')
    cursor = get_db().execute('INSERT INTO quote_templates(name,plan_id,valid_days) VALUES (?,?,?)',
        (text(form.get('name'), 'Name'), plan, number(form.get('valid_days'), 'Validity', 1, 365)))
    from brightloop.subscriptions import read_product_lines
    lines = read_product_lines(form)
    if not lines:
        raise ValueError('Add at least one product to this quotation template.')
    for line in lines:
        get_db().execute('INSERT INTO template_lines(template_id,product_id,variant_id,quantity) VALUES (?,?,?,?)',
            (cursor.lastrowid, line['product_id'], line['variant_id'], line['quantity']))


@catalog.route('/catalog/<kind>', methods=['GET', 'POST'])
@require_login
def manage(kind):
    require_admin()
    if kind not in KINDS:
        abort(404)
    if request.method == 'POST':
        try:
            if kind == 'products':
                save_product(request.form)
            elif kind == 'variants':
                save_variant(request.form)
            elif kind == 'plans':
                save_plan(request.form)
            elif kind == 'taxes':
                save_tax(request.form)
            elif kind == 'discounts':
                save_discount(request.form)
            elif kind == 'templates':
                save_template(request.form)
            elif kind == 'staff':
                add_user(request.form.get('name'), request.form.get('email', ''), request.form.get('password', ''), role='staff')
            log_event(f'Added a record to {kind}.')
            get_db().commit()
            flash('Saved successfully.', 'success')
            return redirect(url_for('catalog.manage', kind=kind))
        except ValueError as error:
            get_db().rollback()
            flash(str(error), 'error')
    db = get_db()
    table = 'quote_templates' if kind == 'templates' else kind
    if kind == 'staff':
        rows = db.execute("SELECT id,name,email,role FROM users WHERE role IN ('admin','staff') ORDER BY id DESC").fetchall()
    else:
        rows = db.execute(f'SELECT * FROM {table} ORDER BY id DESC LIMIT 100').fetchall()
    choices = {}
    for name in ['products', 'plans', 'taxes', 'variants', 'subscriptions']:
        choices[name] = db.execute(f'SELECT * FROM {name} ORDER BY id DESC LIMIT 500').fetchall()
    return render_template('catalog.html', title=kind.title(), kind=kind, rows=rows, choices=choices, kinds=KINDS)
