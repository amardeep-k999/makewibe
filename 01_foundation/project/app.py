"""Start here: create the app, connect its pages, and start the web server."""
import os
import secrets
from pathlib import Path

from flask import Flask, g, render_template, request, session, abort
from werkzeug.exceptions import HTTPException

from brightloop import database, helpers


def create_app(test_config=None):
    app = Flask(__name__)
    app.instance_path = os.environ.get('BRIGHTLOOP_INSTANCE', app.instance_path)
    folder = Path(app.instance_path)
    folder.mkdir(parents=True, exist_ok=True)
    # Keeping this key on disk means a server restart does not log everyone out.
    key_file = folder / 'secret.key'
    if not key_file.exists():
        try:
            with key_file.open('x') as stream:
                stream.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY') or key_file.read_text().strip(),
        DATABASE=str(folder / 'brightloop.sqlite'),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('HTTPS_ONLY') == '1',
        MAX_CONTENT_LENGTH=1_000_000,
        PUBLIC_URL=os.environ.get('PUBLIC_URL', 'http://127.0.0.1:5055'),
        MAIL_MODE=os.environ.get('MAIL_MODE', 'outbox'),
    )
    if test_config:
        app.config.update(test_config)
    app.teardown_appcontext(database.close_db)
    with app.app_context():
        database.init_db()

    from brightloop.auth import auth
    from brightloop.catalog import catalog
    from brightloop.subscriptions import subscriptions
    from brightloop.invoices import invoices
    from brightloop.reports import reports
    for pages in [auth, catalog, subscriptions, invoices, reports]:
        app.register_blueprint(pages)

    @app.before_request
    def prepare_request():
        g.user = None
        if session.get('user_id'):
            g.user = database.get_db().execute(
                'SELECT * FROM users WHERE id = ?', (session['user_id'],)
            ).fetchone()
            if g.user and g.user['session_version'] != session.get('version'):
                session.clear()
                g.user = None
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(24)
        if request.method == 'POST':
            token = request.form.get('csrf', '')
            if not secrets.compare_digest(token, session['csrf']):
                abort(400, 'This form expired. Refresh the page and try again.')

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def common_template_values():
        return {'today': helpers.today(), 'money': helpers.money,
                'csrf_token': session.get('csrf', '')}

    app.jinja_env.filters['money'] = helpers.money

    @app.errorhandler(HTTPException)
    def show_error(error):
        return render_template('error.html', title=str(error.code), message=error.description), error.code

    @app.cli.command('seed')
    def seed_command():
        from brightloop.seed import seed_demo
        seed_demo()

    @app.cli.command('bill')
    def bill_command():
        from brightloop.billing import run_billing
        print(run_billing())

    return app


if __name__ == '__main__':
    from waitress import serve
    print('Brightloop is running at http://127.0.0.1:5055', flush=True)
    serve(create_app(), host='127.0.0.1', port=5055)
