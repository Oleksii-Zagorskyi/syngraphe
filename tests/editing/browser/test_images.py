"""Images in the editor (DL-0232, DL-0253, DL-0472): chosen, pasted or dropped, uploaded and
placed as a paragraph of its own after the block holding the cursor; shown through the draft's
image route, an oriented photograph upright; the editor's own image kept when it is pasted back.
Images are invented by Pillow; text is invented."""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Any

import pytest

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"

# The document's blocks as types, each paragraph's children named, for the placement checks.
SHAPE = """() => {
  const shape = (node) => node.type.name === "paragraph"
    ? ["paragraph", node.content.content.map((child) => child.type.name)]
    : [node.type.name, node.content.content.map(shape)];
  return document.getElementById("editor").editor.view.state.doc.content.content.map(shape);
}"""

IMAGES = "() => document.querySelectorAll('#editor .editor-surface span.image img').length"

TRANSFER = """([kind, html, text, files]) => {
  const data = new DataTransfer();
  if (html) data.setData("text/html", html);
  if (text) data.setData("text/plain", text);
  for (const [name, type, b64] of files) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    data.items.add(new File([bytes], name, { type }));
  }
  const editor = document.getElementById("editor").editor;
  editor.view.focus();
  document.querySelector(".editor-status").textContent = "";
  if (kind === "paste") {
    const init = { clipboardData: data, bubbles: true, cancelable: true };
    editor.view.dom.dispatchEvent(new ClipboardEvent("paste", init));
  } else {
    const box = editor.view.dom.querySelector("p").getBoundingClientRect();
    const at = { clientX: box.left + 2, clientY: box.top + 2 };
    const init = { dataTransfer: data, bubbles: true, cancelable: true, ...at };
    editor.view.dom.dispatchEvent(new DragEvent("drop", init));
  }
}"""


def choose(page: Any, data: bytes, name: str = "plan.png", mime: str = "image/png") -> None:
    page.set_input_files(
        "#editor input[data-field=image]", {"name": name, "mimeType": mime, "buffer": data}
    )


def transfer(page: Any, kind: str, html: str = "", text: str = "", files: list[Any] = ()) -> None:
    encoded = [[n, t, base64.b64encode(d).decode()] for n, t, d in files]
    page.evaluate(TRANSFER, [kind, html, text, encoded])


def test_an_uploaded_image_stands_alone(editing: Any, page: Any, invented_image: Any) -> None:
    editing("- First item\n- Second item\n")
    page.evaluate(f"{EDITOR}.select(4)")
    choose(page, invented_image("png"))
    page.wait_for_function(f"{IMAGES} === 1")
    [items] = page.evaluate(SHAPE)
    assert items == [
        "bullet_list",
        [
            ["list_item", [["paragraph", ["text"]], ["paragraph", ["image"]]]],
            ["list_item", [["paragraph", ["text"]]]],
        ],
    ]

    page.evaluate(f"{EDITOR}.replace('word\\n\\n| a | b |\\n| --- | --- |\\n| c | d |\\n')")
    page.evaluate(f"{EDITOR}.select(10)")
    choose(page, invented_image("png", shade=1))
    page.wait_for_function(f"{IMAGES} === 1")
    assert [block[0] for block in page.evaluate(SHAPE)][:3] == ["paragraph", "table", "paragraph"]
    assert page.evaluate(SHAPE)[2] == ["paragraph", ["image"]]


def test_an_oriented_photograph_stands_upright(
    editing: Any, page: Any, invented_image: Any
) -> None:
    editing("A sentence.\n")
    page.evaluate(f"{EDITOR}.select(1)")
    choose(page, invented_image("jpeg", 40, 20, orientation=6), "photo.jpg", "image/jpeg")
    page.wait_for_function(
        "() => { const i = document.querySelector('#editor span.image img');"
        " return i && i.complete && i.naturalWidth > 0; }"
    )
    box = page.locator("#editor span.image img").bounding_box()
    assert box["height"] > box["width"]


