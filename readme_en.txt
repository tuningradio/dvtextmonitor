DV text monitor Ver 3.3  README_EN.txt
DV text monitor Ver 3.3 by JA1XPM 2025/12/24

This program enables D-STAR text messaging from a Windows PC, in the same family of D-STAR text communication used by
ICOM RS-MS1A / RS-MS1I (smartphone apps).
At present, there is no Windows text-messaging software equivalent to RS-MS1A / RS-MS1I, so this was created to
fill that gap.

Primary intended setup: IC-9700(USB(B)) + Windows PC
With this program, you no longer need to connect a smartphone to the IC-9700, and you can send/receive D-STAR text
messages from the PC.

--------------------------------------------------------------------------------
1. Requirements
- Windows 11 PC (older versions of Windows are not tested)
- ICOM IC-9700 (use DV Data I/F (USB(B)); set the rig to DV mode)
- Connect the rig and the PC with a USB cable. For the required device driver, refer to the ICOM website.
- COM port number on the PC (e.g. COM3)

* PTT control for TX/RX is not required. The IC-9700 is designed to transmit automatically when you feed data into
  the USB(B) configured for DV data.

--------------------------------------------------------------------------------
2. How to run

2-1) Run
    python dvtextmonitor.py

2-2) Save to a log file (optional; the file name is arbitrary)
    python dvtextmonitor.py log.txt

- The log can be specified using either a relative path or an absolute path.
  Example: python dvtextmonir.py C:\temp\dvlog.txt
- If the file already exists, after startup you can choose overwrite or append.
- The log is UTF-8 (no BOM). If you accidentally store it in another encoding (e.g. Shift-JIS), it may become
  unreadable.

--------------------------------------------------------------------------------
3. Configuration file: dvtextmonitor.ini
At startup, the program looks for dvtextmonitor.ini in the same folder as the program itself.

- If the ini file does not exist: it is created automatically (written with default values)
- If the ini file exists: it is loaded and used
  If the contents are corrupted, the program prints "INI FILE ERROR" and exits.

3-1) Example ini (ONLY these 4 items are required)
    COM=COM1
    SPEED=9600
    MY=JA1XPM C
    UR=CQCQCQ

- COM   : COM port name (e.g. COM3)
- SPEED : serial speed (numeric)
- MY    : sender callsign (e.g. JA1XPM C)
- UR    : destination callsign (e.g. W1AW A / CQCQCQ)

* Even if you change values after startup using the console commands /MY and /UR (see below), the program does NOT
  write back to the ini file (the ini is for recovery).
* SPEED is only required to be numeric; the program does not restrict the value. However, on the IC-9700 DV Data I/F,
  the selectable speeds are only 4800 or 9600.

--------------------------------------------------------------------------------
4. Usage
After startup, received messages are displayed. When another station sends DV text using RS-MS1A / RS-MS1I, it will be
displayed here.
If you transmit a DV image with an attached text message, that text message is also displayed (image data is discarded).
If GNSS-format GPS information is attached, it is displayed as a Google Maps-style URL. Ctrl+left-click opens a web
browser and shows the location.
If D-PRS-format GPS information is attached, it is displayed as-is.
To transmit from this program, type text in the console and press Enter to send it to the other station.

4-1) Change MY (sender) / UR (destination) during runtime
- Show current values:
    /MY
    /UR
- Set values:
    /MY JA1XPM C
    /UR W1AW A

* Uppercase/lowercase input is accepted.
* Changing callsigns with /MY /UR does NOT write back to the ini file.
* It is recommended to set /MY to the same callsign configured in the IC-9700.
* In the current version, there is no function to read the callsign configured in the IC-9700.

--------------------------------------------------------------------------------
5. Common issues

5-1) Cannot open the COM port
- Wrong COM number
- Another application is using the COM port
- Permission/driver issues

In this case, the program prints: "Serial Port Error: ..."

5-2) The program exits with "INI FILE ERROR"
The dvtextmonitor.ini contents are corrupted.
Delete the ini file and restart; it will be regenerated with default values.

--------------------------------------------------------------------------------
6. Exit
Press Ctrl + C to exit.
The program leaves the text "Exiting.." in the log. If the program terminates abnormally, it will not be left.

--------------------------------------------------------------------------------
Disclaimer
Use this software at your own risk.
Operate in compliance with all applicable laws and rules.

================================================================================
Technical Notes (RS-MS1A-compatible text)
================================================================================

A) RS-MS1A-style text packet format ($$Msg)
On the serial interface, the format is roughly as follows (ASCII representation):

    $$Msg,<MY>,<UR>,<BODY>\r\0

- $$Msg : header (ASCII)
- <MY>  : sender callsign (e.g. JA1XPM C)
- <UR>  : destination callsign (e.g. W1AW A, CQCQCQ, etc.)
- <BODY>: concatenation of:
    1) ID   : fixed 6 bytes (ASCII) "0011nn"
    2) TEXT : message body (after RS-MS1A-compatible escaping)
    3) CS   : checksum (1 byte or 2 bytes)
- Trailer: 0x0D 0x00 (CR + NUL)

Example:
    $$Msg,JA1XPM C,W1AW A,0011AFaaa#\r\0

--------------------------------------------------------------------------------
B) ID generation (6 bytes "0011nn")
The ID is fixed 6 bytes:
    ID = "0011" + nn (2-digit uppercase hex)

nn is computed from both the sender (MY) and destination (UR).

B-1) Callsign parsing
For a callsign like "JA1XPM C":
  BASE   = "JA1XPM"
  SUFFIX = "C" (one character; may be absent)
SUFFIX is lowercased for calculation (C -> c).

