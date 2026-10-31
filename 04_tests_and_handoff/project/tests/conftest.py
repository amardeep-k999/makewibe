"""Every test gets its own temporary database, never your real demo data."""
import shutil
import pytest
from app import create_app
from brightloop.seed import seed_demo


@pytest.fixture(scope='session')
def demo_database(tmp_path_factory):
    folder = tmp_path_factory.mktemp('demo')
    app = create_app({'TESTING': True, 'DATABASE': str(folder/'seed.sqlite')})
    with app.app_context():
        seed_demo()
    return folder/'seed.sqlite'


@pytest.fixture
def app(tmp_path, demo_database):
    database = tmp_path/'test.sqlite'
    shutil.copyfile(demo_database, database)
    app = create_app({'TESTING':True, 'DATABASE':str(database), 'MAIL_MODE':'outbox', 'SECRET_KEY':'test-only-secret'})
    app.instance_path = str(tmp_path)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def login_as(client, user_id=1):
    with client.session_transaction() as session:
        session.update(user_id=user_id,version=1,csrf='test-csrf')


def post(client, url, **fields):
    return client.post(url, data={'csrf':'test-csrf', **fields}, follow_redirects=True)
