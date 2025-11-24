import socket
from datetime import datetime
import select
from typing import Dict, List, Sequence, Tuple, Union, Optional


class MCError(RuntimeError):
    pass


class FX3U:
    DEV_D = "4420"
    DEV_X = "5820"
    DEV_Y = "5920"

    _POINTS_MODE_CACHE: Dict[Tuple[int, str], bool] = {}

    def __init__(
            self,
            ip: str,
            port: int,
            timeout: float = 1.5,
            keep_conn: bool = True
    ):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.keep_conn = keep_conn
        self._sock: Optional[socket.socket] = None

    def __enter__(self) -> "FX3U":
        if self.keep_conn:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def connect(self, timeout: Optional[float] = None) -> None:
        if not self.keep_conn:
            return

        if self._sock is not None:
            return

        to = timeout if timeout is not None else self.timeout
        sock = socket.create_connection((self.ip, self.port), timeout=to)
        sock.settimeout(self.timeout)
        self._sock = sock

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def _recv_all_from_sock(self, sock: socket.socket) -> str:
        try:
            first = sock.recv(4096)
        except socket.timeout:
            raise MCError("Timeout waiting for response from PLC")
        except OSError as e:
            raise MCError(f"Socket recv error: {e}") from e

        if not first:
            raise MCError("Empty response from PLC")

        chunks: List[bytes] = [first]

        short_timeout = 0.2
        while True:
            r, _, _ = select.select([sock], [], [], short_timeout)
            if not r:
                break
            try:
                part = sock.recv(4096)
            except socket.timeout:
                break
            if not part:
                break
            chunks.append(part)

        rx = b"".join(chunks).decode("ascii", errors="ignore").strip()
        if not rx:
            raise MCError("Empty/invalid ASCII response from PLC")
        return rx

    def _exchange(self, cmd_hex: str) -> str:
        if self.keep_conn:
            if self._sock is None:
                self.connect()

            assert self._sock is not None
            try:
                self._sock.settimeout(self.timeout)
                self._sock.sendall(cmd_hex.encode("ascii"))
                rx = self._recv_all_from_sock(self._sock)
                return rx
            except (OSError, MCError) as e:
                # Try to recover by re-opening connection once
                try:
                    self.close()
                    self.connect()
                    assert self._sock is not None
                    self._sock.settimeout(self.timeout)
                    self._sock.sendall(cmd_hex.encode("ascii"))
                    rx = self._recv_all_from_sock(self._sock)
                    return rx
                except Exception as e2:
                    self.close()
                    raise MCError(f"Socket error to {self.ip}:{self.port} -> {e2}") from e2
        else:
            try:
                with socket.create_connection((self.ip, self.port), timeout=self.timeout) as sock:
                    sock.settimeout(self.timeout)
                    sock.sendall(cmd_hex.encode("ascii"))
                    rx = self._recv_all_from_sock(sock)
                    return rx
            except OSError as e:
                raise MCError(f"Socket error to {self.ip}:{self.port} -> {e}") from e

    @staticmethod
    def _parse(rx: str) -> str:
        if len(rx) < 4:
            raise MCError(f"Response too short: {rx!r}")

        end_code = rx[2:4]
        if end_code != "00":
            raise MCError(f"MC EndCode=0x{end_code}, raw={rx!r}")

        return rx[4:]

    @staticmethod
    def _build_1e_cmd_header(
            cmd: int,
            dev_code: str,
            head: int,
            count: int,
            *,
            swap_points: bool = False,
    ) -> str:
        if not (0 <= cmd <= 0xFF):
            raise MCError(f"Invalid cmd: {cmd}")

        header = f"{cmd:02X}FF000A"
        head_hex = f"{head & 0xFFFFFFFF:08X}"

        if not swap_points:
            cnt_hex = f"{count & 0xFFFF:04X}"
        else:
            lo = count & 0xFF
            hi = (count >> 8) & 0xFF
            cnt_hex = f"{lo:02X}{hi:02X}"

        return header + dev_code + head_hex + cnt_hex

    def _cmd(
            self,
            cmd: int,
            dev: str,
            head: int,
            count: int,
            data: Optional[str] = None,
    ) -> str:
        key = (cmd, dev)

        if key in self._POINTS_MODE_CACHE:
            modes: List[Tuple[str, bool]] = [("cached", self._POINTS_MODE_CACHE[key])]
        else:
            modes = [("spec", False), ("swap", True)]

        last_err: Optional[Exception] = None

        for name, swap in modes:
            frame = self._build_1e_cmd_header(cmd, dev, head, count, swap_points=swap)
            if data is not None:
                frame += data

            try:
                rx = self._exchange(frame)
                payload = self._parse(rx)

                if name in ("spec", "swap"):
                    self._POINTS_MODE_CACHE[key] = swap

                return payload

            except Exception as e:
                last_err = e
                if name == "cached":
                    self._POINTS_MODE_CACHE.pop(key, None)
                    return self._cmd(cmd, dev, head, count, data)

        raise MCError(f"Command failed (both spec/swap modes): {last_err}")

    def read_d(self, head: int, words: int = 1) -> List[int]:
        if words <= 0:
            return []

        payload = self._cmd(0x01, self.DEV_D, head, words)

        expected_len = words * 4  # 4 hex chars per word
        if len(payload) < expected_len:
            raise MCError(
                f"Not enough word data, expected {expected_len} chars, "
                f"got {len(payload)}, payload={payload!r}"
            )

        values: List[int] = []
        for i in range(words):
            start = i * 4
            chunk = payload[start:start + 4]
            values.append(int(chunk, 16))

        return values

    def write_d(self, head: int, values: Union[Sequence[int], int]) -> None:
        if isinstance(values, int):
            values = [values]

        vals = list(values)
        if not vals:
            return

        data = "".join(f"{v & 0xFFFF:04X}" for v in vals)
        self._cmd(0x03, self.DEV_D, head, len(vals), data)

    def _read_bits(self, dev: str, head: int, points: int) -> List[int]:
        if points <= 0:
            return []

        payload = self._cmd(0x00, dev, head, points)

        if len(payload) < points:
            raise MCError(
                f"Not enough bit data, expected {points}, "
                f"got {len(payload)}, payload={payload!r}"
            )

        return [1 if c == "1" else 0 for c in payload[:points]]

    def read_x(self, head: int, points: int) -> List[int]:
        return self._read_bits(self.DEV_X, head, points)

    def read_y(self, head: int, points: int) -> List[int]:
        return self._read_bits(self.DEV_Y, head, points)

    def write_y(self, head: int, values: Union[Sequence[Union[int, bool]], int, bool]) -> None:
        if isinstance(values, (int, bool)):
            values = [values]

        vals = [1 if bool(v) else 0 for v in values]
        if not vals:
            return

        data = "".join("1" if v else "0" for v in vals)

        if len(data) % 2 == 1:
            data += "0"

        self._cmd(0x02, self.DEV_Y, head, len(vals), data)


