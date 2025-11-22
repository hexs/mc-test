import socket

IP = "192.168.3.254"
PORT = 1027  # ตอนนี้คุณใช้ 1027 อยู่

try:
    print(f"Connecting to {IP}:{PORT} ...")
    with socket.create_connection((IP, PORT), timeout=3) as s:
        print("OK: TCP connected")
except OSError as e:
    print("ERROR:", e)
