```
pi@raspberrypi:~/PythonProjects/mc-test $ cat v6.py
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
        time.sleep(0.1)
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
        time.sleep(0.1)
    except Exception as e:
        print("Error: ", e)

pi@raspberrypi:~/PythonProjects/mc-test $ python v6.py 

TX: 00FF000A5820000000000800
Raw response: b'800000000000'
Decoded     : 800000000000
MC header: subheader=80, end_code=00
2025-11-24 07:43:06.127324 X0..X7 = [0, 0, 0, 0, 0, 0, 0, 0]

TX: 02FF000A592000000000010000
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:06.247429 Y0 = 0

TX: 02FF000A592000000001010000
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:06.367254 Y1 = 0

TX: 02FF000A592000000002010000
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:06.487257 Y2 = 0

TX: 02FF000A592000000003010000
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:06.607250 Y3 = 0

TX: 02FF000A592000000004010000
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:06.727285 Y4 = 0

TX: 02FF000A592000000005010000
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:06.847278 Y5 = 0

TX: 02FF000A592000000006010000
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:06.967230 Y6 = 0

TX: 02FF000A592000000007010000
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:07.087229 Y7 = 0

TX: 00FF000A5920000000000800
Raw response: b'800000000000'
Decoded     : 800000000000
MC header: subheader=80, end_code=00
2025-11-24 07:43:07.207303 Y0..Y7 = [0, 0, 0, 0, 0, 0, 0, 0]

TX: 02FF000A592000000000010010
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:07.327225 Y0 = 1

TX: 02FF000A592000000001010010
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:07.447260 Y1 = 1

TX: 02FF000A592000000002010010
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:07.567214 Y2 = 1

TX: 02FF000A592000000003010010
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:07.687223 Y3 = 1

TX: 02FF000A592000000004010010
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:07.807221 Y4 = 1

TX: 02FF000A592000000005010010
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:07.927199 Y5 = 1

TX: 02FF000A592000000006010010
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:08.047240 Y6 = 1

TX: 02FF000A592000000007010010
Raw response: b'8200'
Decoded     : 8200
MC header: subheader=82, end_code=00
Write payload: 
2025-11-24 07:43:08.167214 Y7 = 1

TX: 00FF000A5920000000000800
Raw response: b'800011111111'
Decoded     : 800011111111
MC header: subheader=80, end_code=00
2025-11-24 07:43:08.287266 Y0..Y7 = [1, 1, 1, 1, 1, 1, 1, 1]

TX: 01FF000A4420000000000A00
Raw response: b'8100000A000B000C0000000000190000000000000000'
Decoded     : 8100000A000B000C0000000000190000000000000000
MC header: subheader=81, end_code=00
2025-11-24 07:43:08.407423 D0..D9 = [10, 11, 12, 0, 0, 25, 0, 0, 0, 0]

TX: 01FF000A4420000000000A00
Raw response: b'8100000A000B000C0000000000190000000000000000'
Decoded     : 8100000A000B000C0000000000190000000000000000
MC header: subheader=81, end_code=00

TX: 03FF000A4420000000050100001A
Raw response: b'8300'
Decoded     : 8300
MC header: subheader=83, end_code=00
Write D payload: 
2025-11-24 07:43:08.647230 Wrote D5 = 26

TX: 01FF000A4420000000000A00
Raw response: b'8100000A000B000C00000000001A0000000000000000'
Decoded     : 8100000A000B000C00000000001A0000000000000000
MC header: subheader=81, end_code=00
2025-11-24 07:43:08.767415 D0..D9 = [10, 11, 12, 0, 0, 26, 0, 0, 0, 0]
pi@raspberrypi:~/PythonProjects/mc-test $ 
pi@raspberrypi:~/PythonProjects/mc-test $ nano v6.py
remove all time.sleep(0.1) from if __name__ == "__main__":


pi@raspberrypi:~/PythonProjects/mc-test $ python v6.py 

TX: 00FF000A5820000000000800
Raw response: b'800000000000'
Decoded     : 800000000000
MC header: subheader=80, end_code=00
2025-11-24 07:44:23.594741 X0..X7 = [0, 0, 0, 0, 0, 0, 0, 0]

TX: 02FF000A592000000000010000
Error:  [Errno 111] Connection refused

TX: 00FF000A5920000000000800
Error:  [Errno 111] Connection refused

TX: 02FF000A592000000000010010
Error:  [Errno 111] Connection refused

TX: 00FF000A5920000000000800
Error:  [Errno 111] Connection refused

TX: 01FF000A4420000000000A00
Error:  [Errno 111] Connection refused

TX: 01FF000A4420000000000A00
Raw response: b'8100000A000B000C00000000001A0000000000000000'
Decoded     : 8100000A000B000C00000000001A0000000000000000
MC header: subheader=81, end_code=00

TX: 03FF000A4420000000050100001B
Error:  [Errno 111] Connection refused

TX: 01FF000A4420000000000A00
Error:  [Errno 111] Connection refused

```


