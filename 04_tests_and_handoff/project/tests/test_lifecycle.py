from datetime import date,timedelta
from brightloop.database import get_db
from brightloop.helpers import today,cycle_date
from brightloop.billing import run_billing
from conftest import login_as,post
from test_billing import make_subscription


def test_draft_quote_confirm_activate_flow(app,client):
    login_as(client)
    post(client,'/subscriptions/new',customer_id='3',plan_id='1',start_date=today(),expiry_date=cycle_date(today(),'yearly',1),product_0='1',quantity_0='1')
    with app.app_context():
        sub_id=get_db().execute('SELECT MAX(id) FROM subscriptions').fetchone()[0]
    for action,expected in [('quote','Quotation'),('confirm','Confirmed'),('activate','Active')]:
        post(client,f'/subscriptions/{sub_id}/{action}')
        with app.app_context():
            assert get_db().execute('SELECT status FROM subscriptions WHERE id=?',(sub_id,)).fetchone()[0]==expected


def test_expired_quote_cannot_confirm(app,client):
    sub=make_subscription(app)
    with app.app_context():
        db=get_db();db.execute("UPDATE subscriptions SET status='Quotation',quote_until='2001-01-01' WHERE id=?",(sub,));db.commit()
    login_as(client)
    assert b'quotation expired' in post(client,f'/subscriptions/{sub}/confirm').data


def test_plan_controls_cannot_be_bypassed(app,client):
    sub=make_subscription(app)
    with app.app_context():
        db=get_db();db.execute('UPDATE plans SET allow_pause=0,allow_close=0 WHERE id=1');db.commit();run_billing()
    login_as(client)
    for action in ['pause','close']:
        assert b'not allowed' in post(client,f'/subscriptions/{sub}/{action}').data


def test_renewal_is_copied_once(app,client):
    yesterday=(date.today()-timedelta(days=1)).isoformat()
    sub=make_subscription(app,start_date=yesterday,expiry_date=yesterday)
    with app.app_context(): run_billing()
    login_as(client,3)
    response=post(client,f'/subscriptions/{sub}/renew',start_date=today(),expiry_date=cycle_date(today(),'yearly',1))
    assert b'Renewal copied' in response.data
    with app.app_context():
        new=get_db().execute('SELECT * FROM subscriptions ORDER BY id DESC LIMIT 1').fetchone()
        assert new['id']!=sub and new['status']=='Draft' and new['customer_id']==3
    assert b'already renewed' in post(client,f'/subscriptions/{sub}/renew',start_date=today(),expiry_date=cycle_date(today(),'yearly',1)).data


def test_min_quantity_and_variant_validation(app,client):
    login_as(client)
    fields={'customer_id':'3','plan_id':'1','start_date':today(),'expiry_date':cycle_date(today(),'yearly',1),'product_0':'2','quantity_0':'1','variant_0':'1'}
    assert b'variant must belong' in post(client,'/subscriptions/new',**fields).data
    with app.app_context():
        db=get_db();db.execute('UPDATE plans SET min_quantity=10 WHERE id=1');db.commit()
    fields['variant_0']=''
    assert b'at least 10' in post(client,'/subscriptions/new',**fields).data


def test_cancelled_invoice_never_recreated(app,client):
    sub=make_subscription(app)
    with app.app_context():
        run_billing()
        invoice=get_db().execute('SELECT id FROM invoices WHERE subscription_id=?',(sub,)).fetchone()[0]
    login_as(client)
    post(client,f'/invoices/{invoice}/cancel')
    with app.app_context():
        assert run_billing()==0
        assert get_db().execute('SELECT status FROM invoices WHERE id=?',(invoice,)).fetchone()[0]=='Cancelled'


def test_zero_total_invoice_is_paid_on_confirmation(app,client):
    sub=make_subscription(app)
    with app.app_context():
        db=get_db();db.execute('DELETE FROM discounts')
        db.execute("INSERT INTO discounts(name,kind,value,starts,ends,max_uses) VALUES ('Full discount','percent',10000,?,?,1)",(today(),today()))
        db.commit();run_billing()
        invoice=db.execute('SELECT * FROM invoices WHERE subscription_id=?',(sub,)).fetchone()
        assert invoice['total']==0
    login_as(client)
    post(client,f"/invoices/{invoice['id']}/confirm")
    with app.app_context():
        assert get_db().execute('SELECT status FROM invoices WHERE id=?',(invoice['id'],)).fetchone()[0]=='Paid'


def test_discount_and_invoice_roll_back_together(app):
    sub=make_subscription(app)
    with app.app_context():
        db=get_db();db.execute('DELETE FROM discounts')
        db.execute("INSERT INTO discounts(name,kind,value,starts,ends,max_uses) VALUES ('Rollback check','percent',1000,?,?,1)",(today(),today()))
        db.execute("CREATE TRIGGER reject_invoice_line BEFORE INSERT ON invoice_lines BEGIN SELECT RAISE(ABORT,'test failure'); END")
        db.commit()
        import pytest,sqlite3
        with pytest.raises(sqlite3.IntegrityError): run_billing()
        assert db.execute('SELECT COUNT(*) FROM invoices WHERE subscription_id=?',(sub,)).fetchone()[0]==0
        assert db.execute('SELECT uses FROM discounts').fetchone()[0]==0
