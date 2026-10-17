// The whitelist specification as both sides read it: `src/editing/whitelist/spec.json`, its
// patterns compiled. `src/editing/markdown/__init__.py::spec_from` is the Python reading.
import raw from "../whitelist/spec.json" with { type: "json" };

export const rawSpec = raw;

export function specFrom(data) {
  return {
    version: data.version,
    maxBytes: data.maxBytes,
    headingMaxDepth: data.headingMaxDepth,
    listMaxDepth: data.listMaxDepth,
    spans: Object.fromEntries(Object.entries(data.spans).map(([name, value]) => [name, Boolean(value.id)])),
    calloutTypes: [...data.calloutTypes],
    quotes: data.quotes,
    headingsTopLevelOnly: data.headingsTopLevelOnly,
    tablesTopLevelOnly: data.tablesTopLevelOnly,
    imageAlone: data.imageAlone,
    imageSrc: new RegExp(data.imageSrc),
    linkSchemes: new RegExp(data.linkSchemes, "i"),
    mentionId: new RegExp(data.mentionId),
    refusals: data.refusals,
  };
}

export const spec = specFrom(raw);
