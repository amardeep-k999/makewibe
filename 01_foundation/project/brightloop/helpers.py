"""Reusable validation, permission checks, dates and money formatting."""
import calendar
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from flask import g, abort, redirect, url_for
from brightloop.database import get_db


def today():
    return date.today().isoformat()


def money(paise):
    return f'₹{paise / 100:,.2f}'


def number(value, label, minimum=0, maximum=1_000_000):
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label} must be a whole number.')
    if not minimum <= result <= maximum:
        raise ValueError(f'{label} must be between {minimum} and {maximum}.')
    return result


def cents(value, label='Amount'):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > 100_000_000:
            raise ValueError()
        if amount != amount.quantize(Decimal('0.01')):
            raise ValueError()
        return int(amount * 100)
    except (ValueError, InvalidOperation):
        raise ValueError(f'{label} must be a positive amount (or zero), with at most two decimals.')


def percentage(value):
    result = cents(value, 'Percentage')
    if result > 10000:
        raise ValueError('Percentage cannot exceed 100.')
    return result


def round_ratio(value, numerator, denominator):
    return int((Decimal(value) * numerator / denominator).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def text(value, label, limit=200):
    value = str(value or '').strip()
    if not value or len(value) > limit:
        raise ValueError(f'{label} is required and must be at most {limit} characters.')
    return value


def valid_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError('Enter a valid date.')


def date_range(start, end):
    start, end = valid_date(start), valid_date(end)
    if end < start:
        raise ValueError('The end date must be on or after the start date.')
    return start, end


def cycle_date(anchor, interval, cycle):
    """Always count from the original date, so Jan 31 -> Feb 28 -> Mar 31."""
    start = date.fromisoformat(anchor)
    if interval == 'daily':
        return (start + timedelta(days=cycle)).isoformat()
    if interval == 'weekly':
        return (start + timedelta(weeks=cycle)).isoformat()
    months = cycle if interval == 'monthly' else cycle * 12
    month_index = start.year * 12 + start.month - 1 + months
    year, month = divmod(month_index, 12)
    month += 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def require_login(function):
    @wraps(function)
    def checked(*args, **kwargs):
        if not g.user:
            return redirect(url_for('auth.login'))
        return function(*args, **kwargs)
    return checked


def require_team():
    if g.user['role'] not in ('admin', 'staff'):
        abort(403)


def require_admin():
    if g.user['role'] != 'admin':
        abort(403)


def owned_row(table, row_id):
    # Callers use fixed table names; user input is only passed as a SQL parameter.
    if table not in ('subscriptions', 'invoices'):
        raise ValueError('Unsupported table.')
    row = get_db().execute(f'SELECT * FROM {table} WHERE id = ?', (row_id,)).fetchone()
    if row is None:
        abort(404)
    if g.user['role'] == 'customer' and row['customer_id'] != g.user['id']:
        abort(404)
    return row


def log_event(message):
    user_id = g.user['id'] if getattr(g, 'user', None) else None
    get_db().execute('INSERT INTO activity(user_id, message) VALUES (?, ?)', (user_id, message))


def page_number(value):
    try:
        return min(1_000_000, max(1, int(value or 1)))
    except ValueError:
        return 1
