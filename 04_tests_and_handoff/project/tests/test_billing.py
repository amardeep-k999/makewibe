from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
import pytest
from flask import g
from brightloop.database import get_db
from brightloop.helpers import cycle_date,today,cents
from brightloop.subscriptions import create_subscription
from brightloop.billing import run_billing
from conftest import login_as,post


def make_subscription(app, **changes):
    with app.app_context():
        g.user=get_db().execute('SELECT * FROM users WHERE id=1').fetchone()
        form={'plan_id':'1','start_date':today(),'expiry_date':cycle_date(today(),'yearly',1),
              'payment_days':'14','product_0':'1','quantity_0':'3'}
        form.update(changes)
        sub_id=create_subscription(form,3)
        get_db().execute("UPDATE subscriptions SET status='Active' WHERE id=?",(sub_id,))
        get_db().commit()
        return sub_id


@pytest.mark.parametrize('anchor,interval,cycle,expected',[
    ('2025-01-31','monthly',1,'2025-02-28'),('2025-01-31','monthly',2,'2025-03-31'),
    ('2024-02-29','yearly',1,'2025-02-28'),('2024-02-29','yearly',4,'2028-02-29'),
    ('2026-10-31','daily',1,'2026-11-01'),('2026-10-31','weekly',1,'2026-11-07')])
def test_calendar(anchor,interval,cycle,expected):
    assert cycle_date(anchor,interval,cycle)==expected


@pytest.mark.parametrize('value',['NaN','Infinity','-1','12.345'])
def test_invalid_money(value):
    with pytest.raises(ValueError): cents(value)


def test_billing_is_idempotent_and_snapshots_prices(app):
    sub=make_subscription(app)
    with app.app_context():
        assert run_billing()==1
        assert run_billing()==0
        invoice=dict(get_db().execute('SELECT * FROM invoices WHERE subscription_id=?',(sub,)).fetchone())
        assert invoice['subtotal']==49900+49000*3
        get_db().execute('UPDATE products SET sales_price=999999 WHERE id=1')
        get_db().commit()
        assert get_db().execute('SELECT total FROM invoices WHERE id=?',(invoice['id'],)).fetchone()[0]==invoice['total']


def test_parallel_billing_does_not_double_bill(app):
    sub=make_subscription(app)
    def run():
        with app.app_context(): return run_billing()
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=list(workers.map(lambda _:run(),range(2)))
    assert sum(results)==1
    with app.app_context():
        assert get_db().execute('SELECT COUNT(*) FROM invoices WHERE subscription_id=?',(sub,)).fetchone()[0]==1


def test_discount_expiry_quantity_limit_and_tax(app):
    sub=make_subscription(app)
    with app.app_context():
        db=get_db()
        db.execute('DELETE FROM discounts')
        for name,quantity,starts,ends,uses in [('valid',1,today(),today(),1),('expired',1,'2000-01-01','2001-01-01',5),('too many seats',99,today(),today(),5)]:
            db.execute('INSERT INTO discounts(name,kind,value,min_quantity,starts,ends,max_uses) VALUES (?,\'percent\',1000,?,?,?,?)',(name,quantity,starts,ends,uses))
        db.commit()
        run_billing()
        bill=db.execute('SELECT * FROM invoices WHERE subscription_id=?',(sub,)).fetchone()
        assert bill['discount_name']=='valid'
        assert bill['discount']==19690
        assert bill['tax']==31898  # Round each discounted line to paise.
        assert bill['total']==209108
        assert db.execute("SELECT uses FROM discounts WHERE name='valid'").fetchone()[0]==1
    other=make_subscription(app)
    with app.app_context():
        run_billing()
        assert get_db().execute('SELECT discount FROM invoices WHERE subscription_id=?',(other,)).fetchone()[0]==0


def test_fixed_product_discount_is_capped(app):
    sub=make_subscription(app,quantity_0='1')
    with app.app_context():
        db=get_db();db.execute('DELETE FROM discounts')
        db.execute("INSERT INTO discounts(name,kind,value,starts,ends,max_uses,product_id) VALUES ('Free seats','fixed',999999,?,?,1,1)",(today(),today()))
        db.commit();run_billing()
        bill=db.execute('SELECT * FROM invoices WHERE subscription_id=?',(sub,)).fetchone()
        assert bill['discount']==49000
        assert bill['total']==58882


