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

function Div(div)
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
