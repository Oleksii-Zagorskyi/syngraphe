-- The platform's classes as named Word styles (ADR-0013): a span's class sets its character
-- style, a callout's paragraphs take the callout's paragraph style. Pandoc never decides what the
-- document contains; the reference document carries each style's look.
local SPANS = {
  ["entity-role"] = "Entity Role",
  ["entity-action"] = "Entity Action",
  ["entity-term"] = "Entity Term",
  ["underline"] = "Underline",
  ["num"] = "Clause Number",
}

local CALLOUTS = {
  ["callout-note"] = "Callout Note",
  ["callout-warning"] = "Callout Warning",
  ["callout-example"] = "Callout Example",
}

function Span(span)
  -- A change of formatting alone: the text as it now reads, never its earlier form.
  if span.classes:includes("format-old") then
    return {}
  end
  if span.classes:includes("format-changed") then
    -- Marked by its colour alone: the words naming the change are the screen's (DL-0363).
    span.attributes["custom-style"] = "Format Changed"
    return span
  end
  for _, class in ipairs(span.classes) do
    local style = SPANS[class]
    if style then
      span.attributes["custom-style"] = style
      return span
    end
  end
end

-- A page of its own for the parts the platform generates: the title page ends one, the
-- attachment list begins one.
local PAGE = pandoc.RawBlock("openxml", '<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

-- An image pair stands side by side, as on the page: a row of two equal cells, each holding one
-- side's figure; `docx.py` fits each picture to its cell.
local function pair(div)
  local cells = {}
  for _, block in ipairs(div.content) do
    cells[#cells + 1] = { block }
  end
  local widths = {}
  local aligns = {}
  for i = 1, #cells do
    widths[i] = 1 / #cells
    aligns[i] = "AlignDefault"
  end
  return pandoc.utils.from_simple_table(pandoc.SimpleTable({}, aligns, widths, {}, { cells }))
end

function Div(div)
  if div.classes:includes("imgpair") then
    return pair(div)
  end
  for _, class in ipairs(div.classes) do
    local style = CALLOUTS[class]
    if style then
      div.attributes["custom-style"] = style
      return div
    end
    if class == "title-page" then
      return { div, PAGE }
    end
    if class == "attachment-list" then
      return { PAGE, div }
    end
  end
end

-- A marked export's insertions and deletions arrive as `<ins>` and `<del>`, which Pandoc reads as
-- underline and strike-out; each takes a style of its own, so an insertion never looks like the
-- *Underline* span.
function Underline(el)
  return pandoc.Span(el.content, { ["custom-style"] = "Inserted" })
end

function Strikeout(el)
  return pandoc.Span(el.content, { ["custom-style"] = "Deleted" })
end

-- A heading's number is part of the heading and takes its look, not a clause number's (DL-0363):
-- its span is unwrapped, so the heading's own style sets it.
function Header(header)
  header.content = header.content:walk({
    Span = function(span)
      if span.classes:includes("num") then
        return span.content
      end
    end,
  })
  return header
end

-- The page's `<title>` names the export for the PDF's metadata; Pandoc would print it at the top
-- of the document as a title paragraph, the header DL-0362 removed. A DOCX has no such line.
function Meta(meta)
  meta.title = nil
  return meta
end
