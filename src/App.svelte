<script lang="ts">
  import { untrack } from 'svelte';
  import { mountProduction, searchNames, searchGo } from './lib/production';
  import Pops from './Pops.svelte';
  import Nations from './Nations.svelte';
  import { DATA } from './lib/data';
  import { AGE, setAge } from './lib/age.svelte';
  const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI'], AGES = Object.keys(DATA.ages).map(Number);

  let side = $state<HTMLElement>(), main = $state<HTMLElement>(), search: HTMLInputElement;
  let hash = $state(location.hash);
  const isPops = $derived(/^#(pops|p\/)/.test(hash)), isNations = $derived(/^#n(\/|$)/.test(hash));
  // the Production Chains page renders itself into the aside / main panes while it is shown
  $effect(() => { if (!isPops && !isNations && side && main) return untrack(() => mountProduction(side!, main!)); });

  function go() { searchGo(search.value); search.value = ''; }
  function focusSearch(e: KeyboardEvent) {
    if (e.key === '/' && document.activeElement !== search) { e.preventDefault(); search.focus(); }
  }
</script>

<svelte:window onkeydown={focusSearch} onhashchange={() => hash = location.hash} />

<header>
  <h1>Europedia V</h1>
  <nav><a href="#/" class:on={!isPops && !isNations}>Production Chains</a><a href="#pops" class:on={isPops}>Pops</a><a href="#n" class:on={isNations}>Nations</a></nav>
  <input id="search" bind:this={search} onchange={go} placeholder="Search goods, buildings or pops…  (/)" list="names" autocomplete="off">
  <datalist id="names">{#each searchNames as n}<option value={n}></option>{/each}</datalist>
  <div class="agesel" title="The age you are playing in: production shows what's available, pop demand includes that age's modifiers">
    <span class="flbl">Age</span>
    <button class="all" class:on={!AGE.v} onclick={() => setAge(null)}>All</button>
    {#each AGES as a}<button class:on={AGE.v === a} onclick={() => setAge(a)} title="Age {ROMAN[a]}: {DATA.ages[a]}">{ROMAN[a]}</button>{/each}
    {#if AGE.v}<span class="agename">{DATA.ages[AGE.v]}</span>{/if}
  </div>
  <small class="legal">Fan-made, not affiliated with Paradox Interactive. Game data and art © Paradox Interactive.</small>
</header>
{#if isPops}
  <Pops id={hash.startsWith('#p/') ? hash.slice(3) : null} />
{:else if isNations}
  <Nations tag={hash.startsWith('#n/') ? hash.slice(3) : null} />
{:else}
  <div class="layout">
    <aside bind:this={side}></aside>
    <main bind:this={main}></main>
  </div>
{/if}