def main() -> None:
    import time
    with FX3U("192.168.3.254", 1027, timeout=1.5, keep_conn=True) as plc:

        try:
            x_vals = plc.read_x(0, 8)
            print(datetime.now(), "X0..X7 =", x_vals)
        except MCError as e:
            print("MCError reading X0..X7:", e)
        time.sleep(1)
        try:
            # ปิด Y0..Y7 ทีละบิต
            for i in range(8):
                plc.write_y(i, 0)
                print(datetime.now(), f"Y{i} = 0")
        except MCError as e:
            print("MCError writing Y0..Y7:", e)
        time.sleep(1)
        try:
            y_vals = plc.read_y(0, 8)
            print(datetime.now(), "Y0..Y7 =", y_vals)
        except MCError as e:
            print("MCError reading Y0..Y7:", e)
        time.sleep(1)
        try:
            # เปิด Y0..Y7 ทีละบิต
            for i in range(8):
                plc.write_y(i, 1)
                print(datetime.now(), f"Y{i} = 1")
        except MCError as e:
            print("MCError writing Y0..Y7:", e)
        time.sleep(1)
        try:
            y_vals = plc.read_y(0, 8)
            print(datetime.now(), "Y0..Y7 =", y_vals)
        except MCError as e:
            print("MCError reading Y0..Y7:", e)
        time.sleep(1)
        try:
            d_vals = plc.read_d(0, 10)
            print(datetime.now(), "D0..D9 =", d_vals)
        except MCError as e:
            print("MCError reading D0..D9:", e)
        time.sleep(1)
        try:
            plc.write_d(5, d_vals[5] + 1)
            print(datetime.now(), "Wrote D5 =", d_vals[5] + 1)
        except MCError as e:
            print("MCError writing D5:", e)
        time.sleep(1)
        try:
            d_vals = plc.read_d(0, 10)
            print(datetime.now(), "D0..D9 =", d_vals)
        except MCError as e:
            print("MCError reading D0..D9:", e)


