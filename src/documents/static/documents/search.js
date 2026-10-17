// The type filter beside the search box submits its form when a type is chosen; without this
// script the form is sent with Enter in the search box (DL-0236).
document.addEventListener("change", (event) => {
  const filter = event.target.closest("#type-filter");
  if (filter) filter.form.submit();
});