```
pi@raspberrypi:~/PythonProjects/mc-test $ cat v4.py 
#!/usr/bin/env python3
import socket
import select
from datetime import datetime
from typing import Dict, List, Sequence, Tuple, Union, Optional


class MCError(RuntimeError):
    """MC protocol or communication error."""
    pass


class FX3U:
    """
    FX3U-16M + FX3U-ENET-L
    MC protocol A-compatible 1E, ASCII.

    Features:
    - Auto-detect "points mode" (normal vs swapped) per (cmd, device).
    - Optional persistent connection for speed (keep_conn=True).
    - Simple high-level methods:
        * read_d / write_d
        * read_x / read_y / write_y
    """

    DEV_D = "4420"  # D register (word)
    DEV_X = "5820"  # X input (bit)
    DEV_Y = "5920"  # Y output (bit)

    # (cmd:int, dev_code:str) -> swap_points:bool
    _POINTS_MODE_CACHE: Dict[Tuple[int, str], bool] = {}

    def __init__(
            self,
            ip: str,
            port: int,
            timeout: float = 1.5,
            keep_conn: bool = True,
            debug: bool = False,
    ):
        """
        ip        : IP address of FX3U-ENET-L (e.g. "192.168.3.254")
        port      : MC protocol port (e.g. 1027)
        timeout   : socket timeout per command (seconds)
        keep_conn : reuse single TCP connection for multiple commands if True
        debug     : print raw TX/RX frames if True
        """
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.keep_conn = keep_conn
        self.debug = debug

        # persistent socket (when keep_conn=True)
        self._sock: Optional[socket.socket] = None

    # ------------------------------------------------------------------
    # Context manager & basic connection management
    # ------------------------------------------------------------------
    def __enter__(self) -> "FX3U":
        if self.keep_conn:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def connect(self, timeout: Optional[float] = None) -> None:
        """
        Open persistent connection (only used when keep_conn=True).
        Safe to call multiple times.
        """
        if not self.keep_conn:
            # per-command connection → do nothing
            return

        if self._sock is not None:
            # already connected
            return

        to = timeout if timeout is not None else self.timeout
        sock = socket.create_connection((self.ip, self.port), timeout=to)
        sock.settimeout(self.timeout)
        self._sock = sock

    def close(self) -> None:
        """Close persistent connection (if any)."""
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    # ------------------------------------------------------------------
    # Low-level send/recv
    # ------------------------------------------------------------------
    def _recv_all_from_sock(self, sock: socket.socket) -> str:
        """
        Receive full ASCII MC response.
        1) Wait for first chunk with normal timeout.
        2) Then use a short "linger" window to collect all remaining bytes.
        """
        try:
            first = sock.recv(4096)
        except socket.timeout:
            raise MCError("Timeout waiting for response from PLC")
        except OSError as e:
            raise MCError(f"Socket recv error: {e}") from e

        if not first:
            raise MCError("Empty response from PLC")

        chunks: List[bytes] = [first]

        # short "linger" to gather any remaining data in the buffer
        short_timeout = 0.2  # ขยายจาก 0.05 → 0.2 เผื่อ PLC ช้า
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
        """
        Send one MC command (ASCII hex string) and return full ASCII response.
        Handles persistent connection or per-command connection.
        """
        if self.debug:
            print(f"TX: {cmd_hex}")

        if self.keep_conn:
            # Ensure connected
            if self._sock is None:
                self.connect()

            assert self._sock is not None
            try:
                self._sock.settimeout(self.timeout)
                self._sock.sendall(cmd_hex.encode("ascii"))
                rx = self._recv_all_from_sock(self._sock)
                if self.debug:
                    print(f"RX: {rx}")
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
                    if self.debug:
                        print(f"RX(retry): {rx}")
                    return rx
                except Exception as e2:
                    self.close()
                    raise MCError(f"Socket error to {self.ip}:{self.port} -> {e2}") from e2
        else:
            # Per-command connection
            try:
                with socket.create_connection((self.ip, self.port), timeout=self.timeout) as sock:
                    sock.settimeout(self.timeout)
                    sock.sendall(cmd_hex.encode("ascii"))
                    rx = self._recv_all_from_sock(sock)
                    if self.debug:
                        print(f"RX: {rx}")
                    return rx
            except OSError as e:
                raise MCError(f"Socket error to {self.ip}:{self.port} -> {e}") from e

    # ------------------------------------------------------------------
    # MC frame building & parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse(rx: str) -> str:
        """
        Parse MC 1E ASCII response.
        Format (ASCII hex):
          - chars[0:2]  : subheader (normally "00")
          - chars[2:4]  : EndCode (00=OK)
          - chars[4:..] : payload
        """
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
        """
        Build MC 1E ASCII command header (without data part).

        cmd       : command code
                    00H = batch read (bit)
                    01H = batch read (word)
                    02H = batch write (bit)
                    03H = batch write (word)
        dev_code  : device code string (e.g. "4420", "5820", "5920")
        head      : device head address (decimal int, will be formatted as 8-digit hex)
        count     : number of points/words
        swap_points: if True, point count bytes are swapped (to handle ENET-L quirk)
        """
        if not (0 <= cmd <= 0xFF):
            raise MCError(f"Invalid cmd: {cmd}")

        # "FF000A" = PC No.=FF, monitor timer=000A (ASCII: 'FF000A')
        header = f"{cmd:02X}FF000A"

        head_hex = f"{head & 0xFFFFFFFF:08X}"

        if not swap_points:
            cnt_hex = f"{count & 0xFFFF:04X}"
        else:
            # Swap low/high bytes of count
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
        """
        Full MC command:
          1) Build header
          2) Append data if any
          3) Auto-try normal / swapped "points" format per (cmd, dev)
          4) Cache working mode in _POINTS_MODE_CACHE
        Return payload string (already EndCode-checked).
        """
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

                # Cache points mode (only when we are in detection stage)
                if name in ("spec", "swap"):
                    self._POINTS_MODE_CACHE[key] = swap

                return payload

            except Exception as e:
                last_err = e
                if name == "cached":
                    # Cached mode failed, clear and retry with spec/swap
                    self._POINTS_MODE_CACHE.pop(key, None)
                    return self._cmd(cmd, dev, head, count, data)

        raise MCError(f"Command failed (both spec/swap modes): {last_err}")

    # ------------------------------------------------------------------
    # D register (word) operations
    # ------------------------------------------------------------------
    def read_d(self, head: int, words: int = 1) -> List[int]:
        """
        Read D registers (word).
        Example: read_d(0, 10) -> [D0..D9]
        """
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
        """
        Write D registers (word).
        values can be:
          - single int  → write_d(10, 1234)
          - sequence    → write_d(10, [1, 2, 3]) → D10, D11, D12
        """
        if isinstance(values, int):
            values = [values]

        vals = list(values)
        if not vals:
            return

        data = "".join(f"{v & 0xFFFF:04X}" for v in vals)
        self._cmd(0x03, self.DEV_D, head, len(vals), data)

    # ------------------------------------------------------------------
    # Bit operations (X/Y)
    # ------------------------------------------------------------------
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
        """
        Read X input bits.
        Example: read_x(0, 8) -> X0..X7
        """
        return self._read_bits(self.DEV_X, head, points)

    def read_y(self, head: int, points: int) -> List[int]:
        """
        Read Y output bits.
        Example: read_y(0, 8) -> Y0..Y7
        """
        return self._read_bits(self.DEV_Y, head, points)

    def write_y(self, head: int, values: Union[Sequence[Union[int, bool]], int, bool]) -> None:
        """
        Write Y output bits.
        values can be:
          - single int/bool → write_y(0, 1) → Y0 = ON
          - sequence        → write_y(0, [1,0,1,1,0,0,0,1]) → Y0..Y7
        """
        if isinstance(values, (int, bool)):
            values = [values]

        vals = [1 if bool(v) else 0 for v in values]
        if not vals:
            return

        # Data: exactly N ASCII '0'/'1' chars (no extra padding)
        data = "".join("1" if v else "0" for v in vals)

        self._cmd(0x02, self.DEV_Y, head, len(vals), data)


def main() -> None:
    with FX3U("192.168.3.254", 1027, timeout=1.5, keep_conn=False, debug=False) as plc:
        # self-test สั้น ๆ เวลา start
        try:
            d0 = plc.read_d(0, 1)[0]
            x0 = plc.read_x(0, 1)[0]
            y0 = plc.read_y(0, 1)[0]
            print("Connected to PLC")
            print("  D0 =", d0, "  X0 =", x0, "  Y0 =", y0)
            print()
        except MCError as e:
            print("MCError on startup:", e)
            return

        while True:
            x_vals = plc.read_x(0, 8)
            print(datetime.now(), "X0..X7 =", x_vals)

            # ปิด Y0..Y7 ทีละบิต
            for i in range(8):
                plc.write_y(i, 0)
                print(datetime.now(), f"Y{i} = 0")

            y_vals = plc.read_y(0, 8)
            print(datetime.now(), "Y0..Y7 =", y_vals)

            # เปิด Y0..Y7 ทีละบิต
            for i in range(8):
                plc.write_y(i, 1)
                print(datetime.now(), f"Y{i} = 1")

            y_vals = plc.read_y(0, 8)
            print(datetime.now(), "Y0..Y7 =", y_vals)

            d_vals = plc.read_d(0, 10)
            print(datetime.now(), "D0..D9 =", d_vals)

            plc.write_d(5, d_vals[5] + 1)
            print()


if __name__ == "__main__":
    main()
pi@raspberrypi:~/PythonProjects/mc-test $ python v4.py 
MCError on startup: Command failed (both spec/swap modes): Socket error to 192.168.3.254:1027 -> [Errno 111] Connection refused
pi@raspberrypi:~/PythonProjects/mc-test $ nano v4.py 
pi@raspberrypi:~/PythonProjects/mc-test $ # change with FX3U("192.168.3.254", 1027, timeout=1.5, keep_conn=True, debug=False) as plc:
pi@raspberrypi:~/PythonProjects/mc-test $ python v4.py 
Connected to PLC
  D0 = 10   X0 = 0   Y0 = 0

2025-11-24 02:08:07.113935 X0..X7 = [0, 0, 0, 0, 0, 0, 0, 0]
Traceback (most recent call last):
  File "/home/pi/PythonProjects/mc-test/v4.py", line 431, in <module>
    main()
    ~~~~^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 409, in main
    plc.write_y(i, 0)
    ~~~~~~~~~~~^^^^^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 386, in write_y
    self._cmd(0x02, self.DEV_Y, head, len(vals), data)
    ~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 291, in _cmd
    raise MCError(f"Command failed (both spec/swap modes): {last_err}")
MCError: Command failed (both spec/swap modes): [Errno 111] Connection refused

```

