import socket
import time
from typing import List, Sequence
from datetime import datetime


class FX3U:
    DEV_D = "4420"  # D registers
    DEV_X = "5820"  # X inputs
    DEV_Y = "5920"  # Y outputs

    def __init__(self, ip: str, port: int = 1027, timeout: float = 2.0):
        self.PLC_IP = ip
        self.PLC_PORT = port
        self.TIMEOUT = timeout
        # print(f"FX3U instance created for {self.PLC_IP}:{self.PLC_PORT}")

    # --------- low-level helpers (private methods) ---------

    def _exchange(self, cmd_hex: str) -> str:
        """Send one MC ASCII command (hex string) and return decoded ASCII reply."""
        # print(f"TX: {cmd_hex}")
        with socket.create_connection((self.PLC_IP, self.PLC_PORT), timeout=self.TIMEOUT) as sock:
            sock.sendall(cmd_hex.encode("ascii"))
            data = sock.recv(4096)

        rx = data.decode("ascii", errors="ignore").strip()
        # print("Decoded     :", rx)
        return rx

    def _parse_mc_payload(self, rx: str, expect_ok: bool = True) -> str:
        """
        Common parser: returns payload (after 4 chars) when end_code == '00'.
        """
        if len(rx) < 4:
            raise RuntimeError(f"Response too short: {rx!r}")

        # subheader = rx[0:2] # Not needed for return value
        end_code = rx[2:4]

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
        """
        Build A-compatible 1E ASCII frame using low/high byte order (…PPHH).
        """
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
        """
        Build and execute command with the fixed format, returns payload.
        """
        cmd_hex = self._build_1e_cmd(cmd, dev_code, head, points)
        if data_field:
            cmd_hex += data_field

        rx = self._exchange(cmd_hex)
        payload = self._parse_mc_payload(rx, expect_ok=True)
        return payload

    # --------- bit devices: X / Y (private helpers) ---------

    def _read_bits(self, dev_code: str, head: int, points: int) -> List[int]:
        """Generic bit-device batch read (command 0x00)."""
        if points <= 0:
            return []

        payload = self._execute_cmd(0x00, dev_code, head, points)

        if len(payload) < points:
            raise RuntimeError(f"Not enough bit data, payload={payload!r}")

        bits = [1 if c == "1" else 0 for c in payload[:points]]
        return bits

    def _write_bits(self, dev_code: str, head: int, values: Sequence[int | bool]) -> None:
        """Generic bit-device batch write (command 0x02)."""
        vals = [1 if bool(v) else 0 for v in values]
        points = len(vals)
        if points == 0:
            return

        data_chars = "".join("1" if v else "0" for v in vals)
        if points % 2 == 1:
            data_chars += "0"  # dummy

        self._execute_cmd(0x02, dev_code, head, points, data_field=data_chars)

    # --------- public APIs ---------

    def read_x(self, head: int, points: int = 1) -> List[int]:
        """Read X[head] .. X[head+points-1] (bit units)."""
        return self._read_bits(self.DEV_X, head, points)

    def read_y(self, head: int, points: int = 1) -> List[int]:
        """Read Y[head] .. Y[head+points-1] (bit units)."""
        return self._read_bits(self.DEV_Y, head, points)

    def write_y(self, head: int, values: Sequence[int | bool] | int | bool) -> None:
        """Write to Y devices (bit units). Accepts single value or sequence."""
        if isinstance(values, (int, bool)):
            vals_seq = [values]
        else:
            vals_seq = list(values)
        self._write_bits(self.DEV_Y, head, vals_seq)

    def read_d(self, head: int, words: int = 1) -> List[int]:
        """Read D registers (word units)."""
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
        """Write to D registers (word units). Accepts single value or sequence."""
        if isinstance(values, int):
            values = [values]

        words = len(values)
        if words <= 0:
            return

        data_field = "".join(f"{v & 0xFFFF:04X}" for v in values)
        self._execute_cmd(0x03, self.DEV_D, head, words, data_field=data_field)


if __name__ == "__main__":
    plc = FX3U("192.168.3.254", 1027)

    try:
        x_vals = plc.read_x(0, 8)
        print(datetime.now(), "X0..X7 =", x_vals)
    except Exception as e:
        print("Error reading X0..X7:", e)
    time.sleep(0.5)

    try:
        print("\n--- Turning off Y0..Y7 bit by bit ---")
        # ปิด Y0..Y7 ทีละบิต
        for i in range(8):
            plc.write_y(i, 0)
            # print(datetime.now(), f"Y{i} = 0") # Optional logging for every step
    except Exception as e:
        print("Error writing Y0..Y7:", e)
    time.sleep(0.5)

    try:
        y_vals = plc.read_y(0, 8)
        print(datetime.now(), "Y0..Y7 (After OFF) =", y_vals)
    except Exception as e:
        print("Error reading Y0..Y7:", e)
    time.sleep(0.5)

    try:
        print("\n--- Turning on Y0..Y7 bit by bit ---")
        # เปิด Y0..Y7 ทีละบิต
        for i in range(8):
            plc.write_y(i, 1)
            # print(datetime.now(), f"Y{i} = 1") # Optional logging
    except Exception as e:
        print("Error writing Y0..Y7:", e)
    time.sleep(0.5)

    try:
        y_vals = plc.read_y(0, 8)
        print(datetime.now(), "Y0..Y7 (After ON) =", y_vals)
    except Exception as e:
        print("Error reading Y0..Y7:", e)
    time.sleep(0.5)

    initial_d_vals = []
    try:
        d_vals = plc.read_d(0, 10)
        initial_d_vals = d_vals  # store them for later use
        print(datetime.now(), "D0..D9 =", d_vals)
    except Exception as e:
        print("Error reading D0..D9:", e)
    time.sleep(0.5)

    try:
        if initial_d_vals:
            new_d5_value = initial_d_vals[5] + 1
            plc.write_d(5, new_d5_value)
            print(datetime.now(), "Wrote D5 =", new_d5_value)
        else:
            print("Skipping D5 write because initial D read failed.")
    except Exception as e:
        print("Error writing D5:", e)
    time.sleep(0.5)

    try:
        d_vals = plc.read_d(0, 10)
        print(datetime.now(), "D0..D9 =", d_vals)
    except Exception as e:
        print("Error reading D0..D9:", e)

    print("\n--- Test Finished ---")
