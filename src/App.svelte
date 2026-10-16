<script lang="ts">
  import { mountProduction, searchNames, searchGo } from './lib/production';
  import Pops from './Pops.svelte';

  let side = $state<HTMLElement>(), main = $state<HTMLElement>(), search: HTMLInputElement;
  let hash = $state(location.hash);
  const isPops = $derived(/^#(pops|p\/)/.test(hash));
  // the Production Chains page renders itself into the aside / main panes while it is shown
  $effect(() => { if (!isPops && side && main) return mountProduction(side, main); });

  function go() { searchGo(search.value); search.value = ''; }
  function focusSearch(e: KeyboardEvent) {
    if (e.key === '/' && document.activeElement !== search) { e.preventDefault(); search.focus(); }
  }
</script>

<svelte:window onkeydown={focusSearch} onhashchange={() => hash = location.hash} />

<header>
  <h1>Europedia V</h1>
  <nav><a href="#/" class:on={!isPops}>Production Chains</a><a href="#pops" class:on={isPops}>Pops</a></nav>
  <input id="search" bind:this={search} onchange={go} placeholder="Search goods, buildings or pops…  (/)" list="names" autocomplete="off">
  <datalist id="names">{#each searchNames as n}<option value={n}></option>{/each}</datalist>
  <small class="legal">Fan-made, not affiliated with Paradox Interactive. Game data and art © Paradox Interactive.</small>
</header>
{#if isPops}
  <Pops id={hash.startsWith('#p/') ? hash.slice(3) : null} />
{:else}
  <div class="layout">
    <aside bind:this={side}></aside>
    <main bind:this={main}></main>
  </div>
{/if}
