"""Create the first admin in a fresh database, without loading demo accounts."""
from getpass import getpass
from app import create_app
from brightloop.auth import add_user
from brightloop.database import get_db


def main():
    app=create_app()
    with app.app_context():
        if get_db().execute("SELECT id FROM users WHERE role='admin'").fetchone():
            print('An administrator already exists. Sign in with that account.')
            return
        name=input('Admin name: ')
        email=input('Admin email: ')
        password=getpass('Password (9+ characters, uppercase, lowercase, special character): ')
        confirmation=getpass('Repeat password: ')
        if password!=confirmation:
            print('Passwords did not match. No account created.')
            return
        try:
            add_user(name,email,password,role='admin')
            get_db().commit()
            print('Admin created. Start the server with python app.py.')
        except ValueError as error:
            get_db().rollback()
            print(error)


if __name__=='__main__':
    main()