def test_paste_and_drop_upload(
    editing: Any, markdown: Any, page: Any, invented_image: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    editing("A first sentence.\n")
    page.evaluate(f"{EDITOR}.select(1)")
    transfer(page, "paste", files=[("screen.png", "image/png", invented_image("png", shade=2))])
    page.wait_for_function(f"{IMAGES} === 1")
    inline = base64.b64encode(invented_image("gif")).decode()
    transfer(page, "paste", html=f"<p><img src='data:image/gif;base64,{inline}'></p>", text="")
    page.wait_for_function(f"{IMAGES} === 2")
    transfer(page, "drop", files=[("drop.png", "image/png", invented_image("png", shade=3))])
    page.wait_for_function(f"{IMAGES} === 3")
    assert all(block == ["paragraph", ["image"]] for block in page.evaluate(SHAPE)[1:])

    transfer(
        page,
        "paste",
        html="<p>Kept <img src='https://example.org/a.png'> words</p>",
        text="Kept words",
    )
    page.wait_for_timeout(100)
    assert "copy the image itself and paste it" in (page.text_content(".editor-status") or "")
    assert "Kept" in markdown() and "example.org" not in markdown()
    assert markdown().count("](images/") == 3


def test_the_editors_own_image_node_is_kept(
    editing: Any,
    markdown: Any,
    page: Any,
    invented_image: Any,
    migrated_tenant: Any,
    settings: Any,
) -> None:
    """An image paragraph pasted back is kept as it stands, with no notice; one naming an image
    this document does not hold is kept too, and refused at finishing by its line (DL-0439)."""
    settings.LANGUAGE_CODE = "en"
    editing("A first sentence.\n")
    page.evaluate(f"{EDITOR}.select(1)")
    choose(page, invented_image("png"))
    page.wait_for_function(f"{IMAGES} === 1")
    own = page.get_attribute("#editor span.image", "data-src")
    foreign = "images/" + hashlib.sha256(b"another document's image").hexdigest() + ".png"
    for src in (own, foreign):
        node = (
            f'<p><span class="image" data-src="{src}" data-alt="A plan"><img src="/x/"></span></p>'
        )
        transfer(page, "paste", html=node, text="")
        page.wait_for_timeout(100)
        assert (page.text_content(".editor-status") or "") == ""
    assert markdown().count(f"]({own})") == 2 and markdown().count(f"]({foreign})") == 1
    assert all(block[1] == ["image"] for block in page.evaluate(SHAPE)[1:])

    page.evaluate(f"async () => {{ await {EDITOR}.capture.finish(); }}")
    finishing = page.request.get(page.url.replace("/edit/", "/edit/finish/"))
    assert re.search(r"line \d+: an image the document does not hold", finishing.text())


def test_several_images_keep_their_order(
    editing: Any, markdown: Any, page: Any, invented_image: Any
) -> None:
    editing("A first sentence.\n")
    page.evaluate(f"{EDITOR}.select(1)")
    first, second = invented_image("gif", shade=10), invented_image("gif", shade=20)
    html = "".join(
        f"<p><img src='data:image/gif;base64,{base64.b64encode(data).decode()}'></p>"
        for data in (first, second)
    )
    transfer(page, "paste", html=html)
    page.wait_for_function(f"{IMAGES} === 2")
    stored = markdown()
    names = [hashlib.sha256(images_check(data)).hexdigest() for data in (first, second)]
    assert stored.index(names[0]) < stored.index(names[1])


def images_check(data: bytes) -> bytes:
    from editing import images

    return images.check(data).data


def test_a_drop_keeps_its_text(editing: Any, markdown: Any, page: Any, invented_image: Any) -> None:
    editing("A first sentence.\n")
    inline = base64.b64encode(invented_image("gif", shade=30)).decode()
    transfer(
        page,
        "drop",
        html=f"<p>Dropped words <img src='data:image/gif;base64,{inline}'></p>",
        text="Dropped words",
    )
    page.wait_for_function(f"{IMAGES} === 1")
    assert "Dropped words" in markdown()


def test_a_file_and_its_own_data_image_are_one_image(
    editing: Any, markdown: Any, page: Any, invented_image: Any
) -> None:
    editing("A first sentence.\n")
    page.evaluate(f"{EDITOR}.select(1)")
    data = invented_image("png", shade=40)
    html = f"<img src='data:image/png;base64,{base64.b64encode(data).decode()}'>"
    transfer(page, "paste", html=html, files=[("copied.png", "image/png", data)])
    page.wait_for_function(f"{IMAGES} === 1")
    page.wait_for_timeout(300)
    assert page.evaluate(IMAGES) == 1


def test_a_busy_or_failed_upload_says_so(
    editing: Any, page: Any, invented_image: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    editing("A first sentence.\n")
    page.evaluate(f"{EDITOR}.select(1)")
    upload = "**/edit/image/"
    page.route(upload, lambda route: route.fulfill(status=503, json={"busy": True}))
    choose(page, invented_image("png", shade=50))
    page.wait_for_function(
        "() => document.querySelector('.editor-status').textContent.includes('busy')"
    )
    page.unroute(upload)
    page.route(upload, lambda route: route.fulfill(status=500, body="no"))
    choose(page, invented_image("png", shade=51))
    status = "() => document.querySelector('.editor-status').textContent"
    page.wait_for_function(f"{status}.includes('The image was not added')")
    assert "Not captured" not in (page.text_content(".editor-status") or "")


def test_a_refused_upload_says_why(editing: Any, markdown: Any, page: Any, settings: Any) -> None:
    """The server's reason for refusing an image reaches the notice line: the type, and the
    dimensions read from the file's header; nothing is placed."""
    import struct
    import zlib

    settings.LANGUAGE_CODE = "en"
    editing("A first sentence.\n")
    page.evaluate(f"{EDITOR}.select(1)")
    status = "() => document.querySelector('.editor-status').textContent"

    choose(page, b'<svg xmlns="http://www.w3.org/2000/svg"/>', "plan.svg", "image/svg+xml")
    page.wait_for_function(f"{status}.includes('Only PNG, JPEG and GIF images are accepted.')")

    header = struct.pack(">IIBBBBB", 20_000, 10, 8, 2, 0, 0, 0)
    wide = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(header))
        + b"IHDR"
        + header
        + struct.pack(">I", zlib.crc32(b"IHDR" + header))
    )
    choose(page, wide, "wide.png")
    page.wait_for_function(f"{status}.includes('20000 × 10 pixels')")
    assert page.evaluate(IMAGES) == 0
    assert markdown() == "A first sentence.\n"