```
pi@raspberrypi:~/PythonProjects/mc-test $ cat v4.py 
#!/usr/bin/env python3
import socket
import select
from datetime import datetime
from typing import Dict, List, Sequence, Tuple, Union, Optional


class MCError(RuntimeError):
    """MC protocol or communication error."""
    pass


class FX3U:
    """
    FX3U-16M + FX3U-ENET-L
    MC protocol A-compatible 1E, ASCII.

    Features:
    - Auto-detect "points mode" (normal vs swapped) per (cmd, device).
    - Optional persistent connection for speed (keep_conn=True).
    - Simple high-level methods:
        * read_d / write_d
        * read_x / read_y / write_y
    """

    DEV_D = "4420"  # D register (word)
    DEV_X = "5820"  # X input (bit)
    DEV_Y = "5920"  # Y output (bit)

    # (cmd:int, dev_code:str) -> swap_points:bool
    _POINTS_MODE_CACHE: Dict[Tuple[int, str], bool] = {}

    def __init__(
            self,
            ip: str,
            port: int,
            timeout: float = 1.5,
            keep_conn: bool = True,
            debug: bool = False,
    ):
        """
        ip        : IP address of FX3U-ENET-L (e.g. "192.168.3.254")
        port      : MC protocol port (e.g. 1027)
        timeout   : socket timeout per command (seconds)
        keep_conn : reuse single TCP connection for multiple commands if True
        debug     : print raw TX/RX frames if True
        """
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.keep_conn = keep_conn
        self.debug = debug

        # persistent socket (when keep_conn=True)
        self._sock: Optional[socket.socket] = None

    # ------------------------------------------------------------------
    # Context manager & basic connection management
    # ------------------------------------------------------------------
    def __enter__(self) -> "FX3U":
        if self.keep_conn:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def connect(self, timeout: Optional[float] = None) -> None:
        """
        Open persistent connection (only used when keep_conn=True).
        Safe to call multiple times.
        """
        if not self.keep_conn:
            # per-command connection → do nothing
            return

        if self._sock is not None:
            # already connected
            return

        to = timeout if timeout is not None else self.timeout
        sock = socket.create_connection((self.ip, self.port), timeout=to)
        sock.settimeout(self.timeout)
        self._sock = sock

    def close(self) -> None:
        """Close persistent connection (if any)."""
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    # ------------------------------------------------------------------
    # Low-level send/recv
    # ------------------------------------------------------------------
    def _recv_all_from_sock(self, sock: socket.socket) -> str:
        """
        Receive full ASCII MC response.
        1) Wait for first chunk with normal timeout.
        2) Then use a short "linger" window to collect all remaining bytes.
        """
        try:
            first = sock.recv(4096)
        except socket.timeout:
            raise MCError("Timeout waiting for response from PLC")
        except OSError as e:
            raise MCError(f"Socket recv error: {e}") from e

        if not first:
            raise MCError("Empty response from PLC")

        chunks: List[bytes] = [first]

        # short "linger" to gather any remaining data in the buffer
        short_timeout = 0.2  # ขยายจาก 0.05 → 0.2 เผื่อ PLC ช้า
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
        """
        Send one MC command (ASCII hex string) and return full ASCII response.
        Handles persistent connection or per-command connection.
        """
        if self.debug:
            print(f"TX: {cmd_hex}")

        if self.keep_conn:
            # Ensure connected
            if self._sock is None:
                self.connect()

            assert self._sock is not None
            try:
                self._sock.settimeout(self.timeout)
                self._sock.sendall(cmd_hex.encode("ascii"))
                rx = self._recv_all_from_sock(self._sock)
                if self.debug:
                    print(f"RX: {rx}")
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
                    if self.debug:
                        print(f"RX(retry): {rx}")
                    return rx
                except Exception as e2:
                    self.close()
                    raise MCError(f"Socket error to {self.ip}:{self.port} -> {e2}") from e2
        else:
            # Per-command connection
            try:
                with socket.create_connection((self.ip, self.port), timeout=self.timeout) as sock:
                    sock.settimeout(self.timeout)
                    sock.sendall(cmd_hex.encode("ascii"))
                    rx = self._recv_all_from_sock(sock)
                    if self.debug:
                        print(f"RX: {rx}")
                    return rx
            except OSError as e:
                raise MCError(f"Socket error to {self.ip}:{self.port} -> {e}") from e

    # ------------------------------------------------------------------
    # MC frame building & parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse(rx: str) -> str:
        """
        Parse MC 1E ASCII response.
        Format (ASCII hex):
          - chars[0:2]  : subheader (normally "00")
          - chars[2:4]  : EndCode (00=OK)
          - chars[4:..] : payload
        """
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
        """
        Build MC 1E ASCII command header (without data part).

        cmd       : command code
                    00H = batch read (bit)
                    01H = batch read (word)
                    02H = batch write (bit)
                    03H = batch write (word)
        dev_code  : device code string (e.g. "4420", "5820", "5920")
        head      : device head address (decimal int, will be formatted as 8-digit hex)
        count     : number of points/words
        swap_points: if True, point count bytes are swapped (to handle ENET-L quirk)
        """
        if not (0 <= cmd <= 0xFF):
            raise MCError(f"Invalid cmd: {cmd}")

        # "FF000A" = PC No.=FF, monitor timer=000A (ASCII: 'FF000A')
        header = f"{cmd:02X}FF000A"

        head_hex = f"{head & 0xFFFFFFFF:08X}"

        if not swap_points:
            cnt_hex = f"{count & 0xFFFF:04X}"
        else:
            # Swap low/high bytes of count
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
        """
        Full MC command:
          1) Build header
          2) Append data if any
          3) Auto-try normal / swapped "points" format per (cmd, dev)
          4) Cache working mode in _POINTS_MODE_CACHE
        Return payload string (already EndCode-checked).
        """
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

                # Cache points mode (only when we are in detection stage)
                if name in ("spec", "swap"):
                    self._POINTS_MODE_CACHE[key] = swap

                return payload

            except Exception as e:
                last_err = e
                if name == "cached":
                    # Cached mode failed, clear and retry with spec/swap
                    self._POINTS_MODE_CACHE.pop(key, None)
                    return self._cmd(cmd, dev, head, count, data)

        raise MCError(f"Command failed (both spec/swap modes): {last_err}")

    # ------------------------------------------------------------------
    # D register (word) operations
    # ------------------------------------------------------------------
    def read_d(self, head: int, words: int = 1) -> List[int]:
        """
        Read D registers (word).
        Example: read_d(0, 10) -> [D0..D9]
        """
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
        """
        Write D registers (word).
        values can be:
          - single int  → write_d(10, 1234)
          - sequence    → write_d(10, [1, 2, 3]) → D10, D11, D12
        """
        if isinstance(values, int):
            values = [values]

        vals = list(values)
        if not vals:
            return

        data = "".join(f"{v & 0xFFFF:04X}" for v in vals)
        self._cmd(0x03, self.DEV_D, head, len(vals), data)

    # ------------------------------------------------------------------
    # Bit operations (X/Y)
    # ------------------------------------------------------------------
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
        """
        Read X input bits.
        Example: read_x(0, 8) -> X0..X7
        """
        return self._read_bits(self.DEV_X, head, points)

    def read_y(self, head: int, points: int) -> List[int]:
        """
        Read Y output bits.
        Example: read_y(0, 8) -> Y0..Y7
        """
        return self._read_bits(self.DEV_Y, head, points)

    def write_y(self, head: int, values: Union[Sequence[Union[int, bool]], int, bool]) -> None:
        """
        Write Y output bits.
        values can be:
          - single int/bool → write_y(0, 1) → Y0 = ON
          - sequence        → write_y(0, [1,0,1,1,0,0,0,1]) → Y0..Y7
        """
        if isinstance(values, (int, bool)):
            values = [values]

        vals = [1 if bool(v) else 0 for v in values]
        if not vals:
            return

        # Data is string of '0'/'1' characters
        data = "".join("1" if v else "0" for v in vals)

        # If odd number of points, pad one bit (some MC implementations require word alignment)
        if len(data) % 2 == 1:
            data += "0"

        self._cmd(0x02, self.DEV_Y, head, len(vals), data)


def main() -> None:
    with FX3U("192.168.3.254", 1027, timeout=1.5, keep_conn=True, debug=False) as plc:
        # self-test สั้น ๆ เวลา start
        try:
            d0 = plc.read_d(0, 1)[0]
            x0 = plc.read_x(0, 1)[0]
            y0 = plc.read_y(0, 1)[0]
            print("Connected to PLC")
            print("  D0 =", d0, "  X0 =", x0, "  Y0 =", y0)
            print()
        except MCError as e:
            print("MCError on startup:", e)
            return

        while True:
            # อ่าน X0..X7
            x_vals = plc.read_x(0, 8)
            print(datetime.now(), "X0..X7 =", x_vals)

            # ปิด Y0..Y7 ทีละบิต
            for i in range(8):
                plc.write_y(i, 0)
                print(datetime.now(), f"Y{i} = 0")

            y_vals = plc.read_y(0, 8)
            print(datetime.now(), "Y0..Y7 =", y_vals)

            # เปิด Y0..Y7 ทีละบิต
            for i in range(8):
                plc.write_y(i, 1)
                print(datetime.now(), f"Y{i} = 1")

            y_vals = plc.read_y(0, 8)
            print(datetime.now(), "Y0..Y7 =", y_vals)

            # อ่าน D0..D9
            d_vals = plc.read_d(0, 10)
            print(datetime.now(), "D0..D9 =", d_vals)

            # เพิ่มค่า D5 ทีละ 1
            plc.write_d(5, d_vals[5] + 1)

            print()


if __name__ == "__main__":
    main()
pi@raspberrypi:~/PythonProjects/mc-test $ python v4.py 
Connected to PLC
  D0 = 10   X0 = 0   Y0 = 0

2025-11-24 01:54:21.985603 X0..X7 = [0, 0, 0, 0, 0, 0, 0, 0]
Traceback (most recent call last):
  File "/home/pi/PythonProjects/mc-test/v4.py", line 439, in <module>
    main()
    ~~~~^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 414, in main
    plc.write_y(i, 0)
    ~~~~~~~~~~~^^^^^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 390, in write_y
    self._cmd(0x02, self.DEV_Y, head, len(vals), data)
    ~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 291, in _cmd
    raise MCError(f"Command failed (both spec/swap modes): {last_err}")
MCError: Command failed (both spec/swap modes): [Errno 111] Connection refused
```

