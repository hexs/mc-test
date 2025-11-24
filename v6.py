# FX3U-16M + FX3U-ENET-L  (MC protocol A-compatible 1E, ASCII)

import socket
import time
from typing import List, Sequence


class FX3U:
    DEV_D = "4420"  # D
    DEV_X = "5820"  # X
    DEV_Y = "5920"  # Y

    def __init__(self, ip: str, port: int, debug=False) -> None:
        self.ip = ip
        self.port = port
        self.debug = debug

    def _exchange(self, cmd_hex: str) -> str:
        if self.debug: print(f"\nTX: {cmd_hex}")
        with socket.create_connection((self.ip, self.port), timeout=2.0) as sock:
            sock.sendall(cmd_hex.encode("ascii"))
            data = sock.recv(4096)

        if self.debug: print("Raw response:", data)
        rx = data.decode("ascii", errors="ignore").strip()
        if self.debug: print("Decoded     :", rx)
        return rx

    def _parse_mc_payload(self, rx: str, expect_ok: bool = True) -> str:
        if len(rx) < 4:
            raise RuntimeError(f"Response too short: {rx!r}")

        subheader = rx[0:2]
        end_code = rx[2:4]
        if self.debug: print(f"MC header: subheader={subheader}, end_code={end_code}")

        if expect_ok and end_code != "00":
            raise RuntimeError(f"MC protocol error, end_code=0x{end_code}, raw={rx}")

        return rx[4:]

    def _build_1e_cmd(
            self,
            cmd: int,
            dev_code: str,
            head: int,
            points: int,
    ) -> str:
        header = f"{cmd:02X}FF000A"  # cmd, PC=FF, timer=000A
        head_hex = f"{head & 0xFFFFFFFF:08X}"

        # Force low/high byte order (e.g. 0005 -> 0500)
        lo = points & 0xFF
        hi = (points >> 8) & 0xFF
        pts_hex = f"{lo:02X}{hi:02X}"

        return header + dev_code + head_hex + pts_hex

    def _execute_cmd(
            self,
            cmd: int,
            dev_code: str,
            head: int,
            points: int,
            data_field: str | None = None,
    ) -> str:
        cmd_hex = self._build_1e_cmd(cmd, dev_code, head, points)
        if data_field:
            cmd_hex += data_field

        rx = self._exchange(cmd_hex)
        payload = self._parse_mc_payload(rx, expect_ok=True)
        return payload

    # --------- bit devices: X / Y ---------

    def _read_bits(self, dev_code: str, head: int, points: int) -> List[int]:
        if points <= 0:
            return []

        # cmd 0x00 = batch read / bit units
        payload = self._execute_cmd(0x00, dev_code, head, points)

        if len(payload) < points:
            raise RuntimeError(f"Not enough bit data, payload={payload!r}")

        bits = [1 if c == "1" else 0 for c in payload[:points]]
        return bits

    def _write_bits(self, dev_code: str, head: int, values: Sequence[int | bool]) -> None:
        vals = [1 if bool(v) else 0 for v in values]
        points = len(vals)
        if points == 0:
            return

        data_chars = "".join("1" if v else "0" for v in vals)
        if points % 2 == 1:
            data_chars += "0"  # dummy

        # cmd 0x02 = batch write / bit units
        payload = self._execute_cmd(0x02, dev_code, head, points, data_field=data_chars)
        if self.debug: print("Write payload:", payload)

    # --------- public APIs ---------

    def read_x(self, head: int, points: int) -> List[int]:
        return self._read_bits(self.DEV_X, head, points)

    def read_y(self, head: int, points: int) -> List[int]:
        return self._read_bits(self.DEV_Y, head, points)

    def write_y(self, head: int, values: Sequence[int | bool] | int | bool) -> None:
        if isinstance(values, (int, bool)):
            vals_seq = [values]
        else:
            vals_seq = list(values)
        self._write_bits(self.DEV_Y, head, vals_seq)

    def read_d(self, head: int, words: int = 1) -> List[int]:
        if words <= 0:
            return []

        # cmd 0x01 = batch read / word units
        payload = self._execute_cmd(0x01, self.DEV_D, head, words)

        if len(payload) < words * 4:
            raise RuntimeError(f"Not enough word data, payload={payload!r}")

        vals: List[int] = []
        for i in range(words):
            s = payload[i * 4: i * 4 + 4]
            vals.append(int(s, 16))
        return vals

    def write_d(self, head: int, values: Sequence[int] | int) -> None:
        if isinstance(values, int):
            values = [values]

        words = len(values)
        if words <= 0:
            return

        data_field = "".join(f"{v & 0xFFFF:04X}" for v in values)

        # cmd 0x03 = batch write / word units
        payload = self._execute_cmd(0x03, self.DEV_D, head, words, data_field=data_field)
        if self.debug: print("Write D payload:", payload)


if __name__ == "__main__":
    from datetime import datetime

    plc = FX3U("192.168.3.254", 1027, debug=True)

    try:
        x_vals = plc.read_x(0, 8)
        print(datetime.now(), "X0..X7 =", x_vals)
        time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # ปิด Y0..Y7 ทีละบิต
        for i in range(8):
            plc.write_y(i, 0)
            print(datetime.now(), f"Y{i} = 0")
            time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # อ่าน Y0..Y7
        y_vals = plc.read_y(0, 8)
        print(datetime.now(), "Y0..Y7 =", y_vals)
        time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # เปิด Y0..Y7 ทีละบิต
        for i in range(8):
            plc.write_y(i, 1)
            print(datetime.now(), f"Y{i} = 1")
            time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # อ่าน Y0..Y7 อีกครั้ง
        y_vals = plc.read_y(0, 8)
        print(datetime.now(), "Y0..Y7 =", y_vals)
        time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # อ่าน D0..D9
        d_vals = plc.read_d(0, 10)
        print(datetime.now(), "D0..D9 =", d_vals)
        time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # เขียน D5 = D5+1
        d_vals = plc.read_d(0, 10)
        new_val = d_vals[5] + 1
        plc.write_d(5, new_val)
        print(datetime.now(), "Wrote D5 =", new_val)
        time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # อ่าน D0..D9 อีกครั้ง
        d_vals = plc.read_d(0, 10)
        print(datetime.now(), "D0..D9 =", d_vals)
    except Exception as e:
        print("Error: ", e)
