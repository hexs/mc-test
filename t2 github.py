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

def _exchange(cmd_hex: str, connect_timeout: float = 2.0, read_timeout: float = 2.0) -> str:
    """Send one MC ASCII command (hex string) and return decoded ASCII reply.
       Added more logging and ensured the socket read uses a timeout and a loop.
    """
    print("TX:", cmd_hex)
    addr = (PLC_IP, PLC_PORT)
    with socket.create_connection(addr, timeout=connect_timeout) as sock:
        # ensure read won't block forever
        sock.settimeout(read_timeout)
        try:
            sock.sendall(cmd_hex.encode("ascii"))
        except Exception as e:
            print("sendall error:", e)
            raise
        # collect response until timeout or socket close
        parts = []
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                parts.append(chunk)
        except socket.timeout:
            # normal if server doesn't close connection; we use whatever we got
            pass
        data = b"".join(parts)
    rx = data.decode("ascii", errors="ignore").strip()
    print("RX (raw):", rx)
    return rx



def _parse_mc_payload(rx: str, expect_ok: bool = True) -> str:
    if len(rx) < 4:
        raise RuntimeError(f"Response too short: {rx!r}")

    end_code  = rx[2:4]

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
    header = f"{cmd:02X}FF000A"
    head_hex = f"{head & 0xFFFFFFFF:08X}"

    if not swap_points:
        pts_hex = f"{points & 0xFFFF:04X}"
    else:
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
    variants = [
        ("spec", False),
        ("swap_points", True),
    ]

    last_error = None
    for name, swap in variants:
        cmd_hex = _build_1e_cmd(cmd, dev_code, head, points, swap_points=swap)
        if data_field:
            cmd_hex += data_field

        try:
            rx = _exchange(cmd_hex)
            payload = _parse_mc_payload(rx, expect_ok=True)
            return payload
        except Exception as e:
            last_error = e

    raise last_error if last_error is not None else RuntimeError("No response")


# --------- bit devices: X / Y ---------

def _read_bits(dev_code: str, head: int, points: int) -> List[int]:
    if points <= 0:
        return []

    payload = _auto_cmd_and_payload(0x00, dev_code, head, points)

    if len(payload) < points:
        raise RuntimeError(f"Not enough bit data, payload={payload!r}")

    bits = [1 if c == "1" else 0 for c in payload[:points]]
    return bits


def _write_bits(dev_code: str, head: int, values: Sequence[int | bool]) -> None:
    vals = [1 if bool(v) else 0 for v in values]
    points = len(vals)
    if points == 0:
        return

    data_chars = "".join("1" if v else "0" for v in vals)
    if points % 2 == 1:
        data_chars += "0"   # dummy

    payload = _auto_cmd_and_payload(0x02, dev_code, head, points, data_field=data_chars)


# --------- public APIs ---------

def read_x(head: int, points: int) -> List[int]:
    return _read_bits(DEV_X, head, points)


def read_y(head: int, points: int) -> List[int]:
    return _read_bits(DEV_Y, head, points)


def write_y(head: int, values: Sequence[int | bool] | int | bool) -> None:
    if isinstance(values, (int, bool)):
        vals_seq = [values]
    else:
        vals_seq = list(values)
    _write_bits(DEV_Y, head, vals_seq)

def read_d(head: int, words: int = 1) -> List[int]:
    if words <= 0:
        return []

    payload = _auto_cmd_and_payload(0x01, DEV_D, head, words)

    if len(payload) < words * 4:
        raise RuntimeError(f"Not enough word data, payload={payload!r}")

    vals: List[int] = []
    for i in range(words):
        s = payload[i*4 : i*4+4]   # เช่น "0123"
        vals.append(int(s, 16))
    return vals


def write_d(head: int, values: Sequence[int] | int) -> None:
    if isinstance(values, int):
        values = [values]

    words = len(values)
    if words <= 0:
        return

    data_field = "".join(f"{v & 0xFFFF:04X}" for v in values)

    payload = _auto_cmd_and_payload(0x03, DEV_D, head, words, data_field=data_field)



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