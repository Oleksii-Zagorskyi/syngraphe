"""The image checks of an upload: the refusals in their order, the limits, and the stripping of
PNG chunks, JPEG segments and GIF blocks without decoding a pixel. Every image is generated here
with Pillow; what was kept is read by walking the bytes, never by Pillow. Invented English."""

from __future__ import annotations

import dataclasses
import io
import struct
import zlib
from typing import Any

import pytest
from PIL import Image, ImageFile
from PIL.PngImagePlugin import PngInfo

from editing import images

pytestmark = pytest.mark.fast

MIB = 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
KEPT_PNG_CHUNKS = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"pHYs"}
SOF_MARKERS = {*range(0xC0, 0xC4), *range(0xC5, 0xC8), *range(0xC9, 0xCC), *range(0xCD, 0xD0)}
APP1, COM, SOS = 0xE1, 0xFE, 0xDA
ORIENTATION, GPS_IFD, IMAGE_DESCRIPTION = 0x0112, 0x8825, 0x010E


# Generating the images.


def png(size: tuple[int, int] = (16, 12), mode: str = "RGB", **params: Any) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size).save(buffer, "PNG", **params)
    return buffer.getvalue()


def jpeg(size: tuple[int, int] = (64, 48), mode: str = "RGB", **params: Any) -> bytes:
    buffer = io.BytesIO()
    Image.linear_gradient("L").resize(size).convert(mode).save(buffer, "JPEG", **params)
    return buffer.getvalue()


def gif(size: tuple[int, int] = (8, 6), **params: Any) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", size, 128).save(buffer, "GIF", **params)
    return buffer.getvalue()


def exif_with(orientation: int | None = None, order: str = "<", gps: bool = False) -> Image.Exif:
    """EXIF in the byte order `order` (`<` little-endian, `>` big-endian) with a description,
    and the orientation and an invented GPS position when asked."""
    exif = Image.Exif()
    exif.endian = order
    exif[IMAGE_DESCRIPTION] = "A synthetic description"
    if orientation is not None:
        exif[ORIENTATION] = orientation
    if gps:
        exif[GPS_IFD] = {1: "N", 2: (12.0, 34.0, 56.0), 3: "E", 4: (65.0, 43.0, 21.0)}
    return exif


def ftyp(brand: bytes) -> bytes:
    return b"\x00\x00\x00\x14ftyp" + brand + b"\x00\x00\x00\x00" + brand


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def header_only_png(width: int, height: int) -> bytes:
    """A signature and an `IHDR` claiming the size, and nothing after it."""
    return PNG_SIGNATURE + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))


def webp() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, "WEBP")
    return buffer.getvalue()


def other_format(name: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, name)
    return buffer.getvalue()


def minimal_app1(order: str, value: int) -> bytes:
    """An `APP1` holding EXIF with the orientation alone (DL-0472)."""
    head = b"II*\x00" if order == "<" else b"MM\x00*"
    tiff = head + struct.pack(f"{order}I", 8)
    entry = struct.pack(f"{order}HHI", ORIENTATION, 3, 1) + struct.pack(f"{order}H", value)
    ifd = struct.pack(f"{order}H", 1) + entry + b"\x00\x00" + struct.pack(f"{order}I", 0)
    payload = b"Exif\x00\x00" + tiff + ifd
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def jpeg_segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def application_extension(identifier: bytes, payload: bytes) -> bytes:
    return b"\x21\xff\x0b" + identifier + bytes([len(payload)]) + payload + b"\x00"


# Walking the bytes.