```
i@raspberrypi:~/PythonProjects/mc-test $ python v4.py 
MCError on startup: Command failed (both spec/swap modes): Socket error to 192.168.3.254:1027 -> [Errno 111] Connection refused
```

```
pi@raspberrypi:~/PythonProjects/mc-test $ cat v4.py 
import socket
import select
from datetime import datetime
from typing import Dict, List, Sequence, Tuple, Union, Optional


class MCError(RuntimeError):
    """MC protocol or communication error."""
    pass


class FX3U:
    """
    FX3U-16M + FX3U-ENET-L
    MC protocol A-compatible 1E, ASCII.

    Features:
    - Auto-detect "points mode" (normal vs swapped) per (cmd, device).
    - Optional persistent connection for speed (keep_conn=True).
    - Simple high-level methods:
        * read_d / write_d
        * read_x / read_y / write_y
    """

    DEV_D = "4420"  # D register (word)
    DEV_X = "5820"  # X input (bit)
    DEV_Y = "5920"  # Y output (bit)

    # (cmd:int, dev_code:str) -> swap_points:bool
    _POINTS_MODE_CACHE: Dict[Tuple[int, str], bool] = {}

    def __init__(
            self,
            ip: str,
            port: int,
            timeout: float = 1.5,
            keep_conn: bool = True,
            debug: bool = False,
    ):
        """
        ip        : IP address of FX3U-ENET-L (e.g. "192.168.3.254")
        port      : MC protocol port (e.g. 1027)
        timeout   : socket timeout per command (seconds)
        keep_conn : reuse single TCP connection for multiple commands if True
        debug     : print raw TX/RX frames if True
        """
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.keep_conn = keep_conn
        self.debug = debug

        # persistent socket (when keep_conn=True)
        self._sock: Optional[socket.socket] = None

    # ------------------------------------------------------------------
    # Context manager & basic connection management
    # ------------------------------------------------------------------
    def __enter__(self) -> "FX3U":
        if self.keep_conn:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def connect(self, timeout: Optional[float] = None) -> None:
        """
        Open persistent connection (only used when keep_conn=True).
        Safe to call multiple times.
        """
        if not self.keep_conn:
            # per-command connection → do nothing
            return

        if self._sock is not None:
            # already connected
            return

        to = timeout if timeout is not None else self.timeout
        sock = socket.create_connection((self.ip, self.port), timeout=to)
        sock.settimeout(self.timeout)
        self._sock = sock

    def close(self) -> None:
        """Close persistent connection (if any)."""
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    # ------------------------------------------------------------------
    # Low-level send/recv
    # ------------------------------------------------------------------
    def _recv_all_from_sock(self, sock: socket.socket) -> str:
        """
        Receive full ASCII MC response.
        1) Wait for first chunk with normal timeout.
        2) Then use a short "linger" window to collect all remaining bytes.
        """
        try:
            first = sock.recv(4096)
        except socket.timeout:
            raise MCError("Timeout waiting for response from PLC")
        except OSError as e:
            raise MCError(f"Socket recv error: {e}") from e

        if not first:
            raise MCError("Empty response from PLC")

        chunks: List[bytes] = [first]

        # short "linger" to gather any remaining data in the buffer
        short_timeout = 0.2  # ขยายจาก 0.05 → 0.2 เผื่อ PLC ช้า
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
        """
        Send one MC command (ASCII hex string) and return full ASCII response.
        Handles persistent connection or per-command connection.
        """
        if self.debug:
            print(f"TX: {cmd_hex}")

        if self.keep_conn:
            # Ensure connected
            if self._sock is None:
                self.connect()

            assert self._sock is not None
            try:
                self._sock.settimeout(self.timeout)
                self._sock.sendall(cmd_hex.encode("ascii"))
                rx = self._recv_all_from_sock(self._sock)
                if self.debug:
                    print(f"RX: {rx}")
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
                    if self.debug:
                        print(f"RX(retry): {rx}")
                    return rx
                except Exception as e2:
                    self.close()
                    raise MCError(f"Socket error to {self.ip}:{self.port} -> {e2}") from e2
        else:
            # Per-command connection
            try:
                with socket.create_connection((self.ip, self.port), timeout=self.timeout) as sock:
                    sock.settimeout(self.timeout)
                    sock.sendall(cmd_hex.encode("ascii"))
                    rx = self._recv_all_from_sock(sock)
                    if self.debug:
                        print(f"RX: {rx}")
                    return rx
            except OSError as e:
                raise MCError(f"Socket error to {self.ip}:{self.port} -> {e}") from e

    # ------------------------------------------------------------------
    # MC frame building & parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse(rx: str) -> str:
        """
        Parse MC 1E ASCII response.
        Format (ASCII hex):
          - chars[0:2]  : subheader (normally "00")
          - chars[2:4]  : EndCode (00=OK)
          - chars[4:..] : payload
        """
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
        """
        Build MC 1E ASCII command header (without data part).

        cmd       : command code
                    00H = batch read (bit)
                    01H = batch read (word)
                    02H = batch write (bit)
                    03H = batch write (word)
        dev_code  : device code string (e.g. "4420", "5820", "5920")
        head      : device head address (decimal int, will be formatted as 8-digit hex)
        count     : number of points/words
        swap_points: if True, point count bytes are swapped (to handle ENET-L quirk)
        """
        if not (0 <= cmd <= 0xFF):
            raise MCError(f"Invalid cmd: {cmd}")

        # "FF000A" = PC No.=FF, monitor timer=000A (ASCII: 'FF000A')
        header = f"{cmd:02X}FF000A"

        head_hex = f"{head & 0xFFFFFFFF:08X}"

        if not swap_points:
            cnt_hex = f"{count & 0xFFFF:04X}"
        else:
            # Swap low/high bytes of count
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
        """
        Full MC command:
          1) Build header
          2) Append data if any
          3) Auto-try normal / swapped "points" format per (cmd, dev)
          4) Cache working mode in _POINTS_MODE_CACHE
        Return payload string (already EndCode-checked).
        """
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

                # Cache points mode (only when we are in detection stage)
                if name in ("spec", "swap"):
                    self._POINTS_MODE_CACHE[key] = swap

                return payload

            except Exception as e:
                last_err = e
                if name == "cached":
                    # Cached mode failed, clear and retry with spec/swap
                    self._POINTS_MODE_CACHE.pop(key, None)
                    return self._cmd(cmd, dev, head, count, data)

        raise MCError(f"Command failed (both spec/swap modes): {last_err}")

    # ------------------------------------------------------------------
    # D register (word) operations
    # ------------------------------------------------------------------
    def read_d(self, head: int, words: int = 1) -> List[int]:
        """
        Read D registers (word).
        Example: read_d(0, 10) -> [D0..D9]
        """
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
        """
        Write D registers (word).
        values can be:
          - single int  → write_d(10, 1234)
          - sequence    → write_d(10, [1, 2, 3]) → D10, D11, D12
        """
        if isinstance(values, int):
            values = [values]

        vals = list(values)
        if not vals:
            return

        data = "".join(f"{v & 0xFFFF:04X}" for v in vals)
        self._cmd(0x03, self.DEV_D, head, len(vals), data)

    # ------------------------------------------------------------------
    # Bit operations (X/Y)
    # ------------------------------------------------------------------
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
        """
        Read X input bits.
        Example: read_x(0, 8) -> X0..X7
        """
        return self._read_bits(self.DEV_X, head, points)

    def read_y(self, head: int, points: int) -> List[int]:
        """
        Read Y output bits.
        Example: read_y(0, 8) -> Y0..Y7
        """
        return self._read_bits(self.DEV_Y, head, points)

    def write_y(self, head: int, values: Union[Sequence[Union[int, bool]], int, bool]) -> None:
        """
        Write Y output bits.
        values can be:
          - single int/bool → write_y(0, 1) → Y0 = ON
          - sequence        → write_y(0, [1,0,1,1,0,0,0,1]) → Y0..Y7
        """
        if isinstance(values, (int, bool)):
            values = [values]

        vals = [1 if bool(v) else 0 for v in values]
        if not vals:
            return

        # Data is string of '0'/'1' characters
        data = "".join("1" if v else "0" for v in vals)

        # If odd number of points, pad one bit (some MC implementations require word alignment)
        if len(data) % 2 == 1:
            data += "0"

        self._cmd(0x02, self.DEV_Y, head, len(vals), data)


def main() -> None:
    # ใช้งานจริง: เปิด keep_conn, ปิด debug
    with FX3U("192.168.3.254", 1027, timeout=1.5, keep_conn=True, debug=False) as plc:
        # self-test สั้น ๆ เวลา start
        try:
            d0 = plc.read_d(0, 1)[0]
            x0 = plc.read_x(0, 1)[0]
            y0 = plc.read_y(0, 1)[0]
            print("Connected to PLC")
            print("  D0 =", d0, "  X0 =", x0, "  Y0 =", y0)
            print()
        except MCError as e:
            print("MCError on startup:", e)
            return

        while True:
            # อ่าน X0..X7
            x_vals = plc.read_x(0, 8)
            print(datetime.now(), "X0..X7 =", x_vals)

            # ปิด Y0..Y7 ทีละบิต
            for i in range(8):
                plc.write_y(i, 0)
                print(datetime.now(), f"Y{i} = 0")

            y_vals = plc.read_y(0, 8)
            print(datetime.now(), "Y0..Y7 =", y_vals)

            # เปิด Y0..Y7 ทีละบิต
            for i in range(8):
                plc.write_y(i, 1)
                print(datetime.now(), f"Y{i} = 1")

            y_vals = plc.read_y(0, 8)
            print(datetime.now(), "Y0..Y7 =", y_vals)

            # อ่าน D0..D9
            d_vals = plc.read_d(0, 10)
            print(datetime.now(), "D0..D9 =", d_vals)

            # เพิ่มค่า D5 ทีละ 1
            plc.write_d(5, d_vals[5] + 1)

            print()


main()
pi@raspberrypi:~/PythonProjects/mc-test $ 
pi@raspberrypi:~/PythonProjects/mc-test $ python v4.py 
Traceback (most recent call last):
  File "/home/pi/PythonProjects/mc-test/v4.py", line 438, in <module>
    main()
    ~~~~^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 394, in main
    with FX3U("192.168.3.254", 1027, timeout=1.5, keep_conn=True, debug=False) as plc:
         ~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 61, in __enter__
    self.connect()
    ~~~~~~~~~~~~^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 81, in connect
    sock = socket.create_connection((self.ip, self.port), timeout=to)
  File "/usr/lib/python3.13/socket.py", line 864, in create_connection
    raise exceptions[0]
  File "/usr/lib/python3.13/socket.py", line 849, in create_connection
    sock.connect(sa)
    ~~~~~~~~~~~~^^^^
OSError: [Errno 101] Network is unreachable

```

