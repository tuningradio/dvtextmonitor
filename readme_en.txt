DV text monitor Ver 3.3  README.txt 2025/12/24
Copyright (C)JA1XPM

Before reading...
--------------------------------------------------------------------------------
This software is an unofficial personally developed tool, and is not related to Icom Inc. or any related organizations.
Names such as “D-STAR”, “ICOM”, “IC-9700”, “RS-MS1A/RS-MS1I” are trademarks/registered trademarks of their respective rights holders.
This software is an interoperable implementation based on observation of real hardware, and it may stop working due to future firmware/app updates, etc.
--------------------------------------------------------------------------------

This program is a Windows PC application that can communicate via DV text with ICOM RS-MS1A / RS-MS1I (smartphone apps).
Currently, RS-MS1A / RS-MS1I are only smartphone apps, and I developed this because I thought that if there were Windows software, it could communicate with them.

Primary assumed configuration: IC-9700(USB(B)) + Windows PC
With this program, you no longer need to connect a smartphone to the IC-9700, and you can send/receive text from the PC.

--------------------------------------------------------------------------------
1. Required items
- Windows11 PC (older versions of Windows have not been tested)
- ICOM IC-9700 (DV Data I/F (USB(B)) is used) Set the mode to DV mode
- Connect the rig and the PC with a USB cable. For the required device driver, refer to the ICOM home page
- COM port number on the PC side (example: COM3, etc.)

* PTT control for TX/RX is not required. The IC-9700 is designed to transmit automatically if you feed data into the USB(B) set for DV data.

--------------------------------------------------------------------------------
2. How to start

2-1) Start
    python dvtextmonitor.py

2-2) If you want to save to a log file (optional, and the file name is arbitrary)
    python dvtextmonitor.py log.txt

- log can be specified with either a relative path or an absolute path.
  Example: python dvtextmonitor.py C:\temp\dvlog.txt
- If the file already exists, after startup you can choose overwrite or append.
- The character encoding of the log is UTF-8 (no BOM). If you mistakenly save it with a character encoding such as Shift-JIS, the characters will become unreadable.
--------------------------------------------------------------------------------
3. Configuration file dvtextmonitor.ini
At startup, it looks for dvtextmonitor.ini in the same folder as the program itself.

- If there is no ini: it automatically creates a new one (writes with initial values)
- If there is an ini: it reads the contents and uses them
  However, if the contents are broken, it displays "INI FILE ERROR" and exits

3-1) Example of ini (only these 4 items without fail)
    COM=COM1
    SPEED=9600
    MY=JA1XPM C
    UR=CQCQCQ

- COM   : COM port name (example COM3)
- SPEED : communication speed (number)
- MY    : sender callsign (example JA1XPM C)
- UR    : destination callsign (example W1AW A / CQCQCQ)

* Even if you change it with each command /MY /UR (described later) on the console after startup, it is not written back to the ini (the ini is for recovery).
* SPEED is only required to be "a numeric value", and the application does not restrict it, but if the IC-9700 USB(B) is used as DV data, the only usable speeds are 4800 or 9600.

--------------------------------------------------------------------------------
4. Usage (basic)
When started, it begins displaying received messages. When DV text is sent from another station by RS-MS1A/RS-MS1I, it displays it.
When you transmit a DV image and a text message is added, it also displays that message. (image data is discarded)
If GNSS-format GPS information is added, it displays it as a Google Map format URL. Ctrl+left-click launches a web browser and displays the location.
If D-PRS-format GPS information is added, it displays it as-is.
If you enter characters in the console and press Enter, it transmits to the other station.

4-1) Switching sender callsign MY / destination callsign UR (possible during execution)
- Display current values:
    /MY
    /UR
- Change:
    /MY JA1XPM C
    /UR W1AW A

* You can enter either uppercase or lowercase.
* Even if you change the callsign with /MY /UR, it is not written back to the ini.
* It is recommended that /MY be the same as the callsign set in the IC-9700.
* In the current version, there is no function to fetch the callsign set in the IC-9700.