def png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Each chunk as its type and its whole bytes: length, type, data, CRC."""
    assert data[:8] == PNG_SIGNATURE
    chunks = []
    pos = 8
    while pos < len(data):
        end = pos + 12 + int.from_bytes(data[pos : pos + 4], "big")
        chunks.append((data[pos + 4 : pos + 8], data[pos:end]))
        pos = end
    return chunks


def png_types(data: bytes) -> list[bytes]:
    return [kind for kind, _ in png_chunks(data)]


def jpeg_segments(data: bytes) -> list[tuple[int, bytes]]:
    """Each marker segment as its marker and its bytes, contiguous from `SOI` to `EOI`; an `SOS`
    segment carries its entropy-coded data, `RSTn` and stuffed `FF00` included."""
    assert data[:2] == b"\xff\xd8"
    segments = [(0xD8, data[:2])]
    pos = 2
    while pos < len(data):
        assert data[pos] == 0xFF
        start = pos
        while data[pos] == 0xFF:
            pos += 1
        marker = data[pos]
        pos += 1
        if marker == 0xD9:
            segments.append((marker, data[start:pos]))
            break
        pos += int.from_bytes(data[pos : pos + 2], "big")
        if marker == SOS:
            while not (data[pos] == 0xFF and data[pos + 1] not in {0x00, *range(0xD0, 0xD8)}):
                pos += 1
        segments.append((marker, data[start:pos]))
    return segments


def jpeg_markers(data: bytes) -> list[int]:
    return [marker for marker, _ in jpeg_segments(data)]


def app1_segments(data: bytes) -> list[bytes]:
    return [segment for marker, segment in jpeg_segments(data) if marker == APP1]


def from_first_scan(data: bytes) -> bytes:
    """Everything from the first `SOS` to `EOI`."""
    segments = jpeg_segments(data)
    first = next(i for i, (marker, _) in enumerate(segments) if marker == SOS)
    return b"".join(segment for _, segment in segments[first:])


def sof_offset(data: bytes) -> int:
    pos = 0
    for marker, segment in jpeg_segments(data):
        if marker in SOF_MARKERS:
            return pos
        pos += len(segment)
    raise AssertionError("no SOFn")


def with_jpeg_size(data: bytes, width: int, height: int) -> bytes:
    """The JPEG with its first `SOFn` claiming another size."""
    at = sof_offset(data) + 5
    return data[:at] + struct.pack(">HH", height, width) + data[at + 4 :]


def spliced_after_app0(data: bytes, *extra: bytes) -> bytes:
    segments = [segment for _, segment in jpeg_segments(data)]
    assert jpeg_markers(data)[1] == 0xE0
    return b"".join([segments[0], segments[1], *extra, *segments[2:]])


def gif_blocks(data: bytes) -> list[bytes]:
    """The header with its global colour table, then each extension and image, then the
    trailer, as whole bytes."""

    def colour_table(packed: int) -> int:
        return 3 << ((packed & 0x07) + 1) if packed & 0x80 else 0

    pos = 13 + colour_table(data[10])
    blocks = [data[:pos]]
    while data[pos] != 0x3B:
        start = pos
        if data[pos] == 0x21:
            pos += 2
        else:
            assert data[pos] == 0x2C
            pos += 10 + colour_table(data[pos + 9]) + 1
        while data[pos]:
            pos += data[pos] + 1
        pos += 1
        blocks.append(data[start:pos])
    blocks.append(data[pos : pos + 1])
    return blocks


def is_gif_comment(block: bytes) -> bool:
    return block[:2] == b"\x21\xfe"


def gif_application(block: bytes) -> bytes | None:
    return block[3:14] if block[:3] == b"\x21\xff\x0b" else None


def with_gif_block(data: bytes, block: bytes) -> bytes:
    """The GIF with `block` placed straight after its header."""
    blocks = gif_blocks(data)
    return b"".join([blocks[0], block, *blocks[1:]])


def with_gif_size(data: bytes, width: int, height: int) -> bytes:
    return data[:6] + struct.pack("<HH", width, height) + data[10:]


# Reading the refusals.


def refusal(data: bytes) -> tuple[str, dict[str, int]]:
    with pytest.raises(images.ImageRefused) as caught:
        images.check(data)
    return caught.value.code, caught.value.params


def dimensions(width: int, height: int) -> tuple[str, dict[str, int]]:
    params = {"width": width, "height": height, "max_side": 10_000, "max_pixels": 40_000_000}
    return "dimensions", params


# Metadata and refusals.


def test_metadata_is_stripped_without_decoding() -> None:
    text = PngInfo()
    text.add_text("Comment", "A synthetic note about the drawing")
    tagged_png = png(pnginfo=text, exif=exif_with(orientation=6))
    located = jpeg(exif=exif_with(orientation=6, gps=True), comment=b"A synthetic comment")
    unrotatable = jpeg(exif=exif_with(orientation=9))
    commented_gif = gif(comment=b"A synthetic comment")
    assert {b"tEXt", b"eXIf"} <= set(png_types(tagged_png))
    assert {APP1, COM} <= set(jpeg_markers(located))
    assert APP1 in jpeg_markers(unrotatable)
    assert any(is_gif_comment(block) for block in gif_blocks(commented_gif))

    checked_png = images.check(tagged_png)
    checked_located = images.check(located)
    checked_unrotatable = images.check(unrotatable)
    checked_gif = images.check(commented_gif)

    assert app1_segments(checked_located.data) == [minimal_app1("<", 6)]
    assert COM not in jpeg_markers(checked_located.data)
    assert from_first_scan(checked_located.data) == from_first_scan(located)
    assert APP1 not in jpeg_markers(checked_unrotatable.data)
    assert not {b"tEXt", b"eXIf"} & set(png_types(checked_png.data))
    assert not any(is_gif_comment(block) for block in gif_blocks(checked_gif.data))


def test_refusals_name_their_rule(settings: Any) -> None:
    settings.UPLOAD_MAX_BYTES = 20 * MIB
    cases = [
        (ftyp(b"heic"), ("heic", {})),
        (SVG, ("type", {})),
        (webp(), ("type", {})),
        (PNG_SIGNATURE + bytes(11 * MIB - 8), ("too_large", {"limit_mb": 10})),
        (png((12_000, 10), mode="1"), dimensions(12_000, 10)),
        (png((7_000, 7_000), mode="1"), dimensions(7_000, 7_000)),
        (header_only_png(20_000, 10_000), dimensions(20_000, 10_000)),
        (png()[:20], ("unreadable", {})),
    ]
    for data, expected in cases:
        assert refusal(data) == expected

    settings.UPLOAD_MAX_BYTES = 5 * MIB
    six_mb = png((2_500, 2_500), mode="L", compress_level=0)
    assert 5 * MIB < len(six_mb) < 10 * MIB
    assert refusal(six_mb) == ("too_large", {"limit_mb": 5})


# The limits.


def test_the_platforms_limits() -> None:
    assert images.MAX_BYTES == 10 * 1024 * 1024
    assert images.MAX_PIXELS == 40_000_000
    assert images.MAX_SIDE == 10_000


def test_limit_is_the_smaller_of_the_ceiling_and_the_setting(settings: Any) -> None:
    settings.UPLOAD_MAX_BYTES = 20 * MIB
    assert images.limit() == 10 * MIB
    settings.UPLOAD_MAX_BYTES = 5 * MIB
    assert images.limit() == 5 * MIB


def test_limit_is_read_on_each_call(settings: Any) -> None:
    four_mb = PNG_SIGNATURE + bytes(4 * MIB - 8)
    settings.UPLOAD_MAX_BYTES = 5 * MIB
    assert refusal(four_mb)[0] == "unreadable"
    settings.UPLOAD_MAX_BYTES = 3 * MIB
    assert images.limit() == 3 * MIB
    assert refusal(four_mb) == ("too_large", {"limit_mb": 3})


def test_too_large_names_whole_megabytes_rounded_down(settings: Any) -> None:
    settings.UPLOAD_MAX_BYTES = 5 * MIB + MIB // 2
    assert refusal(PNG_SIGNATURE + bytes(6 * MIB)) == ("too_large", {"limit_mb": 5})


def test_an_upload_of_exactly_the_limit_passes(settings: Any) -> None:
    data = png()
    settings.UPLOAD_MAX_BYTES = len(data)
    assert images.check(data).data == data
    settings.UPLOAD_MAX_BYTES = len(data) - 1
    assert refusal(data) == ("too_large", {"limit_mb": 0})


def test_size_is_checked_before_the_type(settings: Any) -> None:
    settings.UPLOAD_MAX_BYTES = 20 * MIB
    for data in (SVG + b" " * (11 * MIB), ftyp(b"heic") + bytes(11 * MIB)):
        assert refusal(data) == ("too_large", {"limit_mb": 10})


# The type.


@pytest.mark.parametrize("brand", [b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"])
def test_every_heic_brand_is_named_heic(brand: bytes) -> None:
    assert refusal(ftyp(brand)) == ("heic", {})


@pytest.mark.parametrize(
    "data",
    [
        SVG,
        pytest.param(b"", id="empty"),
        pytest.param(ftyp(b"isom"), id="mp4"),
        pytest.param(b"GIF88a" + bytes(16), id="gif88a"),
        pytest.param(b"\xff\xd8" + bytes(16), id="jpeg-two-bytes"),
        pytest.param(b"\x89PNG\r\n\x1a" + bytes(16), id="png-seven-bytes"),
    ],
)
def test_every_other_signature_is_type(data: bytes) -> None:
    assert refusal(data) == ("type", {})


@pytest.mark.parametrize("name", ["WEBP", "BMP", "TIFF"])
def test_other_formats_pillow_writes_are_type(name: str) -> None:
    assert refusal(other_format(name)) == ("type", {})


# The dimensions.


@pytest.mark.parametrize("size", [(12_000, 10), (10, 12_000), (7_000, 7_000)])
@pytest.mark.parametrize("kind", ["baseline jpeg", "progressive jpeg", "gif"])
def test_dimensions_are_read_from_the_header(kind: str, size: tuple[int, int]) -> None:
    width, height = size
    if kind == "gif":
        data = with_gif_size(gif(), width, height)
    else:
        data = with_jpeg_size(jpeg(progressive=kind == "progressive jpeg"), width, height)
    assert refusal(data) == dimensions(width, height)


def test_a_side_and_a_product_at_their_maxima_pass() -> None:
    checked = images.check(png((10_000, 4_000), mode="1"))
    assert (checked.width, checked.height) == (10_000, 4_000)
    assert refusal(png((10_000, 4_001), mode="1")) == dimensions(10_000, 4_001)


def test_pillows_bomb_error_is_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    assert refusal(png((20, 20))) == dimensions(0, 0)


# Pillow's bomb warning is no refusal: the header's own limits are lower than Pillow's.
@pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
def test_pillows_bomb_warning_is_not_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 300)
    assert images.check(png((20, 20))).width == 20


# Unreadable.


def corrupted_idat() -> bytes:
    data = png()
    pos = 8
    for kind, chunk in png_chunks(data):
        if kind == b"IDAT":
            break
        pos += len(chunk)
    at = pos + 8
    return data[:at] + bytes([data[at] ^ 0xFF]) + data[at + 1 :]


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(PNG_SIGNATURE + b"\x00\x00\x00\x0dIHDR", id="png-cut-in-ihdr"),
        pytest.param(PNG_SIGNATURE + png_chunk(b"IEND", b""), id="png-without-ihdr"),
        pytest.param(header_only_png(10, 10), id="png-header-only"),
        pytest.param(corrupted_idat(), id="png-bad-idat-crc"),
        pytest.param(b"\xff\xd8\xff\xd9", id="jpeg-without-sof"),
        pytest.param(
            b"\xff\xd8" + jpeg_segment(SOS, b"\x01\x01\x00\x00\x3f\x00") + b"\x12\x34\xff\xd9",
            id="jpeg-scan-before-sof",
        ),
        pytest.param(jpeg()[: sof_offset(jpeg()) + 6], id="jpeg-cut-in-sof"),
        pytest.param(b"GIF89a\x08\x00\x06", id="gif-short-descriptor"),
    ],
)
def test_what_does_not_read_is_unreadable(data: bytes) -> None:
    assert refusal(data) == ("unreadable", {})


# PNG stripping.


def test_png_keeps_its_rendering_chunks_byte_for_byte() -> None:
    picture = Image.new("P", (16, 12))
    picture.putpalette([0, 0, 0, 255, 255, 255])
    info = PngInfo()
    info.add(b"gAMA", struct.pack(">I", 45455))
    info.add(b"cHRM", struct.pack(">8I", 31270, 32900, 64000, 33000, 30000, 60000, 15000, 6000))
    info.add(b"sRGB", b"\x00")
    info.add_text("Comment", "A synthetic note")
    buffer = io.BytesIO()
    picture.save(buffer, "PNG", pnginfo=info, transparency=0, dpi=(300, 300))
    data = buffer.getvalue()
    assert KEPT_PNG_CHUNKS <= set(png_types(data))

    kept = [chunk for kind, chunk in png_chunks(data) if kind in KEPT_PNG_CHUNKS]
    assert images.check(data).data == PNG_SIGNATURE + b"".join(kept)


def test_png_drops_iccp_and_time_and_keeps_phys() -> None:
    info = PngInfo()
    info.add(b"tIME", struct.pack(">HBBBBB", 2000, 1, 1, 0, 0, 0))
    data = png(pnginfo=info, icc_profile=b"A synthetic profile", dpi=(72, 72))
    assert {b"iCCP", b"tIME", b"pHYs"} <= set(png_types(data))

    stripped = images.check(data).data
    assert png_types(stripped) == [b"IHDR", b"pHYs", b"IDAT", b"IEND"]
    phys = [chunk for kind, chunk in png_chunks(data) if kind == b"pHYs"]
    assert [chunk for kind, chunk in png_chunks(stripped) if kind == b"pHYs"] == phys


def test_png_drops_every_other_chunk_before_or_after_the_image_data() -> None:
    info = PngInfo()
    info.add_text("Title", "A synthetic title", zip=True)
    info.add_itxt("Author", "A synthetic author")
    info.add(b"prVb", b"private before")
    info.add(b"prVa", b"private after", after_idat=True)
    data = png(pnginfo=info)
    assert {b"zTXt", b"iTXt", b"prVb", b"prVa"} <= set(png_types(data))

    assert png_types(images.check(data).data) == [b"IHDR", b"IDAT", b"IEND"]


# JPEG stripping.


def test_jpeg_keeps_its_coding_segments_and_drops_the_rest() -> None:
    base = jpeg(
        xmp=b"<x:xmpmeta>A synthetic packet</x:xmpmeta>",
        icc_profile=b"A synthetic profile",
        comment=b"A synthetic comment",
    )
    extra = [jpeg_segment(marker, b"synthetic") for marker in (*range(0xE3, 0xEE), 0xEF)]
    data = spliced_after_app0(base, *extra)
    dropped = {*range(0xE1, 0xEE), 0xEF, COM}
    assert {APP1, 0xE2, COM} <= set(jpeg_markers(data))

    kept = [segment for marker, segment in jpeg_segments(data) if marker not in dropped]
    assert images.check(data).data == b"".join(kept)


def test_jpeg_keeps_the_adobe_segment() -> None:
    data = jpeg(mode="CMYK")
    assert 0xEE in jpeg_markers(data)

    assert images.check(data).data == data


def test_jpeg_scans_are_copied_with_their_restarts() -> None:
    data = jpeg((64, 64), restart_marker_rows=1, progressive=True, comment=b"A synthetic comment")
    assert jpeg_markers(data).count(SOS) > 1
    assert 0xDD in jpeg_markers(data)

    stripped = images.check(data).data
    assert from_first_scan(stripped) == from_first_scan(data)
    assert jpeg_markers(stripped) == [m for m in jpeg_markers(data) if m != COM]


def test_the_minimal_app1_stands_where_the_exif_stood() -> None:
    data = jpeg(exif=exif_with(orientation=6), comment=b"A synthetic comment")

    stripped = images.check(data).data
    assert jpeg_markers(stripped) == [m for m in jpeg_markers(data) if m != COM]
    assert app1_segments(stripped) == [minimal_app1("<", 6)]


@pytest.mark.parametrize("orientation", [1, 8])
def test_the_minimal_app1_carries_any_orientation_from_one_to_eight(orientation: int) -> None:
    data = jpeg(exif=exif_with(orientation=orientation))

    assert app1_segments(images.check(data).data) == [minimal_app1("<", orientation)]


def test_the_minimal_app1_keeps_a_big_endian_byte_order() -> None:
    data = jpeg(exif=exif_with(orientation=3, order=">", gps=True))
    assert app1_segments(data)[0][10:14] == b"MM\x00*"

    assert app1_segments(images.check(data).data) == [minimal_app1(">", 3)]


@pytest.mark.parametrize("orientation", [None, 0, 9])
def test_exif_without_an_orientation_from_one_to_eight_is_dropped(orientation: int | None) -> None:
    data = jpeg(exif=exif_with(orientation=orientation, gps=True))
    assert APP1 in jpeg_markers(data)

    assert APP1 not in jpeg_markers(images.check(data).data)


# An APP0 that is not JFIF is dropped: a JFXX segment carries a thumbnail of the picture.
def test_an_app0_that_is_not_jfif_is_dropped() -> None:
    base = jpeg()
    jfxx = jpeg_segment(0xE0, b"JFXX\x00\x10" + bytes(32))
    data = spliced_after_app0(base, jfxx)

    assert images.check(data).data == base


# GIF stripping.


def test_gif_keeps_netscape_and_drops_another_application_extension() -> None:
    other = application_extension(b"SYNTHETC1.0", b"synthetic data")
    data = with_gif_block(gif(loop=0), other)
    assert [gif_application(b) for b in gif_blocks(data) if gif_application(b)] == [
        b"SYNTHETC1.0",
        b"NETSCAPE2.0",
    ]

    kept = [block for block in gif_blocks(data) if block != other]
    assert images.check(data).data == b"".join(kept)


def test_gif_keeps_every_other_block_byte_for_byte() -> None:
    first, second = Image.new("L", (8, 6), 0), Image.new("L", (8, 6), 255)
    buffer = io.BytesIO()
    first.save(
        buffer,
        "GIF",
        save_all=True,
        append_images=[second],
        duration=100,
        loop=0,
        comment=b"A synthetic comment",
    )
    data = buffer.getvalue()
    blocks = gif_blocks(data)
    assert any(block[:2] == b"\x21\xf9" for block in blocks)
    assert sum(block[:1] == b"\x2c" for block in blocks) == 2

    kept = [block for block in blocks if not is_gif_comment(block)]
    assert images.check(data).data == b"".join(kept)


# What comes back.


@pytest.mark.parametrize("make", [png, jpeg, gif])
def test_an_image_with_nothing_to_strip_comes_back_unchanged(make: Any) -> None:
    data = make()

    assert images.check(data).data == data


def test_no_image_is_decoded(monkeypatch: pytest.MonkeyPatch) -> None:
    text = PngInfo()
    text.add_text("Comment", "A synthetic note")
    uploads = [
        png(pnginfo=text),
        jpeg(exif=exif_with(orientation=6), comment=b"A synthetic comment"),
        gif(comment=b"A synthetic comment"),
    ]

    def decode(self: Any) -> None:
        raise AssertionError("an image was decoded")

    monkeypatch.setattr(ImageFile.ImageFile, "load", decode)
    for data in uploads:
        images.check(data)


def test_checked_reports_the_format_and_the_size_as_stored() -> None:
    rotated = jpeg((40, 20), exif=exif_with(orientation=6))
    cases = [(png((30, 10)), "png"), (rotated, "jpg"), (gif((12, 7)), "gif")]
    sizes = {"png": (30, 10), "jpg": (40, 20), "gif": (12, 7)}
    for data, ext in cases:
        checked = images.check(data)
        assert isinstance(checked, images.Checked)
        assert checked.ext == ext
        assert (checked.width, checked.height) == sizes[ext]

    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(images.check(png()), "ext", "gif")  # noqa: B010


def test_a_refusal_carries_its_code_and_params() -> None:
    bare = images.ImageRefused("heic")
    named = images.ImageRefused("too_large", {"limit_mb": 10})

    assert isinstance(bare, Exception)
    assert (bare.code, bare.params) == ("heic", {})
    assert (named.code, named.params) == ("too_large", {"limit_mb": 10})


# Frames, thumbnails and extensions a viewer reads past.


def test_a_gif_frame_larger_than_its_screen_is_measured() -> None:
    """A frame is laid out on the screen it extends: the extent of every frame is the image's
    size, however small the logical screen claims to be."""
    data = with_gif_size(gif((2, 2)), 1, 1)
    blocks = gif_blocks(data)
    frame = next(i for i, block in enumerate(blocks) if block[:1] == b"\x2c")
    descriptor = blocks[frame]
    blocks[frame] = descriptor[:5] + struct.pack("<HH", 20_000, 8_000) + descriptor[9:]
    assert refusal(b"".join(blocks)) == dimensions(20_000, 8_000)


def test_an_animation_is_measured_by_every_frame() -> None:
    """An animation's frames are each decoded: their pixels together are held to the limit."""
    frames = [Image.new("L", (2_000, 2_000), shade) for shade in range(11)]
    buffer = io.BytesIO()
    frames[0].save(buffer, "GIF", save_all=True, append_images=frames[1:])
    code, params = refusal(buffer.getvalue())
    assert code == "dimensions" and params["width"] == params["height"] == 2_000


