"""The checks an uploaded image passes before it is staged (DL-0074, DL-0242, DL-0472, ASR-23,
T-06): PNG, JPEG or GIF by its leading bytes, HEIC named in its own refusal, the platform's size
and dimension limits read from the header before any library parses the data, and every metadata
segment stripped — but for a JPEG's orientation tag — by chunk, marker and block. Nothing is ever
decoded to pixels or converted.
"""

from __future__ import annotations

import io
import re
import struct
import warnings
from dataclasses import dataclass

from django.conf import settings
from PIL import Image as Pillow

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_SIDE = 10_000

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
GIF_SIGNATURES = (b"GIF87a", b"GIF89a")
HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}

PNG_KEPT = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"pHYs"}
# The frame markers that carry a JPEG's dimensions; C4, C8 and CC are not frames.
SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
# SOI, DQT, DHT, DAC, DRI, DNL, the frames and SOS, EOI: what a decoder needs. APP0 is kept only as
# JFIF, rebuilt without the thumbnail JFIF may carry — its JFXX extension, which carries one too, is
# dropped — and APP14 only as Adobe's, rebuilt from its fixed fields.
JPEG_KEPT = {0xD8, 0xDB, 0xC4, 0xCC, 0xDD, 0xDC, 0xDA, 0xD9} | SOF
# Where a scan's entropy-coded data ends: an 0xFF that is not a stuffed zero, a restart or fill.
SCAN_END = re.compile(rb"\xff(?![\x00\xd0-\xd7\xff])")
# Markers that stand alone, with no length after them.
STANDALONE = {0x01, 0xD8, 0xD9} | set(range(0xD0, 0xD8))
ORIENTATION = 0x0112


@dataclass(frozen=True)
class Checked:
    """An image that passed: its extension, its stripped bytes, its stored width and height."""

    ext: str
    data: bytes
    width: int
    height: int


class ImageRefused(Exception):
    """The image is refused for `code`; `params` holds the numbers its message names."""

    def __init__(self, code: str, params: dict[str, int] | None = None) -> None:
        super().__init__(code, params or {})
        self.code = code
        self.params = params or {}


class _Unreadable(Exception):
    pass


def limit() -> int:
    """The largest image accepted: the image cap or the platform's upload maximum, the lower."""
    return min(MAX_BYTES, settings.UPLOAD_MAX_BYTES)


