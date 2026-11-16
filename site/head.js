// Runs before the first paint (an external file: the site's CSP allows no inline script).
// The hero's entrance and the moments' guard, as the design kit's starter sets them.
document.documentElement.classList.add("m-enter", "mo-js");
setTimeout(() => document.documentElement.classList.add("m-enter-done"), 700);
setTimeout(() => document.documentElement.classList.add("mo-safe"), 2500);