def test_a_jfif_thumbnail_and_its_trailing_bytes_are_dropped() -> None:
    base = jpeg()
    thumbnail = b"JFIF\x00\x01\x02\x01\x00\x48\x00\x48\x01\x01" + b"\x10\x20\x30"
    jfif = jpeg_segment(0xE0, thumbnail + b"Author: an invented name")
    segments = [segment for _, segment in jpeg_segments(base)]
    data = b"".join([segments[0], jfif, *segments[2:]])
    stripped = images.check(data).data
    app0 = [segment for marker, segment in jpeg_segments(stripped) if marker == 0xE0]
    assert app0 == [jpeg_segment(0xE0, thumbnail[:12] + b"\x00\x00")]
    assert b"Author" not in stripped


def test_gif_extensions_are_an_allow_list() -> None:
    """The graphic control extension and the loop count stand; any other extension — plain text,
    a label no decoder knows, bytes after the loop count — goes."""
    netscape = application_extension(b"NETSCAPE2.0", b"\x01\x00\x00")[:-1] + b"\x05extra\x00"
    plain_text = b"\x21\x01\x0c" + bytes(12) + b"\x05words\x00"
    unknown = b"\x21\x99\x05words\x00"
    data = gif((4, 4))
    for block in (netscape, plain_text, unknown):
        data = with_gif_block(data, block)
    stripped = images.check(data).data
    assert b"words" not in stripped and b"extra" not in stripped
    assert application_extension(b"NETSCAPE2.0", b"\x01\x00\x00") in stripped