```
pi@raspberrypi:~/PythonProjects/mc-test $ python v4.py 
Connected to PLC
  D0 = 10   X0 = 0   Y0 = 1

2025-11-22 09:15:55.009302 X0..X7 = [0, 0, 0, 0, 0, 0, 0, 0]
Traceback (most recent call last):
  File "/home/pi/PythonProjects/mc-test/v4.py", line 438, in <module>
    main()
    ~~~~^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 414, in main
    plc.write_y(i, 0)
    ~~~~~~~~~~~^^^^^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 389, in write_y
    self._cmd(0x02, self.DEV_Y, head, len(vals), data)
    ~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/PythonProjects/mc-test/v4.py", line 290, in _cmd
    raise MCError(f"Command failed (both spec/swap modes): {last_err}")
MCError: Command failed (both spec/swap modes): [Errno 111] Connection refused

```

```
pi@raspberrypi:~/PythonProjects/mc-test $ python test_socket.py 
Connecting to 192.168.3.254:1027 ...
OK: TCP connected
```

```
pi@raspberrypi:~/PythonProjects/mc-test $ ping 192.168.3.254
PING 192.168.3.254 (192.168.3.254) 56(84) bytes of data.
64 bytes from 192.168.3.254: icmp_seq=1 ttl=250 time=1.75 ms
64 bytes from 192.168.3.254: icmp_seq=2 ttl=250 time=1.20 ms
64 bytes from 192.168.3.254: icmp_seq=3 ttl=250 time=1.26 ms
64 bytes from 192.168.3.254: icmp_seq=4 ttl=250 time=1.19 ms
64 bytes from 192.168.3.254: icmp_seq=5 ttl=250 time=1.19 ms
64 bytes from 192.168.3.254: icmp_seq=6 ttl=250 time=1.19 ms
64 bytes from 192.168.3.254: icmp_seq=7 ttl=250 time=1.20 ms
64 bytes from 192.168.3.254: icmp_seq=8 ttl=250 time=1.19 ms
64 bytes from 192.168.3.254: icmp_seq=9 ttl=250 time=1.19 ms
64 bytes from 192.168.3.254: icmp_seq=10 ttl=250 time=1.20 ms
^C
--- 192.168.3.254 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9016ms
rtt min/avg/max/mdev = 1.187/1.256/1.752/0.166 ms
pi@raspberrypi:~/PythonProjects/mc-test $ ^C
pi@raspberrypi:~/PythonProjects/mc-test $ nmap -p 1027 192.168.3.254
Starting Nmap 7.95 ( https://nmap.org ) at 2025-11-22 08:56 GMT
Nmap scan report for 192.168.3.254
Host is up (0.0019s latency).

PORT     STATE SERVICE
1027/tcp open  IIS

Nmap done: 1 IP address (1 host up) scanned in 0.15 seconds
pi@raspberrypi:~/PythonProjects/mc-test $ python v3.py 
Traceback (most recent call last):
  File "/home/pi/PythonProjects/mc-test/v3.py", line 414, in <module>
    main()
    ~~~~^^
  File "/home/pi/PythonProjects/mc-test/v3.py", line 375, in main
    plc.write_y(0,plc.read_y(0, 1))
    ~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/PythonProjects/mc-test/v3.py", line 365, in write_y
    self._cmd(0x02, self.DEV_Y, head, len(vals), data)
    ~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/PythonProjects/mc-test/v3.py", line 266, in _cmd
    raise MCError(f"Command failed (both spec/swap modes): {last_err}")
MCError: Command failed (both spec/swap modes): [Errno 111] Connection refused
```

