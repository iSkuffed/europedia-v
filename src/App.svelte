<script lang="ts">
  import { onMount } from 'svelte';
  import { mountProduction, searchNames, searchGo } from './lib/production';

  let side: HTMLElement, main: HTMLElement, search: HTMLInputElement;
  onMount(() => mountProduction(side, main));

  function go() { searchGo(search.value); search.value = ''; }
  function focusSearch(e: KeyboardEvent) {
    if (e.key === '/' && document.activeElement !== search) { e.preventDefault(); search.focus(); }
  }
</script>

<svelte:window onkeydown={focusSearch} />

<header>
  <h1>Europedia V</h1>
  <nav><a href="#/" class="on">Production Chains</a></nav>
  <input id="search" bind:this={search} onchange={go} placeholder="Search goods or buildings…  (/)" list="names" autocomplete="off">
  <datalist id="names">{#each searchNames as n}<option value={n}></option>{/each}</datalist>
  <small class="legal">Fan-made, not affiliated with Paradox Interactive. Game data and art © Paradox Interactive.</small>
</header>
<div class="layout">
  <aside bind:this={side}></aside>
  <main bind:this={main}></main>
</div>
