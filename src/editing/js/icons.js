// The toolbar's icons (DL-0365): drawn here as inline SVG, no icon library; each button keeps its
// word as tooltip and accessible name. A 20-unit box, stroked in the text's colour.

const svg = (body) =>
  `<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false" ` +
  `fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" ` +
  `stroke-linejoin="round">${body}</svg>`;

// A letter or two set as the icon, for the controls whose sign is a letter.
const glyph = (text, style = "") =>
  svg(
    `<text x="10" y="14.5" text-anchor="middle" font-size="12" stroke="none" fill="currentColor" ` +
      `font-family="system-ui, sans-serif" ${style}>${text}</text>`,
  );

const lines = (...ys) => ys.map((y) => `<path d="M7 ${y}h10"/>`).join("");

export const ICONS = {
  paragraph: glyph("¶"),
  heading1: glyph("H1", 'font-weight="700"'),
  heading2: glyph("H2", 'font-weight="700"'),
  heading3: glyph("H3", 'font-weight="700"'),
  heading4: glyph("H4", 'font-weight="700"'),
  bullet_list: svg(
    `${lines(5, 10, 15)}<circle cx="3.5" cy="5" r="1" fill="currentColor"/>` +
      `<circle cx="3.5" cy="10" r="1" fill="currentColor"/><circle cx="3.5" cy="15" r="1" fill="currentColor"/>`,
  ),
  ordered_list: svg(
    `${lines(5, 10, 15)}<text x="3.5" y="7" font-size="5" text-anchor="middle" stroke="none" ` +
      `fill="currentColor">1</text><text x="3.5" y="12" font-size="5" text-anchor="middle" ` +
      `stroke="none" fill="currentColor">2</text><text x="3.5" y="17" font-size="5" ` +
      `text-anchor="middle" stroke="none" fill="currentColor">3</text>`,
  ),
  strong: glyph("B", 'font-weight="800"'),
  em: glyph("I", 'font-style="italic" font-family="Georgia, serif"'),
  underline: svg(
    `<text x="10" y="13" text-anchor="middle" font-size="12" stroke="none" fill="currentColor" ` +
      `font-family="system-ui, sans-serif">U</text><path d="M5 16.5h10"/>`,
  ),
  quote: svg(`<path d="M4 4v12"/>${lines(6, 10, 14)}`),
  note: svg(`<circle cx="10" cy="10" r="7"/><path d="M10 9v5"/><path d="M10 6.2v.1"/>`),
  warning: svg(`<path d="M10 3l7.5 13h-15z"/><path d="M10 8v4"/><path d="M10 14.2v.1"/>`),
  example: svg(`<rect x="3.5" y="3.5" width="13" height="13" rx="2"/><path d="M7 10.5l2 2 4-5"/>`),
  table: svg(
    `<rect x="3" y="4" width="14" height="12" rx="1"/><path d="M3 8h14M3 12h14M10 4v12"/>`,
  ),
  add_row: svg(
    `<rect x="3" y="3" width="14" height="8" rx="1"/><path d="M3 7h14"/><path d="M10 13v5M7.5 15.5h5"/>`,
  ),
  undo: svg(`<path d="M7 5L3.5 8.5 7 12"/><path d="M3.5 8.5H12a4.5 4.5 0 010 9H9"/>`),
  redo: svg(`<path d="M13 5l3.5 3.5L13 12"/><path d="M16.5 8.5H8a4.5 4.5 0 000 9h3"/>`),
  clear_formatting: svg(`<path d="M5 4h10M10 4l-3 12"/><path d="M12 12l5 5M17 12l-5 5"/>`),
  link: svg(
    `<path d="M8.5 11.5a3.5 3.5 0 005 0l2.5-2.5a3.5 3.5 0 00-5-5l-1 1"/>` +
      `<path d="M11.5 8.5a3.5 3.5 0 00-5 0L4 11a3.5 3.5 0 005 5l1-1"/>`,
  ),
  image: svg(
    `<rect x="3" y="4" width="14" height="12" rx="1"/><circle cx="7.5" cy="8" r="1.3"/>` +
      `<path d="M3.5 15l4.5-4.5 3 3 2-2 3.5 3.5"/>`,
  ),
  // A span of text marked as an entity.
  mark: svg(`<rect x="3.5" y="5.5" width="13" height="9" rx="1.5"/><path d="M3.5 14.5L10 5.5"/>`),
  // A document named by its number.
  mention: svg(`<path d="M8 3.5L6.5 16.5M13.5 3.5L12 16.5M4 7.5h12.5M3.5 12.5H16"/>`),
};
