"""Run manually: python tests/benchmark.py. Uses a disposable, temporary database."""
import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from brightloop.database import get_db
from brightloop.seed import seed_demo


def benchmark():
    with tempfile.TemporaryDirectory() as folder:
        app=create_app({'TESTING':True,'DATABASE':str(Path(folder)/'scale.sqlite')})
        with app.app_context():
            seed_demo()
            db=get_db()
            for index in range(5000):
                cursor=db.execute('''INSERT INTO subscriptions(customer_id,plan_id,status,start_date,expiry_date,
                    payment_days,quote_until,next_billing,billing_anchor,plan_price,plan_name,interval)
                    SELECT customer_id,plan_id,status,start_date,expiry_date,payment_days,quote_until,
                    next_billing,billing_anchor,plan_price,plan_name,interval FROM subscriptions WHERE id=1''')
                sub_id=cursor.lastrowid
                db.execute('''INSERT INTO subscription_lines(subscription_id,product_id,description,quantity,unit_price,tax_id)
                    VALUES (?,1,'Benchmark seats',3,49000,1)''',(sub_id,))
                db.execute('''INSERT INTO invoices(subscription_id,customer_id,customer_name,customer_email,customer_address,
                    billing_date,due_date,status,subtotal,discount,tax,total)
                    VALUES (?,3,'Benchmark customer','bench@example.test','Test only','2026-10-01','2026-10-15','Confirmed',147000,0,26460,173460)''',(sub_id,))
            db.commit()
            counts={table:db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ['subscriptions','invoices']}
        client=app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1,version=1,csrf='benchmark')
        results={}
        for path in ['/','/subscriptions','/invoices','/reports']:
            samples=[]
            for repeat in range(5):
                start=perf_counter()
                response=client.get(path)
                samples.append(round((perf_counter()-start)*1000,2))
                assert response.status_code==200
            results[path]={'maximum_ms':max(samples),'average_ms':round(sum(samples)/len(samples),2)}
        print(json.dumps({'records':counts,'server_render_timings':results},indent=2))


if __name__=='__main__':
    benchmark()
