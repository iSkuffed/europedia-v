// The age the user is playing in, shared by every page and remembered between visits. null = all ages.
const saved = Number(localStorage.getItem('age')) || null;
export const AGE = $state<{v: number | null}>({v: saved});
export function setAge(a: number | null) {
  AGE.v = a;
  if (a) localStorage.setItem('age', String(a)); else localStorage.removeItem('age');
  dispatchEvent(new Event('agechange'));  // for the string-rendered Production page
}
