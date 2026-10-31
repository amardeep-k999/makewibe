import hashlib
import os
import socket


HOST = "127.0.0.1"
PORT = 5000
USER_FILE = "users.txt"
HASH_ITERATIONS = 300_000


def receive_line(connection, maximum=1024):
    data = bytearray()
    while len(data) < maximum:
        byte = connection.recv(1)
        if not byte or byte == b"\n":
            break
        data.extend(byte)
    return data.decode("utf-8").strip()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)


def valid_email(email):
    return "@" in email and " " not in email and "." in email.rsplit("@", 1)[-1]


def find_user(email):
    if not os.path.exists(USER_FILE):
        return None
    with open(USER_FILE, "r", encoding="utf-8") as file:
        for line in file:
            saved_email, saved_salt, saved_hash = line.rstrip("\n").split("|", 2)
            if saved_email.lower() == email.lower():
                return bytes.fromhex(saved_salt), bytes.fromhex(saved_hash)
    return None


def register_user(email, password):
    if not valid_email(email):
        return "Invalid email address"
    if len(password) < 8:
        return "Password must contain at least 8 characters"
    if find_user(email) is not None:
        return "That email is already registered"
    salt = os.urandom(16)
    hashed_password = password_hash(password, salt)
    with open(USER_FILE, "a", encoding="utf-8") as file:
        file.write(f"{email.lower()}|{salt.hex()}|{hashed_password.hex()}\n")
    return "Registration successful"


def login_user(email, password):
    user = find_user(email)
    if user is None:
        return "Login failed"
    salt, saved_hash = user
    return "Login successful" if password_hash(password, salt) == saved_hash else "Login failed"


def handle_client(connection):
    try:
        connection.sendall(b"Choose REGISTER or LOGIN: ")
        action = receive_line(connection).upper()
        connection.sendall(b"Email address: ")
        email = receive_line(connection)
        connection.sendall(b"Password: ")
        password = receive_line(connection)
        if action == "REGISTER":
            result = register_user(email, password)
        elif action == "LOGIN":
            result = login_user(email, password)
        else:
            result = "Unknown action"
        connection.sendall((result + "\n").encode("utf-8"))
    finally:
        connection.close()


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(5)
        print(f"Server listening on {HOST}:{PORT}")
        while True:
            connection, address = server.accept()
            print(f"Connection from {address[0]}:{address[1]}")
            handle_client(connection)


if __name__ == "__main__":
    main()
