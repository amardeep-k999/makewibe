import socket


SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000


def receive_until_prompt(connection, prompt):
    data = bytearray()
    while not data.endswith(prompt):
        byte = connection.recv(1)
        if not byte:
            break
        data.extend(byte)
    return bytes(data)


def main():
    print("1. Sign in")
    print("2. Log in")
    action = {"1": "REGISTER", "2": "LOGIN"}.get(input("Choose an option: ").strip())
    if action is None:
        print("Invalid option")
        return
    email = input("Email address: ").strip()
    password = input("Password: ")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect((SERVER_HOST, SERVER_PORT))
        receive_until_prompt(client, b"Choose REGISTER or LOGIN: ")
        client.sendall((action + "\n").encode("utf-8"))
        receive_until_prompt(client, b"Email address: ")
        client.sendall((email + "\n").encode("utf-8"))
        receive_until_prompt(client, b"Password: ")
        client.sendall((password + "\n").encode("utf-8"))
        print(client.recv(1024).decode("utf-8").strip())


if __name__ == "__main__":
    try:
        main()
    except ConnectionRefusedError:
        print("Could not connect. Start the server first.")