def test_catchup_and_auto_close_preserve_all_periods(app):
    start=(date.today()-timedelta(days=3)).isoformat()
    end=(date.today()-timedelta(days=1)).isoformat()
    sub=make_subscription(app,start_date=start,expiry_date=end)
    with app.app_context():
        db=get_db();db.execute("UPDATE subscriptions SET interval='daily' WHERE id=?",(sub,));db.commit()
        assert run_billing(limit=1)==1
        assert db.execute('SELECT status FROM subscriptions WHERE id=?',(sub,)).fetchone()[0]=='Active'
        assert run_billing()==2
        assert db.execute('SELECT status FROM subscriptions WHERE id=?',(sub,)).fetchone()[0]=='Closed'
        assert db.execute('SELECT COUNT(*) FROM invoices WHERE subscription_id=?',(sub,)).fetchone()[0]==3


def test_partial_payment_overpayment_and_replay(app,client):
    sub=make_subscription(app)
    with app.app_context():
        run_billing()
        bill=get_db().execute('SELECT * FROM invoices WHERE subscription_id=?',(sub,)).fetchone()
        invoice_id,total=bill['id'],bill['total']
    login_as(client)
    post(client,f'/invoices/{invoice_id}/confirm')
    fields={'amount':'100.00','method':'UPI','payment_date':today(),'request_key':'unique-key-first-payment'}
    assert b'Payment recorded' in post(client,f'/invoices/{invoice_id}/payment',**fields).data
    assert b'already recorded' in post(client,f'/invoices/{invoice_id}/payment',**fields).data
    assert b'exceeds' in post(client,f'/invoices/{invoice_id}/payment',**{**fields,'amount':str(total),'request_key':'unique-key-overpayment'}).data
    remaining=f'{(total-10000)/100:.2f}'
    post(client,f'/invoices/{invoice_id}/payment',**{**fields,'amount':remaining,'request_key':'unique-key-final-payment'})
    with app.app_context():
        assert get_db().execute('SELECT status FROM invoices WHERE id=?',(invoice_id,)).fetchone()[0]=='Paid'
        assert get_db().execute('SELECT COUNT(*) FROM payments WHERE invoice_id=?',(invoice_id,)).fetchone()[0]==2
    assert b'cannot be cancelled' in post(client,f'/invoices/{invoice_id}/cancel').data


def test_pause_requires_due_billing_then_resumes(app,client):
    sub=make_subscription(app)
    login_as(client,3)
    assert b'Billing is due' in post(client,f'/subscriptions/{sub}/pause').data
    with app.app_context(): run_billing()
    post(client,f'/subscriptions/{sub}/pause')
    with app.app_context():
        assert get_db().execute('SELECT status FROM subscriptions WHERE id=?',(sub,)).fetchone()[0]=='Paused'
        assert run_billing()==0
    post(client,f'/subscriptions/{sub}/resume')
    with app.app_context():
        assert get_db().execute('SELECT status FROM subscriptions WHERE id=?',(sub,)).fetchone()[0]=='Active'


def test_template_and_variant(app,client):
    sub=make_subscription(app,template_id='1')
    with app.app_context():
        db=get_db()
        assert db.execute('SELECT plan_id FROM subscriptions WHERE id=?',(sub,)).fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM subscription_lines WHERE subscription_id=?',(sub,)).fetchone()[0]==2
    variant_sub=make_subscription(app,variant_0='1')
    with app.app_context():
        assert get_db().execute('SELECT unit_price FROM subscription_lines WHERE subscription_id=?',(variant_sub,)).fetchone()[0]==105000


def test_customer_cannot_activate_quote(app,client):
    login_as(client,3)
    response=post(client,'/subscriptions/new',plan_id='1',start_date=today(),expiry_date=cycle_date(today(),'yearly',1),product_0='1',quantity_0='1')
    assert b'Subscription created' in response.data
    with app.app_context():
        sub=get_db().execute('SELECT * FROM subscriptions ORDER BY id DESC LIMIT 1').fetchone()
        assert sub['status']=='Quotation'
    assert b'not allowed' in post(client,f"/subscriptions/{sub['id']}/confirm").data


def test_addon_update_preserves_existing_invoice(app,client):
    sub=make_subscription(app)
    with app.app_context():
        run_billing()
        old_total=get_db().execute('SELECT total FROM invoices WHERE subscription_id=?',(sub,)).fetchone()[0]
    login_as(client,3)
    response=post(client,f'/subscriptions/{sub}/products',product_0='1',quantity_0='3',product_1='2',quantity_1='1')
    assert b'Products updated' in response.data
    with app.app_context():
        assert get_db().execute('SELECT COUNT(*) FROM subscription_lines WHERE subscription_id=?',(sub,)).fetchone()[0]==2
        assert get_db().execute('SELECT total FROM invoices WHERE subscription_id=?',(sub,)).fetchone()[0]==old_total