def test_a_batch_stays_together_beside_an_earlier_copy(
    editing: Any, markdown: Any, page: Any, invented_image: Any
) -> None:
    """Placing a batch never looks an image up by its name: an earlier copy of the same image
    elsewhere in the text does not draw the rest of the batch to it."""
    editing("A first sentence.\n\nA last sentence.\n")
    first, second = invented_image("gif", shade=60), invented_image("gif", shade=61)
    page.evaluate(f"{EDITOR}.select(22)")
    choose(page, first, "first.gif", "image/gif")
    page.wait_for_function(f"{IMAGES} === 1")
    page.evaluate(f"{EDITOR}.select(1)")
    html = "".join(
        f"<p><img src='data:image/gif;base64,{base64.b64encode(data).decode()}'></p>"
        for data in (first, second)
    )
    transfer(page, "paste", html=html)
    page.wait_for_function(f"{IMAGES} === 3")
    blocks = page.evaluate(SHAPE)
    assert [block[1] for block in blocks[:3]] == [["text"], ["image"], ["image"]]


def test_finishing_waits_for_an_upload_in_flight(
    editing: Any, page: Any, invented_image: Any, migrated_tenant: Any
) -> None:
    """An image still uploading when the editor is closed is placed and captured before the
    editor closes."""
    from editing.models import Draft
    from tenancy.schemas import schema_context

    document = editing("A sentence.\n")
    page.evaluate(
        """() => {
          const original = window.fetch;
          window.fetch = (url, init) => String(url).includes("/edit/image/")
            ? new Promise((resolve) => setTimeout(() => resolve(original(url, init)), 800))
            : original(url, init);
        }"""
    )
    page.evaluate(f"{EDITOR}.select(1)")
    choose(page, invented_image("png", shade=70))
    assert page.evaluate(f"async () => await {EDITOR}.capture.finish()") is True
    with schema_context(migrated_tenant.number):
        body = Draft.objects.get(hold__document=document).content["document.md"]
    assert "](images/" in body


def test_a_malformed_data_image_is_left_out_with_its_text_kept(
    editing: Any, markdown: Any, page: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    editing("A first sentence.\n")
    page.evaluate(f"{EDITOR}.select(1)")
    transfer(
        page,
        "paste",
        html="<p>Kept words <img src='data:image/png;base64,A'></p>",
        text="Kept words",
    )
    page.wait_for_timeout(200)
    assert "Kept words" in markdown()
    assert "copy the image itself" in (page.text_content(".editor-status") or "")