--------------------------------------------------------------------------------
5. Common trouble

5-1) Cannot open the COM port
- COM number is different
- Another application is using the COM
- Permission/driver issues

In this case, it displays "Serial Port Error: ..." at startup.

5-2) Exits with INI FILE ERROR
The contents of dvtextmonitor.ini are broken.
If you delete the ini and restart, it regenerates with initial values.

--------------------------------------------------------------------------------
6. Exit
Exit with Ctrl + C.
It leaves the text "Exiting.." in the log. If it exits abnormally, it will not remain.
--------------------------------------------------------------------------------

--------------------------------------------------------------------------------
7. Disclaimer
This software is provided without warranty. Please use it at your own risk.
Operate in compliance with the Radio Law and various rules.

--------------------------------------------------------------------------------
8. License
This software is published under the MIT License. See LICENSE for details.
--------------------------------------------------------------------------------

================================================================================
Technical explanation (RS-MS1A compatible packet structure)
================================================================================

A) RS-MS1A-type text packet structure ($$Msg)
On the serial line, it is roughly the following format (ASCII representation):

    $$Msg,<MY>,<UR>,<BODY>\r\0

- $$Msg  : Header (ASCII)
- <MY>   : Sender callsign (example JA1XPM C)
- <UR>   : Destination callsign (example W1AW A, CQCQCQ, etc.)
- <BODY> : Concatenate the following
    1) ID  : Fixed 6 bytes (ASCII) "0011nn"
    2) TEXT: Body (after RS-MS1A compatible escaping)
    3) CS  : Checksum (1 byte or 2 bytes)
- Terminator   : 0x0D 0x00 (CR + NUL)

Example:
    JA1XPM C sends "aaa" to JQ1YZA
    $$Msg,JA1XPM C,JQ1YZA,0011EEaaa#\r\0

--------------------------------------------------------------------------------
B) Generation of ID part (6 bytes "0011nn")
The ID is fixed 6 bytes:
    ID = "0011" + nn (2-digit hexadecimal, uppercase)

nn is calculated from both the sender (MY) and the destination (UR).

B-1) Callsign decomposition
"JA1XPM C" is handled as:
  BASE   = "JA1XPM"
  SUFFIX = "C" (1 character; may be absent)
SUFFIX is lower()'d during calculation (C→c).

B-2) Calculation of sender-side constant K (MY → K)
    S = sum(ASCII(MY_BASE)) mod 256
    t = ASCII(lower(MY_SUFFIX)) (if suffix exists) else 0
    K = (S + 0x1A + t) mod 256

B-3) Calculation of destination-side nn (UR → nn)
    U    = sum(ASCII(UR_BASE)) mod 256
    base = (U + K) mod 256
    nn   = base + ASCII(lower(UR_SUFFIX)) (if suffix exists) mod 256
    If there is no suffix, nn = base

B-4) Calculation example (MY=JA1XPM C / UR=JQ1YZA)
MY: JA1XPM C
  ASCII sum of MY_BASE "JA1XPM":
    J=74, A=65, 1=49, X=88, P=80, M=77 → Total 433
    433 mod 256 = 177 = 0xB1
  MY_SUFFIX "C" → lower('c') = 0x63(99)
  K = (0xB1 + 0x1A + 0x63) mod256
    = 177 + 26 + 99 = 302 → 302-256 = 46 = 0x2E

UR: JQ1YZA (no suffix)
  ASCII sum of UR_BASE "JQ1YZA":
    J=74, Q=81, 1=49, Y=89, Z=90, A=65 → Total 448
    448 mod 256 = 192 = 0xC0
  base = (0xC0 + K(0x2E)) mod256 = 0xEE
  Since there is no suffix, nn = 0xEE

Therefore ID = "0011EE"