```
pi@raspberrypi:~/PythonProjects/mc-test $ ifconfig
eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 192.168.3.1  netmask 255.255.255.0  broadcast 192.168.3.255
        inet6 fe80::62ef:1243:9097:d0c2  prefixlen 64  scopeid 0x20<link>
        ether 88:a2:9e:38:b9:3d  txqueuelen 1000  (Ethernet)
        RX packets 22  bytes 2100 (2.0 KiB)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 303  bytes 51189 (49.9 KiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
        device interrupt 113  

lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536
        inet 127.0.0.1  netmask 255.0.0.0
        inet6 ::1  prefixlen 128  scopeid 0x10<host>
        loop  txqueuelen 1000  (Local Loopback)
        RX packets 1024  bytes 85769 (83.7 KiB)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 1024  bytes 85769 (83.7 KiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

wlan0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 10.133.70.248  netmask 255.255.255.0  broadcast 10.133.70.255
        inet6 fe80::ad8f:3485:e395:8287  prefixlen 64  scopeid 0x20<link>
        ether 88:a2:9e:38:b9:3e  txqueuelen 1000  (Ethernet)
        RX packets 49  bytes 13793 (13.4 KiB)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 95  bytes 12519 (12.2 KiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

pi@raspberrypi:~/PythonProjects/mc-test $ python v3.py 
Traceback (most recent call last):
  File "/home/pi/PythonProjects/mc-test/v3.py", line 414, in <module>
    main()
    ~~~~^^
  File "/home/pi/PythonProjects/mc-test/v3.py", line 375, in main
    plc.write_y(0,plc.read_y(0, 1))
    ~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/PythonProjects/mc-test/v3.py", line 365, in write_y
    self._cmd(0x02, self.DEV_Y, head, len(vals), data)
    ~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/PythonProjects/mc-test/v3.py", line 266, in _cmd
    raise MCError(f"Command failed (both spec/swap modes): {last_err}")
MCError: Command failed (both spec/swap modes): [Errno 111] Connection refused
```
