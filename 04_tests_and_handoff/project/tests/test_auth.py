import re
from email import policy
from email.parser import BytesParser
from pathlib import Path
import pytest
from werkzeug.security import check_password_hash
from brightloop.database import get_db
from brightloop.auth import validate_password
from conftest import login_as, post


@pytest.mark.parametrize('password', ['Short!A','alllowercase!','ALLUPPERCASE!','NoSpecial123','NoSpace Only'])
def test_password_rules(password):
    with pytest.raises(ValueError):
        validate_password(password)


def test_signup_duplicate_email_and_hash(app, client):
    login_as(client)
    response = post(client,'/signup',name='New customer',email='New@Example.com',password='Beginner!123')
    assert b'Your account is ready' in response.data
    with app.app_context():
        user=get_db().execute("SELECT * FROM users WHERE email='new@example.com'").fetchone()
        assert user['role']=='customer'
        assert user['password_hash']!='Beginner!123'
        assert check_password_hash(user['password_hash'],'Beginner!123')
    response=post(client,'/signup',name='Duplicate',email='NEW@example.com',password='Beginner!123')
    assert b'already has an account' in response.data


def test_login_and_logout(client):
    client.get('/login')
    with client.session_transaction() as session:
        token=session['csrf']
    response=client.post('/login',data={'csrf':token,'email':'admin@brightloop.demo','password':'Brightloop!2026'},follow_redirects=True)
    assert b'A clear view' in response.data
    with client.session_transaction() as session:
        token=session['csrf']
    client.post('/logout',data={'csrf':token})
    assert client.get('/').status_code==302


def test_csrf_required(client):
    login_as(client)
    assert client.post('/billing/run').status_code==400


def test_role_and_owner_checks(client):
    login_as(client,3)
    assert client.get('/catalog/products').status_code==403
    assert post(client,'/catalog/staff',name='Hacker').status_code==403
    assert client.get('/reports').status_code==403
    assert client.get('/subscriptions/2').status_code==404
    assert post(client,'/subscriptions/2/close').status_code==404
    assert post(client,'/billing/run').status_code==403
    assert b'Noah Patel' not in client.get('/subscriptions').data
    login_as(client,2)
    assert client.get('/catalog/staff').status_code==403
    assert client.get('/invoices').status_code==200


def test_reset_link_is_one_use_and_invalidates_sessions(app,client):
    login_as(client)
    post(client,'/forgot-password',email='customer@brightloop.demo')
    mail=list((Path(app.instance_path)/'outbox').glob('*.eml'))
    assert len(mail)==1
    content=BytesParser(policy=policy.default).parsebytes(mail[0].read_bytes()).get_content()
    path=re.search(r'http://127\.0\.0\.1:5055(/reset-password/[^\s]+)',content).group(1)
    response=post(client,path,password='Changed!123')
    assert b'Password changed' in response.data
    client.get('/login')
    with client.session_transaction() as session:
        token=session['csrf']
    response=client.post(path,data={'csrf':token,'password':'AgainPass!123'},follow_redirects=True)
    assert b'expired or was already used' in response.data
    login_as(client,3)  # This represents an old session carrying version 1.
    assert client.get('/').status_code==302


def test_login_rate_limit(client):
    login_as(client)
    for attempt in range(6):
        response=post(client,'/login',email='wrong@example.test',password='wrong')
    assert b'Too many attempts' in response.data


def test_only_admin_creates_staff(app,client):
    login_as(client)
    response=post(client,'/catalog/staff',name='New Staff',email='staff2@example.test',password='StaffPass!123')
    assert b'Saved successfully' in response.data
    with app.app_context():
        assert get_db().execute("SELECT role FROM users WHERE email='staff2@example.test'").fetchone()[0]=='staff'
