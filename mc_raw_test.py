import socket

IP = "192.168.3.254"
PORT = 1027

# frame สำหรับ read D0, 1 word (ตาม class ด้านบน)
frame = "01FF000A4420000000000001"

print("TX:", frame)

with socket.create_connection((IP, PORT), timeout=2) as s:
    s.sendall(frame.encode("ascii"))
    rx = s.recv(4096)
    print("RX raw:", rx)
    print("RX ascii:", rx.decode("ascii", errors="ignore"))
