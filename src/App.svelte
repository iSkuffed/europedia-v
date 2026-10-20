<script lang="ts">
  import { untrack } from 'svelte';
  import { mountProduction, searchNames, searchGo } from './lib/production';
  import Pops from './Pops.svelte';
  import Nations from './Nations.svelte';
  import Privileges from './Privileges.svelte';
  import Research from './Research.svelte';
  import Units from './Units.svelte';
  import WorldMap from './WorldMap.svelte';
  import { DATA } from './lib/data';
  import { AGE, setAge } from './lib/age.svelte';
  import { loadNations, type NationData } from './lib/nations';
  import { loadPrivileges } from './lib/cards';
  import { SCOPE, setScope, loadScope } from './lib/scope.svelte';
  import { tick } from 'svelte';
  const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI'], AGES = Object.keys(DATA.ages).map(Number);

  let side = $state<HTMLElement>(), main = $state<HTMLElement>(), search: HTMLInputElement;
  let hash = $state(location.hash);
  const isPops = $derived(/^#(pops|p\/)/.test(hash)), isNations = $derived(/^#n(\/|$)/.test(hash));
  const isPriv = $derived(/^#e(\/|$)/.test(hash)), isResearch = $derived(/^#r(\/|$)/.test(hash));
  const isMap = $derived(/^#m(\/|$)/.test(hash)), isUnits = $derived(/^#u(\/|$)/.test(hash));
  // the Production Chains page renders itself into the aside / main panes while it is shown
  $effect(() => { if (!isPops && !isNations && !isPriv && !isResearch && !isMap && !isUnits && side && main) return untrack(() => mountProduction(side!, main!)); });

  // nations join the search once it's first focused (their file is big)
  let N = $state<NationData>();
  const nationNames = $derived(N ? [...new Set(Object.values(N.countries).map(c => c.name))] : []);
  // privileges and reforms too, as [name, route]; only exact names match, so a good called "Iron" still wins over "Iron Mines" privileges
  let privs = $state<[string, string][]>([]);
  const privNames = $derived([...new Set(privs.map(p => p[0]))]);
  function loadSearch() {
    loadNations().then(d => N = d);
    loadPrivileges().then(d => privs = [...d.privileges.map(p => [p.name, `e/${p.id}`] as [string, string]), ...d.reforms.map(r => [r.name, `e/reform:${r.id}`] as [string, string])]);
  }
  function go() {
    const q = search.value.trim().toLowerCase(), t = N && Object.keys(N.countries).find(t => N!.countries[t].name.toLowerCase() === q);
    const e = !t && privs.find(p => p[0].toLowerCase() === q);
    if (t) location.hash = `n/${t}`; else if (e) location.hash = e[1]; else searchGo(search.value);
    search.value = '';
  }
  // "viewing as" a nation: the flag clears it, the name (or the globe in Global view) opens the nation picker
  let picking = $state(false), pickIn = $state<HTMLInputElement>(), nats = $state<[string, string][]>([]);  // [label, tag]
  const fold = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim();
  function openPick() {
    picking = true;
    tick().then(() => pickIn?.focus());
    loadScope().then(d => {
      const cs = Object.entries(d.countries), seen = new Set<string>(), dup = new Set(cs.map(c => c[1].name).filter(n => seen.has(n) || !seen.add(n)));
      const ns: [string, string][] = cs.map(([t, c]) => [dup.has(c.name) ? `${c.name} (${t})` : c.name, t]);
      ns.push(['Yuán', 'CHI']);  // the setup calls the 1337 Yuan "China"; the game shows it as Yuán
      nats = ns.sort((a, b) => a[0].localeCompare(b[0]));
    });
  }
  function pick() {
    const q = fold(pickIn!.value), hit = q && (nats.find(n => fold(n[0]) === q) || nats.find(n => fold(n[0]).startsWith(q)));
    if (hit) setScope(hit[1]);
    picking = false;
  }
  function focusSearch(e: KeyboardEvent) {
    if (e.key === '/' && document.activeElement !== search) { e.preventDefault(); search.focus(); }
  }
</script>

<svelte:window onkeydown={focusSearch} onhashchange={() => hash = location.hash} />

<header>
  <div class="brand">
    <h1><a href="#/" title="Home">Europedia V</a><span class="beta" title="Work in progress: some data may be missing or wrong, and layouts may break.">Beta</span></h1>
    <small class="legal" title="Fan-made, not affiliated with Paradox Interactive. Game data and art © Paradox Interactive.">Fan-made · not affiliated with Paradox</small>
  </div>
  <nav><a href="#/" class:on={!isPops && !isNations && !isPriv && !isResearch && !isMap && !isUnits}>Production Chains</a><a href="#pops" class:on={isPops}>Pops</a><a href="#n" class:on={isNations}>Nations</a><a href="#m" class:on={isMap}>Map</a><a href="#e" class:on={isPriv}>Privileges</a><a href="#r" class:on={isResearch}>Research</a><a href="#u" class:on={isUnits}>Units</a></nav>
  <input id="search" bind:this={search} onchange={go} onfocus={loadSearch} placeholder="Search goods, nations, reforms…  (/)" title="Goods, buildings, pops, nations, privileges and reforms. Press / to jump here." list="names" autocomplete="off">
  <datalist id="names">{#each searchNames as n}<option value={n}></option>{/each}{#each nationNames as n}<option value={n}></option>{/each}{#each privNames as n}<option value={n}></option>{/each}</datalist>
  <div class="viewas">
    {#if picking}
      <input class="vpick" bind:this={pickIn} list="nats" placeholder="View as nation…" autocomplete="off" onchange={pick}
             onblur={() => setTimeout(() => picking = false, 200)} onkeydown={e => e.key === 'Escape' && (picking = false)}>
      <datalist id="nats">{#each nats as n}<option value={n[0]}></option>{/each}</datalist>
    {:else if SCOPE.tag}
      <button class="vflag" onclick={() => setScope(null)} title="Back to Global view"><span class="fl"><img src="flags/{SCOPE.tag}.png" alt=""></span><span class="x">✕</span></button>
      <button class="vname" onclick={openPick} title="Viewing as {SCOPE.name}: pages show only what applies to it. Click to pick another nation.">{SCOPE.name || SCOPE.tag}</button>
    {:else}
      <button class="vglobe" onclick={openPick} title="Global view: everything, for every nation. Click to view the site as one nation.">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.6 3.9 5.6 3.9 9s-1.3 6.4-3.9 9c-2.6-2.6-3.9-5.6-3.9-9S9.4 5.6 12 3z"/></svg>Global</button>
    {/if}
  </div>
  <div class="agesel" title="The age you are playing in: production shows what's available, pop demand includes that age's modifiers">
    <span class="flbl">Age</span>
    <button class="all" class:on={!AGE.v} onclick={() => setAge(null)}>All</button>
    {#each AGES as a}<button class:on={AGE.v === a} onclick={() => setAge(a)} title="Age {ROMAN[a]}: {DATA.ages[a]}">{ROMAN[a]}</button>{/each}
    {#if AGE.v}<span class="agename">{DATA.ages[AGE.v]}</span>{/if}
  </div>
</header>
{#if isPops}
  <Pops id={hash.startsWith('#p/') ? hash.slice(3) : null} />
{:else if isNations}
  <Nations tag={hash.startsWith('#n/') ? hash.slice(3) : null} />
{:else if isPriv}
  <Privileges id={hash.startsWith('#e/') ? decodeURIComponent(hash.slice(3)) : null} />
{:else if isMap}
  <WorldMap />
{:else if isUnits}
  <Units id={hash.startsWith('#u/') ? decodeURIComponent(hash.slice(3)) : null} />
{:else if isResearch}
  <Research id={hash.startsWith('#r/') ? decodeURIComponent(hash.slice(3)) : null} />
{:else}
  <div class="layout">
    <aside bind:this={side}></aside>
    <main bind:this={main}></main>
  </div>
{/if}
<a class="sig" href="https://github.com/iSkuffed" target="_blank" rel="noopener" title="Skuffed Software"><img src="skuffed.svg" alt="Skuffed Software"></a>
