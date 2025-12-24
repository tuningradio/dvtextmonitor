import serial
from datetime import datetime, timezone, timedelta
import time
import sys
import os

# 送信入力を別スレッドで安全に扱う
import threading
import queue

# バージョン表示用
VERSION = "DV text monitor Ver 3.3 by JA1XPM"

# ==== シリアル設定 ====
SERIAL_PORT = 'COM1'
BAUD_RATE = 9600
PARITY = serial.PARITY_NONE
BYTESIZE = serial.EIGHTBITS
STOPBITS = serial.STOPBITS_ONE
TIMEOUT = 0.1  # こまめに読み出す
PACKET_TIMEOUT_SEC = 4.0          # 通常パケットの最大待ち時間（秒）
PACKET_TIMEOUT_PIC_SEC = 15.0     # $$Pic パケット専用の最大待ち時間（秒）

# ==== 送信設定（必要ならここだけ変更）====
# IC-9700 が JA1XPM C なら、発信元はこの形式にする
TX_MY_CALL = "JA1XPM C"  # 送信者コール（CALL + 半角スペース + 識別子 も可）
TX_UR_CALL = "CQCQCQ"      # 宛先

# 送信設定の更新をスレッド間で安全にする
TX_LOCK = threading.Lock()

# ==== ini 設定（exe/py と同一フォルダのみ）====
INI_FILENAME = "dvtextmonitor.ini"
_DEFAULT_INI_TEXT = "COM=COM1\nSPEED=9600\nMY=JA1XPM C\nUR=CQCQCQ\n"


