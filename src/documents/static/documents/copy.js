// Choosing another version in the copy dialog reloads it with that version's appendices; without
// this script the appendices listed are the default version's, and a choice outside them is
// refused when the copy is made.
document.addEventListener("change", (event) => {
  const radio = event.target.closest('#copy-document input[name="version"]');
  if (!radio) return;
  const url = new URL(window.location.href);
  url.searchParams.set("version", radio.value.split(":")[0]);
  window.location.assign(url);
});
