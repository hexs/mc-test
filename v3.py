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

    def __init__(self, ip: str, port: int, timeout: float = 1.5, keep_conn: bool = True):
        """
        ip        : IP address of FX3U-ENET-L (e.g. "192.168.3.254")
        port      : MC protocol port (e.g. 1027)
        timeout   : socket timeout per command (seconds)
        keep_conn : reuse single TCP connection for multiple commands if True
        """
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.keep_conn = keep_conn

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
            # per-command connection mode → do nothing
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
        short_timeout = 0.05
        while True:
            r, _, _ = select.select([sock], [], [], short_timeout)
            if not r:
                break
            try:
                part = sock.recv(4096)
            except socket.timeout:
                # treat as "no more data"
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
        if self.keep_conn:
            # Ensure connected
            if self._sock is None:
                self.connect()

            assert self._sock is not None
            try:
                self._sock.settimeout(self.timeout)
                self._sock.sendall(cmd_hex.encode("ascii"))
                return self._recv_all_from_sock(self._sock)
            except (OSError, MCError) as e:
                # Try to recover by re-opening connection once
                try:
                    self.close()
                    self.connect()
                    assert self._sock is not None
                    self._sock.settimeout(self.timeout)
                    self._sock.sendall(cmd_hex.encode("ascii"))
                    return self._recv_all_from_sock(self._sock)
                except Exception as e2:
                    self.close()
                    raise MCError(f"Socket error to {self.ip}:{self.port} -> {e2}") from e2
        else:
            # Per-command connection (more stable in some environments)
            try:
                with socket.create_connection((self.ip, self.port), timeout=self.timeout) as sock:
                    sock.settimeout(self.timeout)
                    sock.sendall(cmd_hex.encode("ascii"))
                    return self._recv_all_from_sock(sock)
            except OSError as e:
                raise MCError(f"Socket error to {self.ip}:{self.port} -> {e}") from e

    # ------------------------------------------------------------------
    # MC frame building & parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse(rx: str) -> str:
        """
        Parse MC 1E ASCII response.
        rx example: '00' + '00' + data...
          - First 2 chars: subheader (often "00")
          - Next 2 chars: EndCode (00=OK)
        Return payload (data part).
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

        cmd       : command code (0x00 bit-read, 0x01 word-read, 0x02 bit-write, 0x03 word-write)
        dev_code  : device code string (e.g. "4420", "5820", "5920")
        head      : device head address (decimal int, will be formatted as 8-digit hex)
        count     : number of points/words
        swap_points: if True, point count bytes are swapped (to handle ENET-L quirk)
        """
        if not (0 <= cmd <= 0xFF):
            raise MCError(f"Invalid cmd: {cmd}")

        # "FF000A" = station no. FF, wait-time 0, monitor timer 0x000A
        header = f"{cmd:02X}FF000A"

        head_hex = f"{head & 0xFFFFFFFF:08X}"

        if not swap_points:
            cnt_hex = f"{count & 0xFFFF:04X}"
        else:
            # Swap low/high bytes of count (some units expect this)
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


# ----------------------------------------------------------------------
# Example usage
# ----------------------------------------------------------------------
def main() -> None:
    plc = FX3U("192.168.3.254", 1027, timeout=1.5, keep_conn=True)

    plc.read_x(0, 1)
    plc.write_y(0,plc.read_y(0, 1))
    plc.write_d(0, plc.read_d(0, 1))

    try:
        while True:
            # อ่าน X0..X7
            x_vals = plc.read_x(0, 8)
            print(datetime.now(), "X0..X7 =", x_vals)

            # ปิด Y0..Y7 ทีละบิต
            for i in range(8):
                plc.write_y(i, 0)
                print(datetime.now(), f"Y{i} = 0")

            y_vals = plc.read_y(0, 8)  # Y0..Y7
            print(datetime.now(), "Y0..Y7 =", y_vals)

            # เปิด Y0..Y7 ทีละบิต
            for i in range(8):
                plc.write_y(i, 1)
                print(datetime.now(), f"Y{i} = 1")

            y_vals = plc.read_y(0, 8)  # Y0..Y7
            print(datetime.now(), "Y0..Y7 =", y_vals)

            # อ่าน D0..D9 (10 words)
            vals = plc.read_d(0, 10)
            print(datetime.now(), "D0..D9 =", vals)

            # เพิ่มค่า D5 ทีละ 1
            plc.write_d(5, vals[5] + 1)

            print()

    finally:
        plc.close()


if __name__ == "__main__":
    main()
