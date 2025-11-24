# FX3U-16M + FX3U-ENET-L  (MC protocol A-compatible 1E, ASCII)
# v7: persistent TCP connection + connect retry and recv loop

import socket
import time
from typing import List, Sequence, Optional


class FX3U:
    DEV_D = "4420"  # D
    DEV_X = "5820"  # X
    DEV_Y = "5920"  # Y

    def __init__(
            self,
            ip: str,
            port: int = 1027,
            debug: bool = False,
            connect_retries: int = 3,
            connect_backoff: float = 0.05,
            read_timeout: float = 0.5,
    ) -> None:
        self.ip = ip
        self.port = port
        self.debug = debug
        self.connect_retries = connect_retries
        self.connect_backoff = connect_backoff
        self.read_timeout = read_timeout
        self.sock: Optional[socket.socket] = None

    def connect(self) -> None:
        if self.sock:
            return
        last_exc = None
        for attempt in range(1, self.connect_retries + 1):
            try:
                if self.debug:
                    print(f"Connecting to {self.ip}:{self.port} (attempt {attempt})")
                s = socket.create_connection((self.ip, self.port), timeout=2.0)
                # use read timeout for recv loop
                s.settimeout(self.read_timeout)
                self.sock = s
                if self.debug:
                    print("Connected")
                return
            except Exception as e:
                last_exc = e
                if self.debug:
                    print("Connect failed:", e)
                time.sleep(self.connect_backoff)
        raise last_exc

    def close(self) -> None:
        if self.sock:
            try:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self.sock.close()
            finally:
                self.sock = None
                if self.debug:
                    print("Socket closed")

    # Context manager support
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _exchange(self, cmd_hex: str) -> str:
        """
        Send one MC ASCII command (hex string) and return decoded ASCII reply.
        Reuses a single TCP connection.
        """
        if self.debug:
            print(f"\nTX: {cmd_hex}")
        # ensure connected (with retries)
        self.connect()

        assert self.sock is not None
        s = self.sock
        # send
        s.sendall(cmd_hex.encode("ascii"))

        # collect response: loop recv until timeout (server close or no more data)
        parts = []
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    # peer closed
                    break
                parts.append(chunk)
                # small heuristic: if we have at least 4 bytes (header) and no more data arrives
                # recv will raise socket.timeout if no data within read_timeout
        except socket.timeout:
            # normal: we've read whatever server sent
            pass
        except ConnectionResetError as e:
            # server reset the socket: drop connection locally and re-raise
            if self.debug:
                print("Connection reset by peer during recv:", e)
            self.close()
            raise

        data = b"".join(parts)
        if self.debug:
            print("Raw response:", data)
        rx = data.decode("ascii", errors="ignore").strip()
        if self.debug:
            print("Decoded     :", rx)
        return rx

    def _parse_mc_payload(self, rx: str, expect_ok: bool = True) -> str:
        if len(rx) < 4:
            raise RuntimeError(f"Response too short: {rx!r}")

        subheader = rx[0:2]
        end_code = rx[2:4]
        if self.debug:
            print(f"MC header: subheader={subheader}, end_code={end_code}")

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

    # bit devices: X / Y
    def _read_bits(self, dev_code: str, head: int, points: int) -> List[int]:
        if points <= 0:
            return []
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
        self._execute_cmd(0x02, dev_code, head, points, data_field=data_chars)

    # public APIs
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
        self._execute_cmd(0x03, self.DEV_D, head, words, data_field=data_field)


if __name__ == "__main__":
    from datetime import datetime

    plc = FX3U("192.168.3.254", 1027, debug=True)
    plc.connect()
    try:
        x_vals = plc.read_x(0, 8)
        print(datetime.now(), "X0..X7 =", x_vals)
        # time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # ปิด Y0..Y7 ทีละบิต
        for i in range(8):
            plc.write_y(i, 0)
            print(datetime.now(), f"Y{i} = 0")
#             time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # อ่าน Y0..Y7
        y_vals = plc.read_y(0, 8)
        print(datetime.now(), "Y0..Y7 =", y_vals)
#         time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # เปิด Y0..Y7 ทีละบิต
        for i in range(8):
            plc.write_y(i, 1)
            print(datetime.now(), f"Y{i} = 1")
#             time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # อ่าน Y0..Y7 อีกครั้ง
        y_vals = plc.read_y(0, 8)
        print(datetime.now(), "Y0..Y7 =", y_vals)
#         time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # อ่าน D0..D9
        d_vals = plc.read_d(0, 10)
        print(datetime.now(), "D0..D9 =", d_vals)
#         time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # เขียน D5 = D5+1
        d_vals = plc.read_d(0, 10)
#         time.sleep(0.1)
        new_val = d_vals[5] + 1
        plc.write_d(5, new_val)
        print(datetime.now(), "Wrote D5 =", new_val)
#         time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

    try:
        # อ่าน D0..D9 อีกครั้ง
        d_vals = plc.read_d(0, 10)
        print(datetime.now(), "D0..D9 =", d_vals)
#         time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

