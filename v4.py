# v4.py
# FX3U-16M + FX3U-ENET-L (MC protocol A-compatible 1E, ASCII)
# Class-based wrapper using the same stable logic as t2.py
# Works on both Windows PC and Raspberry Pi

import socket
from datetime import datetime
from typing import List, Sequence, Union, Optional


class MCError(RuntimeError):
    """MC protocol or communication error."""
    pass


class FX3U:
    """
    FX3U-16M + FX3U-ENET-L
    MC protocol A-compatible 1E, ASCII.

    Features:
    - Per-command TCP connection (most stable for ENET-L).
    - Simple high-level methods:
        * read_d / write_d
        * read_x / read_y / write_y
    """

    DEV_D = "4420"  # D register (word)
    DEV_X = "5820"  # X input (bit)
    DEV_Y = "5920"  # Y output (bit)

    def __init__(
        self,
        ip: str,
        port: int,
        timeout: float = 1.5,
        debug: bool = False,
    ):
        """
        ip      : IP address of FX3U-ENET-L (e.g. "192.168.3.254")
        port    : MC protocol port (e.g. 1027)
        timeout : socket timeout per command (seconds)
        debug   : print raw TX/RX frames if True
        """
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.debug = debug

    # ------------------------------------------------------------------
    # Low-level: TCP exchange (per-command connection)
    # ------------------------------------------------------------------
    def _exchange(self, cmd_hex: str) -> str:
        """
        Send one MC ASCII command (hex string) and return decoded ASCII reply.
        Opens a new TCP connection per command (most stable for ENET-L).
        """
        if self.debug:
            print(f"TX: {cmd_hex}")

        try:
            with socket.create_connection((self.ip, self.port), timeout=self.timeout) as sock:
                sock.sendall(cmd_hex.encode("ascii"))
                data = sock.recv(4096)
        except OSError as e:
            raise MCError(f"Socket error to {self.ip}:{self.port} -> {e}") from e

        if not data:
            raise MCError("Empty response from PLC")

        rx = data.decode("ascii", errors="ignore").strip()

        if self.debug:
            print(f"RX: {rx}")

        return rx

    # ------------------------------------------------------------------
    # MC frame building & parsing (same behavior as t2.py)
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_mc_payload(rx: str, expect_ok: bool = True) -> str:
        """
        Parse MC 1E ASCII response.
        Format (ASCII hex):
          - chars[0:2]  : subheader (normally "00")
          - chars[2:4]  : EndCode (00=OK)
          - chars[4:..] : payload
        """
        if len(rx) < 4:
            raise MCError(f"Response too short: {rx!r}")

        subheader = rx[0:2]
        end_code = rx[2:4]

        if expect_ok and end_code != "00":
            raise MCError(f"MC protocol error, end_code=0x{end_code}, raw={rx!r}")

        return rx[4:]

    @staticmethod
    def _build_1e_cmd(
        cmd: int,
        dev_code: str,
        head: int,
        points: int,
    ) -> str:
        """
        Build MC 1E ASCII command header (without data part).

        ใช้รูปแบบเดียวกับ t2.py:
        - header = "{cmd:02X}FF000A"
        - head   = 8-digit hex
        - points = low/high byte สลับกัน เช่น 1 -> "0100"
        """
        if not (0 <= cmd <= 0xFF):
            raise MCError(f"Invalid cmd: {cmd}")

        header = f"{cmd:02X}FF000A"      # cmd, PC=FF, timer=000A
        head_hex = f"{head & 0xFFFFFFFF:08X}"

        # Force low/high byte order (e.g. 0005 -> 0500) – same as t2.py
        lo = points & 0xFF
        hi = (points >> 8) & 0xFF
        pts_hex = f"{lo:02X}{hi:02X}"

        return header + dev_code + head_hex + pts_hex

    def _cmd(
        self,
        cmd: int,
        dev_code: str,
        head: int,
        points: int,
        data_field: Optional[str] = None,
    ) -> str:
        """
        Build and execute command with the fixed format (t2.py style), returns payload.
        """
        cmd_hex = self._build_1e_cmd(cmd, dev_code, head, points)
        if data_field:
            cmd_hex += data_field

        rx = self._exchange(cmd_hex)
        payload = self._parse_mc_payload(rx, expect_ok=True)
        return payload

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

        # cmd 0x01 = batch read / word units
        payload = self._cmd(0x01, self.DEV_D, head, words)

        expected_len = words * 4  # 4 hex chars per word
        if len(payload) < expected_len:
            raise MCError(
                f"Not enough word data, expected {expected_len} chars, "
                f"got {len(payload)}, payload={payload!r}"
            )

        vals: List[int] = []
        for i in range(words):
            s = payload[i * 4: i * 4 + 4]
            vals.append(int(s, 16))

        return vals

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

        data_field = "".join(f"{v & 0xFFFF:04X}" for v in vals)

        # cmd 0x03 = batch write / word units
        self._cmd(0x03, self.DEV_D, head, len(vals), data_field=data_field)

    # ------------------------------------------------------------------
    # Bit operations (X/Y)
    # ------------------------------------------------------------------
    def _read_bits(self, dev_code: str, head: int, points: int) -> List[int]:
        if points <= 0:
            return []

        # cmd 0x00 = batch read / bit units
        payload = self._cmd(0x00, dev_code, head, points)

        if len(payload) < points:
            raise MCError(
                f"Not enough bit data, expected {points}, "
                f"got {len(payload)}, payload={payload!r}"
            )

        bits = [1 if c == "1" else 0 for c in payload[:points]]
        return bits

    def read_x(self, head: int, points: int) -> List[int]:
        """
        Read X input bits.
        หมายเหตุ: X/Y เป็นเลขฐาน 8 ในโปรแกรม PLC
        - ถ้าอยากอ่าน X0..X7      -> read_x(0, 8)
        - ถ้าอยากอ่าน X20(octal)  -> read_x(int("20", 8), 8)
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
        points = len(vals)
        if points == 0:
            return

        data_chars = "".join("1" if v else "0" for v in vals)
        if points % 2 == 1:
            # dummy bit ให้เป็นเลขคู่ เหมือน t2.py
            data_chars += "0"

        # cmd 0x02 = batch write / bit units
        self._cmd(0x02, self.DEV_Y, head, points, data_field=data_chars)


if __name__ == "__main__":
    import time

    plc_ip = "192.168.3.254"
    plc_port = 1027

    plc = FX3U(plc_ip, plc_port, timeout=1.5, debug=False)

    try:
        # อ่าน X0..X7
        try:
            x_vals = plc.read_x(0, 8)
            print(datetime.now(), "X0..X7 =", x_vals)
        except MCError as e:
            print("MCError reading X0..X7:", e)
        time.sleep(1)

        # ปิด Y0..Y7 ทีละบิต
        try:
            for i in range(8):
                plc.write_y(i, 0)
                print(datetime.now(), f"Y{i} = 0")
        except MCError as e:
            print("MCError writing Y0..Y7 (OFF loop):", e)
        time.sleep(1)

        # อ่าน Y0..Y7
        try:
            y_vals = plc.read_y(0, 8)
            print(datetime.now(), "Y0..Y7 =", y_vals)
        except MCError as e:
            print("MCError reading Y0..Y7:", e)
        time.sleep(1)

        # เปิด Y0..Y7 ทีละบิต
        try:
            for i in range(8):
                plc.write_y(i, 1)
                print(datetime.now(), f"Y{i} = 1")
        except MCError as e:
            print("MCError writing Y0..Y7 (ON loop):", e)
        time.sleep(1)

        # อ่าน Y0..Y7 อีกครั้ง
        try:
            y_vals = plc.read_y(0, 8)
            print(datetime.now(), "Y0..Y7 =", y_vals)
        except MCError as e:
            print("MCError reading Y0..Y7:", e)
        time.sleep(1)

        # อ่าน D0..D9
        try:
            d_vals = plc.read_d(0, 10)
            print(datetime.now(), "D0..D9 =", d_vals)
        except MCError as e:
            print("MCError reading D0..D9:", e)
        time.sleep(1)

        # เขียน D5 = D5+1
        try:
            d_vals = plc.read_d(0, 10)
            new_val = d_vals[5] + 1
            plc.write_d(5, new_val)
            print(datetime.now(), "Wrote D5 =", new_val)
        except MCError as e:
            print("MCError writing D5:", e)
        time.sleep(1)

        # อ่าน D0..D9 อีกครั้ง
        try:
            d_vals = plc.read_d(0, 10)
            print(datetime.now(), "D0..D9 =", d_vals)
        except MCError as e:
            print("MCError reading D0..D9:", e)

    finally:
        # ไม่มี persistent socket เลย ไม่ต้อง close อะไรเพิ่ม
        pass