B-2) Sender-side constant K calculation (UR -> K)
    S = sum(ASCII(UR_BASE)) mod 256
    t = ASCII(lower(UR_SUFFIX)) (if suffix exists) else 0
    K = (S + 0x1A + t) mod 256

B-3) Destination-side nn calculation (MY -> nn)
    U    = sum(ASCII(MY_BASE)) mod 256
    base = (U + K) mod 256
    nn   = base + ASCII(lower(MY_SUFFIX)) (if suffix exists) mod 256
    If there is no suffix, nn = base

B-4) Example calculation (MY=JA1XPM C / UR=JQ1YZA)
MY: JA1XPM C
  ASCII sum of MY_BASE "JA1XPM":
    J=74, A=65, 1=49, X=88, P=80, M=77 -> total 433
    433 mod 256 = 177 = 0xB1
  MY_SUFFIX "C" -> lower('c') = 0x63 (99)
  K = (0xB1 + 0x1A + 0x63) mod 256
    = 177 + 26 + 99 = 302 -> 302-256 = 46 = 0x2E

UR: JQ1YZA (no suffix)
  ASCII sum of UR_BASE "JQ1YZA":
    J=74, Q=81, 1=49, Y=89, Z=90, A=65 -> total 448
    448 mod 256 = 192 = 0xC0
  base = (0xC0 + K(0x2E)) mod 256 = 0xEE
  No suffix, so nn = 0xEE

Therefore ID = "0011EE"

--------------------------------------------------------------------------------
C) Text body is ASCII or UTF-8 Kanji (RS-MS1A-compatible escaping is required)
The text body is handled as a UTF-8 byte sequence.
For compatibility with observed behavior, certain byte values in the text are replaced (escaped) on transmit.
These special values (see the end of this document) are defined by the D-STAR specification. Such values can appear
inside UTF-8 Kanji sequences, but cannot be sent as-is.

C-1) Text escaping rules (TX)
- 0xE7 -> 0xEF 0x67
- 0xEF -> 0xEF 0x6F

Reverse conversion on receive:
- 0xEF 0x67 -> 0xE7
- 0xEF 0x6F -> 0xEF

C-2) Escaping example: "画像"
Raw UTF-8 for "画像":
  "画" U+753B -> E7 94 BB
  "像" U+50CF -> E5 83 8F
  raw = E7 94 BB E5 83 8F

TX escaping (replace E7):
  E7 94 BB E5 83 8F
  -> EF 67 94 BB E5 83 8F

On RX, EF 67 is converted back to E7 to restore the original UTF-8.

--------------------------------------------------------------------------------
D) Checksum (CS): calculation and on-wire representation
The checksum is calculated using ONLY the raw UTF-8 bytes of the text body.
(ID, escaped payload, and the trailer \r\0 are NOT included.)

D-1) Formula (8-bit sum)
    CS = sum(raw_utf8_bytes) & 0xFF

Example: "aaa"
  0x61 + 0x61 + 0x61 = 0x123 -> CS = 0x23 ('#')

D-2) CS on-wire representation (RS-MS1A-compatible)
Normally, CS is appended as 1 byte. However, for compatibility with observed RS-MS1A behavior, the following special
cases are implemented:

- If CS == 0xEF or CS == 0x2C, encode as 2 bytes:
    CS_bytes = 0xEF, (CS + 0x80) & 0xFF
  Example: 0xEF -> EF 6F
  Example: 0x2C -> EF AC

- Otherwise, encode as 1 byte:
    CS_bytes = [CS]

D-3) Why escape CS (reason)
There is no public vendor specification, so the exact reason cannot be stated with certainty. Based on observed behavior
and structure, "collision avoidance" is a natural interpretation (inference).
- 0xEF is used as an introducer byte for the text escaping scheme. If CS were 0xEF as-is, it may be a non-usable code
  for D-STAR communication, so it is believed to be escaped.
- 0x2C is ASCII ',' (comma) and is also a delimiter in $$Msg fields, so it may be inconvenient for some
  implementations.
Important: What is certain is that RS-MS1A encodes the checksum as 2 bytes for these values; the reason above is an
inference.

D-4) CS escaping example: text body "abcde"
Raw (UTF-8 same as ASCII here):
  61 62 63 64 65

Checksum:
  0x61+0x62+0x63+0x64+0x65 = 0x1EF -> low 8 bits = 0xEF
  Therefore CS = 0xEF

On-wire CS (special case -> 2 bytes):
  CS_bytes = EF (EF+80 mod 256) = EF 6F

Therefore the end of the body looks like this (ID and 0x0D,0x00 omitted):
  ... 61 62 63 64 65 EF 6F ...

--------------------------------------------------------------------------------
E) TX assembly steps (summary)
To transmit text "text":
  1) raw = text.encode("utf-8")
  2) CS = sum(raw) & 0xFF
  3) CS_bytes = (2-byte form if needed)
  4) payload = text_escape(raw)
  5) ID = "0011" + nn (computed from MY/UR)
  6) BODY = ID + payload + CS_bytes
  7) Final assembly (python)packet = b"$$Msg," + UR + b"," + MY + b"," + BODY + b"\r\x00"


================================================================================
Technical Notes (about the special values)
================================================================================
For the D-STAR standard (JARL STD7.0), section 6.2 "Simple data communication" explicitly lists the byte values that are
NOT allowed as characters. Specifically, the following seven values are prohibited:

0x00 (footer)
0x11 (XON)
0x13 (XOFF)
0x76 (used for packet loss notification)
0x84 (used for packet loss notification)
0xE7 (used for packet loss notification)
0xFE (reserved for functional extensions)
