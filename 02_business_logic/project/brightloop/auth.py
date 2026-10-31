"""Signup, login, logout and one-use password reset links."""
import hashlib
import re
import secrets
import sqlite3
import time
from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from brightloop.database import get_db
from brightloop.helpers import require_login, text
from brightloop.mailer import send_mail

auth = Blueprint('auth', __name__)


def validate_password(password):
    if len(password) < 9 or len(password) > 128:
        raise ValueError('Use 9–128 characters for your password.')
    if not any(c.isupper() for c in password) or not any(c.islower() for c in password):
        raise ValueError('Include an uppercase and a lowercase letter.')
    if not any(not c.isalnum() and not c.isspace() for c in password):
        raise ValueError('Include a special character such as ! or @.')


def validate_email(email):
    email = email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise ValueError('Enter a valid email address.')
    return email


def add_user(name, email, password, role='customer', address=''):
    validate_password(password)
    email = validate_email(email)
    name = text(name, 'Name', 100)
    if len(address) > 1000:
        raise ValueError('Address is too long.')
    try:
        cursor = get_db().execute(
            'INSERT INTO users(name,email,password_hash,role,address) VALUES (?,?,?,?,?)',
            (name, email, generate_password_hash(password), role, address))
    except sqlite3.IntegrityError:
        raise ValueError('That email already has an account.')
    return cursor.lastrowid


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()[:254]
        password = request.form.get('password', '')
        db = get_db()
        attempts = db.execute('SELECT * FROM auth_attempts WHERE email=?', (email,)).fetchone()
        now = int(time.time())
        blocked = attempts and attempts['window_start'] > now - 900 and attempts['attempts'] >= 5
        user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if blocked:
            flash('Too many attempts. Try again in 15 minutes.', 'error')
        elif user and len(password) <= 128 and check_password_hash(user['password_hash'], password):
            db.execute('DELETE FROM auth_attempts WHERE email=?', (email,))
            db.commit()
            session.clear()
            session.update(user_id=user['id'], version=user['session_version'], csrf=secrets.token_hex(24))
            return redirect(url_for('reports.dashboard'))
        else:
            if not attempts or attempts['window_start'] <= now - 900:
                db.execute('INSERT OR REPLACE INTO auth_attempts VALUES (?,1,?)', (email, now))
            else:
                db.execute('UPDATE auth_attempts SET attempts=attempts+1 WHERE email=?', (email,))
            db.commit()
            flash('Email or password is incorrect.', 'error')
    return render_template('auth.html', title='Welcome back', mode='login')


@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        try:
            add_user(request.form.get('name'), request.form.get('email', ''),
                     request.form.get('password', ''), address=request.form.get('address', '').strip())
            get_db().commit()
            flash('Your account is ready. Sign in to get started.', 'success')
            return redirect(url_for('auth.login'))
        except ValueError as error:
            get_db().rollback()
            flash(str(error), 'error')
    return render_template('auth.html', title='Create your account', mode='signup')


@auth.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        user = get_db().execute('SELECT * FROM users WHERE email=?',
                                (request.form.get('email', '').strip().lower(),)).fetchone()
        if user:
            previous = get_db().execute('SELECT expires FROM reset_tokens WHERE user_id=? ORDER BY expires DESC LIMIT 1', (user['id'],)).fetchone()
            # Suppress repeat messages for 60 seconds without revealing accounts.
            if not previous or previous['expires'] < int(time.time()) + 1740:
                token = secrets.token_urlsafe(32)
                digest = hashlib.sha256(token.encode()).hexdigest()
                db = get_db()
                db.execute('DELETE FROM reset_tokens WHERE user_id=?', (user['id'],))
                db.execute('INSERT INTO reset_tokens VALUES (?,?,?)', (digest, user['id'], int(time.time()) + 1800))
                db.commit()
                link = current_app.config['PUBLIC_URL'].rstrip('/') + url_for('auth.reset_password', token=token)
                try:
                    send_mail(user['email'], 'Reset your Brightloop password',
                              f'Use this link within 30 minutes:\n{link}\n\nIf you did not request it, ignore this email.')
                except (OSError, ValueError):
                    current_app.logger.error('Password reset email could not be delivered. Check mail configuration.')
        flash('If this account exists, a reset link has been sent. Demo mode saves email in instance/outbox.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth.html', title='Forgot your password?', mode='forgot')


@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    if request.method == 'POST':
        db = get_db()
        try:
            password = request.form.get('password', '')
            validate_password(password)
            db.execute('BEGIN IMMEDIATE')
            reset = db.execute('SELECT * FROM reset_tokens WHERE digest=? AND expires>?', (digest, int(time.time()))).fetchone()
            if not reset:
                raise ValueError('This reset link expired or was already used. Request another.')
            db.execute('UPDATE users SET password_hash=?, session_version=session_version+1 WHERE id=?',
                       (generate_password_hash(password), reset['user_id']))
            db.execute('DELETE FROM reset_tokens WHERE user_id=?', (reset['user_id'],))
            db.commit()
            session.clear()
            flash('Password changed. Sign in with your new password.', 'success')
            return redirect(url_for('auth.login'))
        except ValueError as error:
            db.rollback()
            flash(str(error), 'error')
    return render_template('auth.html', title='Choose a new password', mode='reset')


@auth.route('/account', methods=['GET', 'POST'])
@require_login
def account():
    if request.method == 'POST':
        try:
            name = text(request.form.get('name'), 'Name', 100)
            address = request.form.get('address', '').strip()
            if len(address) > 1000:
                raise ValueError('Address must be under 1,000 characters.')
            get_db().execute('UPDATE users SET name=?, address=? WHERE id=?', (name, address, g.user['id']))
            get_db().commit()
            flash('Account updated. Existing invoice snapshots stay unchanged.', 'success')
            return redirect(url_for('auth.account'))
        except ValueError as error:
            flash(str(error), 'error')
    return render_template('account.html', title='Your account')
