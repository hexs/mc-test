# FX3U-16M + FX3U-ENET-L  (MC protocol A-compatible 1E, ASCII)

import socket
import time
from typing import List, Sequence

PLC_IP   = "192.168.3.254"
PLC_PORT = 1027

# Device codes (ASCII-hex) from manual
DEV_D = "4420"  # D
DEV_X = "5820"  # X
DEV_Y = "5920"  # Y


# --------- low-level helpers ---------

def _exchange(cmd_hex: str) -> str:
    """Send one MC ASCII command (hex string) and return decoded ASCII reply."""
    # print(f"TX: {cmd_hex}")
    with socket.create_connection((PLC_IP, PLC_PORT), timeout=2.0) as sock:
        sock.sendall(cmd_hex.encode("ascii"))
        data = sock.recv(4096)

    # print("Raw response:", data)
    rx = data.decode("ascii", errors="ignore").strip()
    # print("Decoded     :", rx)
    return rx


def _parse_mc_payload(rx: str, expect_ok: bool = True) -> str:
    """
    Common parser: returns payload (after 4 chars) when end_code == '00'.
    subheader is usually 80/81/82/83 etc, we just print it.
    """
    if len(rx) < 4:
        raise RuntimeError(f"Response too short: {rx!r}")

    subheader = rx[0:2]
    end_code  = rx[2:4]
    # print(f"MC header: subheader={subheader}, end_code={end_code}")

    if expect_ok and end_code != "00":
        raise RuntimeError(f"MC protocol error, end_code=0x{end_code}, raw={rx}")

    return rx[4:]


def _build_1e_cmd(
    cmd: int,
    dev_code: str,
    head: int,
    points: int,
    swap_points: bool = False,
) -> str:
    """
    Build A-compatible 1E ASCII frame (no data part).
    cmd       : 0x00,0x01,0x02,0x03,...
    dev_code  : e.g. '4420','5820','5920'
    head      : device number (integer)
    points    : number of points / words
    swap_points=True -> low/high byte order (…PPHH) like Mitsubishi sample
                       "01FF000A4420000000000500".
    """
    header = f"{cmd:02X}FF000A"      # cmd, PC=FF, timer=000A
    head_hex = f"{head & 0xFFFFFFFF:08X}"

    if not swap_points:
        pts_hex = f"{points & 0xFFFF:04X}"          # 0005, 000C, ...
    else:
        # low-byte then high-byte (e.g. 0005 -> 0500)
        lo = points & 0xFF
        hi = (points >> 8) & 0xFF
        pts_hex = f"{lo:02X}{hi:02X}"

    return header + dev_code + head_hex + pts_hex


def _auto_cmd_and_payload(
    cmd: int,
    dev_code: str,
    head: int,
    points: int,
    data_field: str | None = None,
) -> str:
    """
    Try 'spec' frame first, then 'swap_points' frame if PLC returns error.
    Returns payload (data part) of *successful* response.
    """
    variants = [
        ("spec", False),
        ("swap_points", True),
    ]

    last_error = None
    for name, swap in variants:
        cmd_hex = _build_1e_cmd(cmd, dev_code, head, points, swap_points=swap)
        if data_field:
            cmd_hex += data_field

        # print(f"Trying variant={name}")
        try:
            rx = _exchange(cmd_hex)
            payload = _parse_mc_payload(rx, expect_ok=True)
            # print(f"Variant {name} OK")
            return payload
        except Exception as e:
            # print(f"Variant {name} failed: {e}")
            last_error = e

    # ถ้าทั้งสองแบบพลาด ก็โยน error อันสุดท้ายออกไป
    raise last_error if last_error is not None else RuntimeError("No response")


# --------- bit devices: X / Y ---------

def _read_bits(dev_code: str, head: int, points: int) -> List[int]:
    """
    Generic bit-device batch read (command 0x00).
    Returns list of 0/1 ints.
    head   : device number (int).  X0 -> 0, X10(octal) -> int('10', 8) = 8, ...
    points : number of bits
    """
    if points <= 0:
        return []

    # cmd 0x00 = batch read / bit units
    payload = _auto_cmd_and_payload(0x00, dev_code, head, points)

    # ตาม manual: payload คือ '0'/'1' ต่อกัน; ถ้าจำนวน point เป็น odd
    # จะมี dummy '0' ตัวท้ายเพิ่มมา – เราใช้แค่ตัวแรก ๆ ตาม points ที่ขอ
    if len(payload) < points:
        raise RuntimeError(f"Not enough bit data, payload={payload!r}")

    bits = [1 if c == "1" else 0 for c in payload[:points]]
    return bits


