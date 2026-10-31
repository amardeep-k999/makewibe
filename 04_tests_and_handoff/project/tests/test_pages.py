import pytest
from brightloop.database import get_db
from conftest import login_as,post


@pytest.mark.parametrize('path',['/','/subscriptions','/subscriptions/new','/subscriptions/1','/subscriptions/1/products',
    '/invoices','/invoices/1','/invoices/1?print=1','/reports','/account','/catalog/products','/catalog/variants',
    '/catalog/plans','/catalog/taxes','/catalog/discounts','/catalog/templates','/catalog/staff'])
def test_pages_render(client,path):
    login_as(client)
    response=client.get(path)
    assert response.status_code==200
    assert b'Brightloop' in response.data


def test_filters_empty_results_and_pagination(client):
    login_as(client)
    assert b'No subscriptions found' in client.get('/subscriptions?q=not-a-customer').data
    assert client.get('/invoices?page=2').status_code==200
    assert client.get('/subscriptions?page=nonsense').status_code==200
    assert client.get('/reports?start=wrong&end=wrong').status_code==200


def test_invoice_delivery_writes_outbox(app,client):
    from pathlib import Path
    login_as(client)
    response=post(client,'/invoices/1/send')
    assert b'local demo inbox' in response.data
    files=list((Path(app.instance_path)/'outbox').glob('*.eml'))
    assert len(files)==1
    assert 'INV-0001' in files[0].read_text()


def test_csv_escapes_spreadsheet_formulas(app,client):
    with app.app_context():
        db=get_db();db.execute("UPDATE payments SET note='=BADFORMULA()'");db.commit()
    login_as(client)
    response=client.get('/reports/export.csv?start=2000-01-01&end=2099-12-31')
    assert response.status_code==200
    assert b"'=BADFORMULA()" in response.data


def test_user_input_is_html_escaped(app,client):
    with app.app_context():
        db=get_db();db.execute("UPDATE users SET name='<script>alert(1)</script>' WHERE id=1");db.commit()
    login_as(client)
    response=client.get('/')
    assert b'<script>alert' not in response.data
    assert b'&lt;script&gt;' in response.data