--------------------------------------------------------------------------------
C) The text body is UTF-8 code, but with escaping
The text body uses UTF-8 code. However, it is necessary to replace (escape) "specific values" in the body byte sequence when transmitting.
The "specific values" (see end of document) are defined by the D-STAR specification. These specific values may appear in UTF-8 Kanji code, and cannot be sent as-is.
Therefore, the following escaping operation is performed.

C-1) Body escaping rules (when transmitting)
- 0xE7 → 0xEF 0x67
- 0xEF → 0xEF 0x6F

Reverse conversion on reception:
- 0xEF 0x67 → 0xE7
- 0xEF 0x6F → 0xEF

C-2) Escaping example: "画像"
The raw UTF-8 of "画像" is:
  "画" U+753B → E7 94 BB
  "像" U+50CF → E5 83 8F
  raw = E7 94 BB E5 83 8F

Escaping on transmission (replace E7):
  E7 94 BB E5 83 8F
  → EF 67 94 BB E5 83 8F

On reception, it is converted back by EF 67 → E7 and restored to the original UTF-8.

--------------------------------------------------------------------------------
D) Checksum (CS) calculation and transmission representation
The checksum is calculated using "only the raw UTF-8 byte sequence of the text body".
(It does not include the ID part, the escaped body, or the terminator \r\0.)

D-1) Formula (SUM 8bit)
    CS = sum(raw_utf8_bytes) & 0xFF

Example: "aaa"
  0x61 + 0x61 + 0x61 = 0x123 → CS = 0x23 ('#')

D-2) CS transmission representation (RS-MS1A compatible)
Normally, CS is appended as 1 byte, but as observed compatibility the following special cases are implemented:

- If CS == 0xEF or CS == 0x2C, make it 2 bytes:
    CS_bytes = 0xEF, (CS + 0x80) & 0xFF
  Example: 0xEF → EF 6F
  Example: 0x2C → EF AC

- Otherwise, 1 byte:
    CS_bytes = [CS]

D-3) Why CS is escaped
Since there is no manufacturer specification, it cannot be stated definitively, but from observation and structure, it is natural to think that the purpose is "collision avoidance" (inference).
- If CS is 0xEF, it would look like UTF-8 escaping, and logic on the receiving side that expects the next 1 byte is thought to operate.
Therefore, as a special case, it is necessary to send it as 2 bytes.
- 0x2C is ASCII ',' (comma), and is also the delimiter of $$Msg, so it may be inconvenient for implementation.
Important: What can be said for sure is the fact that "RS-MS1A outputs the checksum as 2 bytes when it has that value", and the reason is only an inference.

D-4) CS escaping example: the text body is "abcde"
raw (UTF-8/ASCII are the same):
  61 62 63 64 65

Checksum:
  0x61+0x62+0x63+0x64+0x65 = 0x1EF → lower 8 bits = 0xEF
  Therefore CS = 0xEF

CS transmission representation (2 bytes due to special case):
  CS_bytes = EF (EF+80 mod256) = EF 6F

Therefore the end of the text body is as follows (ID and 0x0D,0x00 are omitted):
  ... 61 62 63 64 65 EF 6F  ... 

--------------------------------------------------------------------------------
E) Assembly order for transmission (summary)
Steps to send the body "text":
  1) raw = text.encode("utf-8")
  2) CS = sum(raw) & 0xFF
  3) CS_bytes = (make it 2 bytes if needed)
  4) payload = body escape(raw)
  5) ID = "0011" + nn (calculated from MY/UR)
  6) BODY = ID + payload + CS_bytes
  7) Final assembly (python) packet = b"$$Msg," + MY + b"," + UR + b"," + BODY + b"\r\x00"


================================================================================
Technical explanation (about specific values)
================================================================================
In the D-STAR standard method (JARL STD7.0) 6.2 Simple data communication, **characters that cannot be used (byte values)** are explicitly stated. Specifically, these seven are listed.
0x00 (footer)
0x11 (XON)
0x13 (XOFF)
0x76 (used for packet loss notification)
0x84 (used for packet loss notification)
0xE7 (used for packet loss notification)
0xFE reserved for functional extensions