def test_a_jpeg_with_two_frames_is_unreadable() -> None:
    base = jpeg()
    segments = jpeg_segments(base)
    frame = next(segment for marker, segment in segments if marker == 0xC0)
    data = base.replace(
        frame, frame + frame[:5] + struct.pack(">HH", 12_000, 12_000) + frame[9:], 1
    )
    assert refusal(data)[0] == "unreadable"


@pytest.mark.budget
def test_a_scan_of_fill_bytes_is_walked_quickly() -> None:
    import time

    base = jpeg()
    at = base.index(b"\xff\xda")
    length = struct.unpack(">H", base[at + 2 : at + 4])[0]
    data = base[: at + 2 + length] + b"\xff" * 9_500_000 + b"\xd9"
    started = time.perf_counter()
    # Fill before a marker is allowed: what matters is that the walk does not crawl over it.
    images.check(data)
    assert time.perf_counter() - started < 1.0


def test_a_png_has_one_header() -> None:
    """A second `IHDR` would be read as the image's size by a library that reads the last one:
    the file is refused, whatever the first claims."""
    small = png((1, 1))
    second = png_chunk(b"IHDR", struct.pack(">IIBBBBB", 9_000, 9_000, 8, 2, 0, 0, 0))
    # The signature and the first IHDR are 33 bytes.
    assert refusal(small[:33] + second + small[33:])[0] == "unreadable"


def test_an_adobe_segment_keeps_its_rendering_fields_alone() -> None:
    base = jpeg(mode="CMYK")
    segments = jpeg_segments(base)
    adobe = next(segment for marker, segment in segments if marker == 0xEE)
    fields = adobe[4:16]
    padded = jpeg_segment(0xEE, fields + b"Location: an invented place")
    foreign = jpeg_segment(0xEE, b"Other\x00 invented application data")
    for replaced in (padded, foreign):
        stripped = images.check(base.replace(adobe, replaced, 1)).data
        kept = [segment for marker, segment in jpeg_segments(stripped) if marker == 0xEE]
        assert b"invented" not in stripped
        assert kept == ([jpeg_segment(0xEE, fields)] if replaced is padded else [])
