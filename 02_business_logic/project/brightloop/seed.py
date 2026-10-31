"""Optional, repeat-safe sample data for a convincing offline demonstration."""
from datetime import date, timedelta
from werkzeug.security import generate_password_hash
from brightloop.database import get_db
from brightloop.helpers import cycle_date, today
from brightloop.billing import run_billing


def seed_demo():
    db = get_db()
    if db.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
        print('Database already has accounts; demo seeding skipped to protect existing data.')
        return
    password = generate_password_hash('Brightloop!2026')
    users = [('Alex Morgan', 'admin@brightloop.demo', 'admin'), ('Sam Lee', 'staff@brightloop.demo', 'staff'),
             ('Amelia Harper', 'customer@brightloop.demo', 'customer'), ('Noah Patel', 'noah@example.test', 'customer'),
             ('Olivia Chen', 'olivia@example.test', 'customer'), ('Liam Wilson', 'liam@example.test', 'customer'),
             ('Emma Davis', 'emma@example.test', 'customer'), ('Ethan Shah', 'ethan@example.test', 'customer')]
    for name, email, role in users:
        db.execute('INSERT INTO users(name,email,password_hash,role,address) VALUES (?,?,?,?,?)', (name,email,password,role,'Brightloop demo customer'))
    db.execute("INSERT INTO taxes(name,rate) VALUES ('Sample tax · 18%',1800)")
    for name, price, cost, kind in [('Workspace seats', 49000, 12000, 'Software'), ('Analytics', 79000, 20000, 'Add-on'), ('Priority support', 99000, 30000, 'Service')]:
        db.execute('INSERT INTO products(name,type,sales_price,cost_price,notes,tax_id) VALUES (?,?,?,?,?,1)', (name,kind,price,cost,'Sample catalog item'))
    db.execute("INSERT INTO variants(product_id,name,extra_price) VALUES (1,'Odoo brand',56000)")
    for name, price, interval in [('Starter', 49900, 'monthly'), ('Growth', 149900, 'monthly'), ('Business annual', 1199900, 'yearly')]:
        db.execute('''INSERT INTO plans(name,price,interval,min_quantity,available_from,available_to,tax_id)
            VALUES (?,?,?,1,?,?,1)''', (name,price,interval,cycle_date(today(),'yearly',-2),cycle_date(today(),'yearly',3)))
    db.execute("INSERT INTO quote_templates(name,plan_id,valid_days) VALUES ('Small business launch',2,30)")
    db.execute('INSERT INTO template_lines(template_id,product_id,quantity) VALUES (1,1,5)')
    db.execute('INSERT INTO template_lines(template_id,product_id,quantity) VALUES (1,2,1)')
    starts = cycle_date(today(), 'monthly', -5)
    db.execute('''INSERT INTO discounts(name,kind,value,min_purchase,min_quantity,starts,ends,max_uses)
        VALUES ('Team welcome','percent',1000,100000,3,?,?,12)''', (starts,cycle_date(today(),'yearly',1)))
    for offset in range(6):
        customer = offset+3
        plan_id = offset % 2 + 1
        plan = db.execute('SELECT * FROM plans WHERE id=?', (plan_id,)).fetchone()
        anchor = date.fromisoformat(starts).replace(day=5+offset*3).isoformat()
        cursor = db.execute('''INSERT INTO subscriptions(customer_id,plan_id,status,start_date,expiry_date,payment_days,
            quote_until,next_billing,billing_anchor,plan_price,plan_name,interval) VALUES (?,?,'Active',?,?,14,?,?,?,?,?,'monthly')''',
            (customer,plan_id,anchor,cycle_date(today(),'yearly',1),today(),anchor,anchor,plan['price'],plan['name']))
        db.execute('''INSERT INTO subscription_lines(subscription_id,product_id,description,quantity,unit_price,tax_id)
            VALUES (?,1,'Workspace seats',?,49000,1)''', (cursor.lastrowid,offset+2))
    db.commit()
    run_billing()
    invoices = db.execute('SELECT * FROM invoices ORDER BY id').fetchall()
    for invoice in invoices:
        db.execute("UPDATE invoices SET status='Confirmed' WHERE id=?", (invoice['id'],))
        if invoice['billing_date'] < (date.today()-timedelta(days=20)).isoformat() or invoice['id'] % 3 == 0:
            db.execute('''INSERT INTO payments(invoice_id,amount,method,payment_date,note,request_key) VALUES (?,?,?,?,?,?)''',
                       (invoice['id'],invoice['total'],'Bank transfer',invoice['billing_date'],'Sample payment',f"seed-{invoice['id']}"))
            db.execute("UPDATE invoices SET status='Paid' WHERE id=?", (invoice['id'],))
    db.execute("INSERT INTO activity(message) VALUES ('Demo workspace is ready. Explore a complete billing cycle.')")
    db.commit()
    print('Demo data created. Login: admin@brightloop.demo / Brightloop!2026')