def _get_app_dir() -> str:
    # exe化(Python frozen)なら実行ファイルの場所。通常はこの .py の場所。
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _normalize_call_value(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    parts = s.split()
    base = parts[0].upper()
    if len(parts) >= 2 and len(parts[1]) == 1:
        return f"{base} {parts[1].upper()}"
    return base


def ensure_and_load_ini() -> None:
    """dvtextmonitor.ini が無ければ生成し、あれば読み込んで反映する。

    ini が存在して内容が異常な場合は、英語1行だけ出して強制終了する。
    """
    global SERIAL_PORT, BAUD_RATE, TX_MY_CALL, TX_UR_CALL

    ini_path = os.path.join(_get_app_dir(), INI_FILENAME)

    # 無ければ新規作成（作れなくても、デフォルト値のまま続行）
    if not os.path.exists(ini_path):
        try:
            with open(ini_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(_DEFAULT_INI_TEXT)
        except OSError:
            pass
        return

    # あれば厳密に読む（異常なら INI FILE ERROR で終了）
    try:
        with open(ini_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        print("INI FILE ERROR")
        sys.exit(1)

    try:
        kv: dict[str, str] = {}
        for line in lines:
            if line.strip() == "":
                raise ValueError("blank line")
            if "=" not in line:
                raise ValueError("no '='")
            k, v = line.split("=", 1)
            k = k.strip().upper()
            v = v.strip()
            if not k or not v:
                raise ValueError("empty")
            if k in kv:
                raise ValueError("dup")
            kv[k] = v

        if set(kv.keys()) != {"COM", "SPEED", "MY", "UR"}:
            raise ValueError("missing/extra keys")

        SERIAL_PORT = kv["COM"]
        BAUD_RATE = int(kv["SPEED"])
        with TX_LOCK:
            TX_MY_CALL = _normalize_call_value(kv["MY"])
            TX_UR_CALL = _normalize_call_value(kv["UR"])

        if not SERIAL_PORT or not TX_MY_CALL or not TX_UR_CALL:
            raise ValueError("empty normalized")
    except Exception:
        print("INI FILE ERROR")
        sys.exit(1)



# ==== 1メッセージ分のブロック状態 ====
block_lat: float | None = None
block_lon: float | None = None
block_alt: float | None = None
block_crc_text: str | None = None


# ==== ICOM RS-MS1A 互換：壊れUTF-8 を直す ====
def fix_rsms1a(msg_bytes: bytes) -> bytes:
    """
    ICOM の「わざと壊したUTF-8」を元に戻す補正。

    復元:
      ef 67 -> e7
      ef 6f -> ef
    """
    return (msg_bytes
            .replace(b'\xef\x67', b'\xe7')
            .replace(b'\xef\x6f', b'\xef'))


# ==== RS-MS1A向け「謎変換」（fix_rsms1a の逆）====
def encode_rsms1a(raw_utf8: bytes) -> bytes:
    """
    raw UTF-8 bytes を ICOM/RS-MS1A 互換の「わざと壊したUTF-8」に変換する。

    逆変換:
      e7 -> ef 67
      ef -> ef 6f

    ※1バイトずつ変換して二重変換事故を避ける。
    """
    out = bytearray()
    for b in raw_utf8:
        if b == 0xE7:
            out.extend(b'\xEF\x67')
        elif b == 0xEF:
            out.extend(b'\xEF\x6F')
        else:
            out.append(b)
    return bytes(out)


# ==== RS-MS1A互換：6バイト部（便宜的“ID”）生成 ====
def build_rsms1a_msg_id(my_call: str, ur_call: str) -> bytes:
    """RS-MS1A/ICOM系の $$Msg の 6バイト部（"0011nn"）を生成する。

    あなたの実機検証で確定した規則（ASCII和 + オフセットの8bit演算）:

    1) 送信側定数 K を From から作る
         S = sumASCII(FROM_BASE) & 0xFF
         t = ASCII(lower(FROM_SUFFIX)) if suffix(1文字) else 0
         K = (S + 0x1A + t) & 0xFF

    2) 宛先側の nn を To から作る
         U = sumASCII(TO_BASE) & 0xFF
         base = (U + K) & 0xFF
         nn = base + ASCII(lower(TO_SUFFIX)) (suffix(1文字)があれば) を 8bit に丸める

    3) msg_id = b"0011" + f"{nn:02X}"（ASCII）
    """

    def _split_call(call: str) -> tuple[str, str | None]:
        s = (call or "").strip()
        if not s:
            return "", None
        parts = s.split()
        base = parts[0]
        suffix = parts[1] if (len(parts) >= 2 and len(parts[1]) == 1) else None
        return base, suffix

    from_base, from_suffix = _split_call(my_call)
    to_base, to_suffix = _split_call(ur_call)

    # 空はあり得ない想定だが、保険で固定
    if not from_base or not to_base:
        return b"001100"

    s_from = sum(from_base.encode("ascii", errors="ignore")) & 0xFF
    t_from = ord(from_suffix.lower()) if from_suffix else 0
    k = (s_from + 0x1A + t_from) & 0xFF

    s_to = sum(to_base.encode("ascii", errors="ignore")) & 0xFF
    base = (s_to + k) & 0xFF
    if to_suffix:
        nn = (base + ord(to_suffix.lower())) & 0xFF
    else:
        nn = base

    return f"0011{nn:02X}".encode("ascii")


# ==== チェックサム計算（rawテキストのみ / SUM 8bit）====
def calc_checksum(text_raw: bytes) -> int:
    """
    チェックサムは「テキスト本文の raw UTF-8 バイト列のみ」を対象とする。
    ID(6byte)やフッター(0x0D/0x00等)は含めない。

    方式: SUM(8bit) = sum(raw) & 0xFF
    """
    return sum(text_raw) & 0xFF


def encode_checksum_rsms1a(cs: int) -> bytes:
    """
    RS-MS1A/ICOM系のチェックサム（SUM8bit）の送信時エンコード。

    観測で確定している特例:
      - CS=0xEF のとき: EF 6F
      - CS=0x2C (',') のとき: EF AC

    これは一般化すると:
      EF (CS + 0x80) の2バイト形式（mod 256）

    ※現時点の確定範囲は 0xEF と 0x2C のみなので、そこだけ適用する。
    """
    cs &= 0xFF
    if cs in (0xEF, 0x2C):
        return bytes([0xEF, (cs + 0x80) & 0xFF])
    return bytes([cs])


# ==== 送信用 $$Msg パケット生成（CSは謎変換前rawのみ / IDはFrom+Toから生成）====
def build_tx_msg_packet(text: str, my_call: str, ur_call: str) -> bytes:
    """
    コンソール入力 text を RS-MS1A が読める $$Msg 形式にして返す。

    手順:
      1) テキストを raw UTF-8 bytes にする
      2) ★チェックサムは raw テキストのみで作る（ID/フッター等は含めない）
      3) ★RS-MS1A特例に従いCSをエンコード（例: 0xEFや0x2Cは2バイト化）
      4) raw を謎変換して payload にする
      5) ★ID(6バイト)は From/To から RS-MS1A互換規則で生成
      6) $$Msg,<from>,<to>,<id+payload+cs>\\r\\x00 を作って返す
    """
    raw = text.encode("utf-8", errors="strict")

    cs = calc_checksum(raw)
    cs_bytes = encode_checksum_rsms1a(cs)

    encoded = encode_rsms1a(raw)
    msg_id = build_rsms1a_msg_id(my_call, ur_call)

    body = msg_id + encoded + cs_bytes
    packet = (
        b"$$Msg,"
        + my_call.encode("ascii", errors="ignore")
        + b","
        + ur_call.encode("ascii", errors="ignore")
        + b","
        + body
        + b"\r\x00"
    )
    return packet


# ==== 送信ログを受信ログと同じフォーマットで出す ====
def print_tx_log(text: str, my_call: str, ur_call: str) -> None:
    if my_call:
        print(f"送信者:{my_call}")
    if ur_call:
        print(f"宛先:{ur_call}")
    print(f"電文:{text}")
    print_recv_time()


# ==== NMEA の度分 → 10進度 変換 ====
def nmea_to_decimal(value: str, is_lat: bool) -> float | None:
    if not value:
        return None
    try:
        if is_lat:
            deg = int(value[0:2])
            minutes = float(value[2:])
        else:
            deg = int(value[0:3])
            minutes = float(value[3:])
        return deg + minutes / 60.0
    except ValueError:
        return None


# ==== 各パケット種別の処理 ====
def handle_gpgga(packet: bytes) -> None:
    """
    $GPGGA パケット
      → 表示はせず、「次の $$Msg 用の位置情報」としてバッファに保存。
    """
    global block_lat, block_lon, block_alt

    try:
        text = packet.decode('ascii', errors='ignore')
    except UnicodeDecodeError:
        return

    fields = text.split(',')
    if len(fields) < 10:
        return

    lat_str = fields[2]
    ns = fields[3]
    lon_str = fields[4]
    ew = fields[5]
    alt_str = fields[9]

    if lat_str and ns in ("N", "S"):
        lat = nmea_to_decimal(lat_str, is_lat=True)
        if lat is not None:
            if ns == "S":
                lat = -lat
            block_lat = lat
        else:
            block_lat = None
    else:
        block_lat = None

    if lon_str and ew in ("E", "W"):
        lon = nmea_to_decimal(lon_str, is_lat=False)
        if lon is not None:
            if ew == "W":
                lon = -lon
            block_lon = lon
        else:
            block_lon = None
    else:
        block_lon = None

    if alt_str:
        try:
            block_alt = float(alt_str)
        except ValueError:
            block_alt = None
    else:
        block_alt = None


def handle_crc(packet: bytes) -> None:
    """
    $$CRC パケット
      → 表示せず、「次の $$Msg 用の D-PRS 行」として文字列を保存。
    """
    global block_crc_text

    try:
        text = packet.decode('ascii', errors='replace').strip()
    except UnicodeDecodeError:
        return

    block_crc_text = f"D-PRS:{text}"


def _split_payload_and_cs(payload_and_cs: bytes) -> tuple[bytes, bytes]:
    """
    payload_and_cs から payload と CSバイト列を分離する。

    既知のCS形式（観測ベース）:
      - 通常: CSは末尾1バイト
      - エスケープ: 末尾が  EF XX  の場合、CSは2バイト
          元CS = (XX - 0x80) & 0xFF
    """
    if len(payload_and_cs) == 0:
        return b"", b""

    if len(payload_and_cs) >= 2 and payload_and_cs[-2] == 0xEF:
        return payload_and_cs[:-2], payload_and_cs[-2:]

    if len(payload_and_cs) >= 1:
        return payload_and_cs[:-1], payload_and_cs[-1:]

    return b"", b""


def handle_msg(packet: bytes) -> None:
    """
    $$Msg パケット（1ブロックを確定させるトリガ）
    """
    global block_lat, block_lon, block_alt, block_crc_text

    parts = packet.split(b',', 3)
    if len(parts) < 4:
        return

    _, from_bytes, to_bytes, body = parts

    my_call = from_bytes.decode('ascii', errors='ignore').strip()
    ur_call = to_bytes.decode('ascii', errors='ignore').strip()

    if len(body) <= 6:
        payload_bytes = b""
    else:
        payload_and_cs = body[6:]  # 先頭6バイトはID
        payload_bytes, _cs_bytes = _split_payload_and_cs(payload_and_cs)

    fixed_payload = fix_rsms1a(payload_bytes)
    text = fixed_payload.decode('utf-8', errors='replace')

    if block_lat is not None and block_lon is not None:
        url = f"https://maps.google.com/?q={block_lat:.7f},{block_lon:.7f}"
        print(f"位置:{url}")

    if block_alt is not None:
        print(f"高度:{block_alt:.0f}m")

    if my_call:
        print(f"送信者:{my_call}")

    if ur_call:
        print(f"宛先:{ur_call}")

    print(f"電文:{text}")

    if block_crc_text:
        print(block_crc_text)

    print_recv_time()
    reset_block()


def handle_pic(packet: bytes) -> None:
    """
    $$Pic パケットは無視
    """
    return


def reset_block() -> None:
    global block_lat, block_lon, block_alt, block_crc_text
    block_lat = None
    block_lon = None
    block_alt = None
    block_crc_text = None


def print_recv_time() -> None:
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    timestr = now.strftime("%y%m%d %H:%M")
    print(f"受信日時:{timestr}JST")
    print()


def process_packet(packet: bytes) -> None:
    if not packet:
        return

    if packet.startswith(b'$GPGGA'):
        handle_gpgga(packet)
    elif packet.startswith(b'$$Msg'):
        handle_msg(packet)
    elif packet.startswith(b'$$CRC'):
        handle_crc(packet)
    elif packet.startswith(b'$$Pic'):
        handle_pic(packet)
    else:
        return


# ==== IME対応の送信入力（別スレッドで input()）====
def console_input_thread(tx_queue: "queue.Queue[str]") -> None:
    """IME対応のコンソール入力を受け取り、送信キューへ渡す。

    追加機能:
      - /MY   [callsign [suffix]] : TX_MY_CALL を変更（引数なしなら現在値を表示）
      - /UR   [callsign [suffix]] : TX_UR_CALL を変更（引数なしなら現在値を表示）
    大文字小文字はどちらでも受け付け、内部は正規化して保持する。
    """
    global TX_MY_CALL, TX_UR_CALL

    def _normalize_call(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        parts = s.split()
        base = parts[0].upper()
        if len(parts) >= 2 and len(parts[1]) == 1:
            suffix = parts[1].upper()
            return f"{base} {suffix}"
        return base

    while True:
        try:
            line = input()
        except EOFError:
            break
        except KeyboardInterrupt:
            break

        line = line.rstrip("\r\n")
        if line.strip() == "":
            continue

        stripped = line.strip()
        if stripped.startswith("/"):
            parts = stripped.split(maxsplit=1)
            cmd = parts[0].lower()

            if cmd == "/my":
                if len(parts) == 1:
                    with TX_LOCK:
                        print(TX_MY_CALL)
                    continue
                new_call = _normalize_call(parts[1])
                if new_call:
                    with TX_LOCK:
                        TX_MY_CALL = new_call
                continue

            if cmd == "/ur":
                if len(parts) == 1:
                    with TX_LOCK:
                        print(TX_UR_CALL)
                    continue
                new_call = _normalize_call(parts[1])
                if new_call:
                    with TX_LOCK:
                        TX_UR_CALL = new_call
                continue

        # 通常送信
        tx_queue.put(line)


# ==== メインループ：シリアルからパケット単位で読む ====
def main():
    print(f"Listening on {SERIAL_PORT} ({BAUD_RATE}bps)...")
    print("パケットごとに $GPGGA / $$Msg / $$Pic / $$CRC を処理します。（Ctrl+C で終了）")
    print("送信：コンソールに文字入力 → Enter で $$Msg を送信します。")

    buf = bytearray()
    in_packet_since: float | None = None

    tx_queue: "queue.Queue[str]" = queue.Queue()
    t = threading.Thread(target=console_input_thread, args=(tx_queue,), daemon=True)
    t.start()

    try:
        with serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            parity=PARITY,
            bytesize=BYTESIZE,
            stopbits=STOPBITS,
            timeout=TIMEOUT,
        ) as ser:

            while True:
                # 送信行が溜まっていれば全部送る
                while True:
                    try:
                        text = tx_queue.get_nowait()
                    except queue.Empty:
                        break

                    try:
                        with TX_LOCK:
                            my_call = TX_MY_CALL
                            ur_call = TX_UR_CALL
                        pkt = build_tx_msg_packet(text, my_call, ur_call)
                        ser.write(pkt)
                        ser.flush()
                        print_tx_log(text, my_call, ur_call)
                    except Exception as e:
                        print(f"[TX-ERR] {e}")

                # 受信済みがあればまとめて読む。なければ1バイト読む。
                to_read = ser.in_waiting or 1
                data = ser.read(to_read)

                if data:
                    buf_was_empty = (len(buf) == 0)
                    buf.extend(data)

                    # bufが空→今回入ったのが 0A/00 だけなら即捨て
                    if (
                        buf_was_empty
                        and buf
                        and (0x0D not in buf)
                        and all(b in (0x0A, 0x00) for b in buf)
                    ):
                        buf.clear()
                        in_packet_since = None
                        continue

                    if buf_was_empty and buf:
                        in_packet_since = time.monotonic()

                    while True:
                        try:
                            idx = buf.index(0x0D)
                        except ValueError:
                            break

                        packet = bytes(buf[:idx])
                        del buf[:idx + 1]

                        # CR の直後に来る 0x0A / 0x00 はフッタとして捨てる
                        while buf and buf[0] in (0x0A, 0x00):
                            del buf[0]

                        process_packet(packet)

                        if not buf:
                            in_packet_since = None

                # パケットタイムアウト監視
                if buf and in_packet_since is not None:
                    if all(b in (0x0A, 0x00) for b in buf):
                        buf.clear()
                        in_packet_since = None
                    else:
                        now = time.monotonic()
                        if buf.startswith(b'$$Pic'):
                            limit = PACKET_TIMEOUT_PIC_SEC
                        else:
                            limit = PACKET_TIMEOUT_SEC

                        if now - in_packet_since > limit:
                            print("[WARN] packet timeout, clearing buffer / state reset")
                            buf.clear()
                            reset_block()
                            in_packet_since = None

    except serial.SerialException as e:
        print(f"\nSerial Port Error: {e}")
    except KeyboardInterrupt:
        print("\nExiting...")


# ==== stdout をコンソール＋ファイルに二重出力するための Tee ====
class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> None:
        for s in self.streams:
            s.write(data)
            s.flush()

    def flush(self) -> None:
        for s in self.streams:
            s.flush()


if __name__ == "__main__":
    ensure_and_load_ini()
    print(VERSION)

    log_file = None
    original_stdout = sys.stdout

    # コマンドライン引数でログファイル指定があれば処理
    # 例: py 002.2dvtextmonitor.py log.txt
    if len(sys.argv) >= 2:
        log_path = sys.argv[1]

        if os.path.exists(log_path):
            while True:
                answer = input(
                    f"ログファイル '{log_path}' は既に存在します。"
                    " 上書き[W] / 追記[A] を選んでください (既定: A): "
                ).strip().lower()

                if answer in ("", "a", "append"):
                    mode = "a"
                    break
                elif answer in ("w", "write"):
                    mode = "w"
                    break
                else:
                    print("W または A を入力してください。")
        else:
            mode = "w"

        try:
            log_file = open(log_path, mode, encoding="utf-8")
            sys.stdout = Tee(original_stdout, log_file)
        except OSError as e:
            print(f"ログファイル '{log_path}' を開けませんでした: {e}")
            print("コンソール出力のみで続行します。")
            log_file = None
            sys.stdout = original_stdout

    try:
        main()
    finally:
        sys.stdout = original_stdout
        if log_file is not None:
            log_file.close()