def check(data: bytes) -> Checked:
    """`data` checked and stripped; `ImageRefused` with the first rule it breaks."""
    if len(data) > limit():
        raise ImageRefused("too_large", {"limit_mb": limit() // (1024 * 1024)})
    if data[4:8] == b"ftyp" and data[8:12] in HEIC_BRANDS:
        raise ImageRefused("heic")
    if data.startswith(PNG_SIGNATURE):
        ext, pillow_format, read = "png", "PNG", _read_png
    elif data.startswith(JPEG_SIGNATURE):
        ext, pillow_format, read = "jpg", "JPEG", _read_jpeg
    elif data[:6] in GIF_SIGNATURES:
        ext, pillow_format, read = "gif", "GIF", _read_gif
    else:
        raise ImageRefused("type")
    try:
        # The size, the pixels decoding would make, and the stripped bytes, from one walk of the
        # structure; nothing is decoded.
        width, height, pixels, stripped = read(data)
    except (_Unreadable, struct.error, IndexError) as error:
        raise ImageRefused("unreadable") from error
    if width > MAX_SIDE or height > MAX_SIDE or max(width * height, pixels) > MAX_PIXELS:
        raise ImageRefused(
            "dimensions",
            {"width": width, "height": height, "max_side": MAX_SIDE, "max_pixels": MAX_PIXELS},
        )
    _verify(data, pillow_format)
    return Checked(ext, stripped, width, height)


def _verify(data: bytes, pillow_format: str) -> None:
    """Pillow's open, by the one parser the signature names, and its `verify` — which checks a
    PNG's chunks and CRCs, and for a JPEG or a GIF no more than the open's own read of the
    header."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Pillow.DecompressionBombWarning)
            with Pillow.open(io.BytesIO(data), formats=(pillow_format,)) as opened:
                opened.verify()
    except Pillow.DecompressionBombError as error:
        params = {"width": 0, "height": 0, "max_side": MAX_SIDE, "max_pixels": MAX_PIXELS}
        raise ImageRefused("dimensions", params) from error
    except Exception as error:  # noqa: BLE001 — every parser failure is an unreadable image
        raise ImageRefused("unreadable") from error


# PNG ---------------------------------------------------------------------------------------------


def _png_chunks(data: bytes) -> list[tuple[bytes, int, int]]:
    """Each chunk as `(type, start, end)`, the end past its CRC; through `IEND`."""
    chunks = []
    position = len(PNG_SIGNATURE)
    while True:
        if position + 8 > len(data):
            raise _Unreadable("a chunk past the end")
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        end = position + 12 + length
        if end > len(data):
            raise _Unreadable("a chunk past the end")
        chunks.append((kind, position, end))
        position = end
        if kind == b"IEND":
            return chunks


def _png_size(data: bytes) -> tuple[int, int]:
    position = len(PNG_SIGNATURE)
    if data[position + 4 : position + 8] != b"IHDR":
        raise _Unreadable("no IHDR")
    width, height = struct.unpack(">II", data[position + 8 : position + 16])
    return int(width), int(height)


def _read_png(data: bytes) -> tuple[int, int, int, bytes]:
    width, height = _png_size(data)
    if width > MAX_SIDE or height > MAX_SIDE or width * height > MAX_PIXELS:
        # Refused by its header alone, however the rest of it reads.
        return width, height, width * height, b""
    chunks = _png_chunks(data)
    headers = [n for n, (kind, _start, _end) in enumerate(chunks) if kind == b"IHDR"]
    if headers != [0] or chunks[0][2] - chunks[0][1] != 25:
        # One header of thirteen bytes, first: a second would be read as the size by a library
        # that takes the last.
        raise _Unreadable("not one header")
    kept = [data[start:end] for kind, start, end in chunks if kind in PNG_KEPT]
    return width, height, width * height, PNG_SIGNATURE + b"".join(kept)


# JPEG --------------------------------------------------------------------------------------------


def _jpeg_segments(data: bytes) -> list[tuple[int, int, int, int]]:
    """Each marker as `(marker, start, payload, end)` — where it starts, where its payload starts
    past the length, and where it ends: a segment through its length, a scan through its
    entropy-coded data; through `EOI`."""
    segments = [(0xD8, 0, 2, 2)]
    position = 2
    while True:
        if position >= len(data) or data[position] != 0xFF:
            raise _Unreadable("no marker where one belongs")
        start = position
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            raise _Unreadable("a marker past the end")
        marker = data[position]
        position += 1
        if marker in STANDALONE:
            segments.append((marker, start, position, position))
            if marker == 0xD9:
                return segments
            continue
        (length,) = struct.unpack(">H", data[position : position + 2])
        end = position + length
        if length < 2 or end > len(data):
            raise _Unreadable("a segment past the end")
        if marker == 0xDA:
            # The entropy-coded data runs to the next marker that is neither a stuffed zero, a
            # restart nor fill.
            found = SCAN_END.search(data, end)
            if found is None or found.start() + 1 >= len(data):
                raise _Unreadable("a scan without its end")
            end = found.start()
        segments.append((marker, start, position + 2, end))
        position = end


def _read_jpeg(data: bytes) -> tuple[int, int, int, bytes]:
    segments = _jpeg_segments(data)
    frames = [payload for marker, _start, payload, _end in segments if marker in SOF]
    if len(frames) != 1:
        # None, or two that disagree on the size: neither is a picture a decoder can trust.
        raise _Unreadable("not one frame")
    first_scan = next((n for n, segment in enumerate(segments) if segment[0] == 0xDA), None)
    frame_at = next(n for n, segment in enumerate(segments) if segment[0] in SOF)
    if first_scan is None or first_scan < frame_at:
        raise _Unreadable("no frame before the scan")
    # The frame's precision, then its height and width.
    height, width = struct.unpack(">HH", data[frames[0] + 1 : frames[0] + 5])
    return int(width), int(height), int(width) * int(height), _strip_jpeg(data, segments)


def _orientation_of(payload: bytes) -> tuple[bytes, int] | None:
    """The byte order and orientation an EXIF `APP1` payload carries, when it carries 1 to 8."""
    if not payload.startswith(b"Exif\x00\x00"):
        return None
    tiff = payload[6:]
    order = tiff[:2]
    if order not in (b"II", b"MM"):
        return None
    endian = "<" if order == b"II" else ">"
    try:
        (offset,) = struct.unpack(endian + "I", tiff[4:8])
        (count,) = struct.unpack(endian + "H", tiff[offset : offset + 2])
        for n in range(count):
            entry = tiff[offset + 2 + 12 * n : offset + 14 + 12 * n]
            tag, kind, number = struct.unpack(endian + "HHI", entry[:8])
            if tag == ORIENTATION and kind == 3 and number == 1:
                (value,) = struct.unpack(endian + "H", entry[8:10])
                return (order, value) if 1 <= value <= 8 else None
    except struct.error:
        return None
    return None


def _minimal_app1(order: bytes, value: int) -> bytes:
    """An `APP1` holding the orientation tag and nothing else (DL-0472)."""
    endian = "<" if order == b"II" else ">"
    tiff = (
        order
        + struct.pack(endian + "H", 42)
        + struct.pack(endian + "I", 8)
        + struct.pack(endian + "H", 1)
        + struct.pack(endian + "HHI", ORIENTATION, 3, 1)
        + struct.pack(endian + "H", value)
        + b"\x00\x00"
        + struct.pack(endian + "I", 0)
    )
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def _strip_jpeg(data: bytes, segments: list[tuple[int, int, int, int]]) -> bytes:
    kept = []
    oriented = False
    for marker, start, payload, end in segments:
        if marker in JPEG_KEPT:
            kept.append(data[start:end])
        elif marker == 0xEE and data[payload : payload + 5] == b"Adobe" and end - payload >= 12:
            # The version, the two flag words and the colour transform.
            fields = data[payload : payload + 12]
            kept.append(b"\xff\xee" + struct.pack(">H", len(fields) + 2) + fields)
        elif marker == 0xE0 and data[payload : payload + 5] == b"JFIF\x00" and end - payload >= 12:
            # The version, units and densities, and a thumbnail of no pixels.
            header = data[payload : payload + 12] + b"\x00\x00"
            kept.append(b"\xff\xe0" + struct.pack(">H", len(header) + 2) + header)
        elif marker == 0xE1 and not oriented:
            found = _orientation_of(data[payload:end])
            if found is not None:
                kept.append(_minimal_app1(*found))
                oriented = True
    return b"".join(kept)


# GIF ---------------------------------------------------------------------------------------------


def _sub_blocks_end(data: bytes, position: int) -> int:
    """Past the sub-blocks starting at `position`, their terminator included."""
    while True:
        size = data[position]
        position += 1 + size
        if size == 0:
            return position
        if position > len(data):
            raise _Unreadable("a block past the end")


def _read_gif(data: bytes) -> tuple[int, int, int, bytes]:
    """The extent every frame reaches on the screen, the pixels all the frames decode to, and the
    blocks a decoder needs: the images, each frame's graphic control, and the loop count, each
    rebuilt from its own fields — any other extension goes."""
    if len(data) < 13:
        raise _Unreadable("no logical screen descriptor")
    width, height = (int(n) for n in struct.unpack("<HH", data[6:10]))
    packed = data[10]
    position = 13 + (3 * 2 ** ((packed & 0x07) + 1) if packed & 0x80 else 0)
    kept = [data[:position]]
    pixels = 0
    while True:
        introducer = data[position]
        if introducer == 0x3B:
            kept.append(b"\x3b")
            return width, height, pixels, b"".join(kept)
        if introducer == 0x2C:
            left, top, frame_width, frame_height = struct.unpack(
                "<HHHH", data[position + 1 : position + 9]
            )
            width, height = max(width, left + frame_width), max(height, top + frame_height)
            pixels += frame_width * frame_height
            if pixels > MAX_PIXELS:
                # Every frame is decoded: no further walk is needed to refuse.
                return width, height, pixels, b""
            descriptor = data[position + 9]
            table = 3 * 2 ** ((descriptor & 0x07) + 1) if descriptor & 0x80 else 0
            end = _sub_blocks_end(data, position + 10 + table + 1)
            kept.append(data[position:end])
        elif introducer == 0x21:
            label = data[position + 1]
            end = _sub_blocks_end(data, position + 2)
            first = data[position + 2]
            if label == 0xF9 and first == 4:
                kept.append(b"\x21\xf9\x04" + data[position + 3 : position + 7] + b"\x00")
            elif label == 0xFF and data[position + 2 : position + 14] == b"\x0bNETSCAPE2.0":
                loop = data[position + 14 : position + 18]
                if loop[:2] == b"\x03\x01":
                    kept.append(b"\x21\xff\x0bNETSCAPE2.0" + loop + b"\x00")
        else:
            raise _Unreadable("an unknown block")
        position = end