def _write_bits(dev_code: str, head: int, values: Sequence[int | bool]) -> None:
    """
    Generic bit-device batch write (command 0x02).
    values: ลิสต์ของ 0/1 หรือ False/True
    """
    vals = [1 if bool(v) else 0 for v in values]
    points = len(vals)
    if points == 0:
        return

    # ตาม manual: ถ้าจำนวน point เป็นเลขคี่ ให้เติม dummy 1 byte ('0')
    data_chars = "".join("1" if v else "0" for v in vals)
    if points % 2 == 1:
        data_chars += "0"   # dummy

    # cmd 0x02 = batch write / bit units
    payload = _auto_cmd_and_payload(0x02, dev_code, head, points, data_field=data_chars)

    # สำหรับ write, payload โดยปกติจะเป็นแค่ header ไม่มี data เพิ่ม
    # print("Write payload:", payload)


# --------- public APIs ---------

def read_x(head: int, points: int) -> List[int]:
    """
    Read X[head] .. X[head+points-1] (bit units).
    หมายเหตุ: X/Y เป็นเลขฐาน 8 ในโปรแกรม PLC
    - ถ้าอยากอ่าน X0..X7      -> read_x(0, 8)
    - ถ้าอยากอ่าน X20(octal)  -> read_x(int("20", 8), 8)
    """
    return _read_bits(DEV_X, head, points)


def read_y(head: int, points: int) -> List[int]:
    """Read Y[head] .. Y[head+points-1] (bit units)."""
    return _read_bits(DEV_Y, head, points)


def write_y(head: int, values: Sequence[int | bool] | int | bool) -> None:
    """
    Write to Y devices (bit units).
    - ถ้า values เป็น int/bool เดี่ยว -> set Y[head]
    - ถ้า values เป็น list/tuple -> เขียนหลายจุดต่อเนื่อง
    """
    if isinstance(values, (int, bool)):
        vals_seq = [values]
    else:
        vals_seq = list(values)
    _write_bits(DEV_Y, head, vals_seq)

def read_d(head: int, words: int = 1) -> List[int]:
    """
    Read D registers (word units)
    เช่น:
        read_d(0, 5)  -> D0..D4
        read_d(100)   -> D100 (1 word)
    """
    if words <= 0:
        return []

    # cmd 0x01 = batch read / word units
    payload = _auto_cmd_and_payload(0x01, DEV_D, head, words)

    # word = 4 hex chars
    if len(payload) < words * 4:
        raise RuntimeError(f"Not enough word data, payload={payload!r}")

    vals: List[int] = []
    for i in range(words):
        s = payload[i*4 : i*4+4]   # เช่น "0123"
        vals.append(int(s, 16))
    return vals


def write_d(head: int, values: Sequence[int] | int) -> None:
    """
    Write to D registers (word units)
    - ถ้า values เป็น int เดี่ยว -> set D[head]
    - ถ้า values เป็น list/tuple -> set D[head..]
    """
    if isinstance(values, int):
        values = [values]

    words = len(values)
    if words <= 0:
        return

    # สร้าง data field: แต่ละ word = 4 hex chars
    data_field = "".join(f"{v & 0xFFFF:04X}" for v in values)

    # cmd 0x03 = batch write / word units
    payload = _auto_cmd_and_payload(0x03, DEV_D, head, words, data_field=data_field)
    # print("Write D payload:", payload)



if __name__ == "__main__":
    print("ตัวอย่างอ่าน X0..X7")
    x_vals = read_x(0, 8)  # X0..X7
    print("X0..X7 =", x_vals)
    time.sleep(0.01)
    print()

    print("ตัวอย่างอ่าน Y0..Y7")
    y_vals = read_y(0, 8)  # Y0..Y7
    print("Y0..Y7 =", y_vals)
    time.sleep(0.01)
    print()

    print("ตัวอย่างเขียน Y")
    write_y(0, [1, 1])
    print("เขียน Y0=1, Y1=1")
    time.sleep(0.01)
    print()

    print("ตัวอย่างอ่าน D0..D9")
    vals = read_d(0, 20)
    print("D0..D9 =", vals)
    time.sleep(0.01)
    print()

    print("ตัวอย่างเขียนค่า 123 ไปที่ D5")
    write_d(5, 123)
    time.sleep(0.01)
    print()

    write_d(10, [10,20,30])
    print("เขียน D10=10, D11=20, D12=30")
    time.sleep(0.01)
    print()

'''
C:\PythonProjects\mc-test\.venv\Scripts\python.exe C:\PythonProjects\mc-test\t2.py 
ตัวอย่างอ่าน X0..X7
X0..X7 = [0, 0, 0, 0, 0, 0, 0, 0]

ตัวอย่างอ่าน Y0..Y7
Y0..Y7 = [1, 1, 0, 0, 0, 0, 0, 0]

ตัวอย่างเขียน Y
เขียน Y0=1, Y1=1

ตัวอย่างอ่าน D0..D9
D0..D9 = [10, 11, 12, 0, 0, 123, 0, 0, 0, 0, 10, 20, 30, 0, 0, 0, 0, 0, 0, 0]

ตัวอย่างเขียนค่า 123 ไปที่ D5

เขียน D10=10, D11=20, D12=30

'''