if __name__ == "__main__":
    main()

'''
run v4.py on windows PC
C:\PythonProjects\CHTDX\.venv\Scripts\python.exe C:\PythonProjects\mc-test\v4.py 
2025-11-24 10:01:07.664831 X0..X7 = [0, 0, 0, 0, 0, 0, 0, 0]
2025-11-24 10:01:11.945349 Y0 = 0
2025-11-24 10:01:12.161519 Y1 = 0
2025-11-24 10:01:12.396145 Y2 = 0
2025-11-24 10:01:12.631277 Y3 = 0
2025-11-24 10:01:12.851624 Y4 = 0
2025-11-24 10:01:13.068965 Y5 = 0
2025-11-24 10:01:13.288404 Y6 = 0
2025-11-24 10:01:13.505218 Y7 = 0
2025-11-24 10:01:13.738704 Y0..Y7 = [0, 0, 0, 0, 0, 0, 0, 0]
2025-11-24 10:01:13.957468 Y0 = 1
2025-11-24 10:01:14.191432 Y1 = 1
2025-11-24 10:01:14.412073 Y2 = 1
2025-11-24 10:01:14.632735 Y3 = 1
2025-11-24 10:01:14.852889 Y4 = 1
2025-11-24 10:01:15.071526 Y5 = 1
2025-11-24 10:01:15.291203 Y6 = 1
2025-11-24 10:01:15.507996 Y7 = 1
2025-11-24 10:01:15.741191 Y0..Y7 = [1, 1, 1, 1, 1, 1, 1, 1]
2025-11-24 10:01:16.193071 D0..D9 = [10, 11, 12, 0, 0, 5, 0, 0, 0, 0]
2025-11-24 10:01:20.452603 Wrote D5 = 6
2025-11-24 10:01:20.672692 D0..D9 = [10, 11, 12, 0, 0, 6, 0, 0, 0, 0]

run v4.py on raspberrypi
(.venv) pi@raspberrypi:~/PythonProjects/mc-test $ python v4.py 
/home/pi/PythonProjects/mc-test/v4.py:453: SyntaxWarning: invalid escape sequence '\P'
  C:\PythonProjects\CHTDX\.venv\Scripts\python.exe C:\PythonProjects\mc-test\v4.py
2025-11-24 03:14:00.686462 X0..X7 = [0, 0, 0, 0, 0, 0, 0, 0]
MCError writing Y0..Y7: Command failed (both spec/swap modes): [Errno 111] Connection refused
2025-11-24 03:14:04.426201 Y0..Y7 = [1, 1, 1, 1, 1, 1, 1, 1]
MCError writing Y0..Y7: Command failed (both spec/swap modes): [Errno 111] Connection refused
2025-11-24 03:14:08.156072 Y0..Y7 = [1, 1, 1, 1, 1, 1, 1, 1]
2025-11-24 03:14:09.583990 D0..D9 = [10, 11, 12, 0, 0, 6, 0, 0, 0, 0]
MCError writing D5: Command failed (both spec/swap modes): [Errno 111] Connection refused
2025-11-24 03:14:13.313754 D0..D9 = [10, 11, 12, 0, 0, 6, 0, 0, 0, 0]
'''
