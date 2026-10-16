<script lang="ts">
  // Pops page: social classes, what each one buys, and what makes room for them / makes them promote.
  import { DATA, type PopSource } from './lib/data';
  import { icon, fmt, gChip, bChip, pIcon, esc, KIND, signed, pctTxt, ROMAN } from './lib/production';

  let { id }: { id: string | null } = $props();
  const {goods: G, buildings: B, pops: P, cats: CATS, popInfo: PI} = DATA;
  const T = PI.types, POPS = Object.keys(T);

  // base per-pop demand: (own + all + upper) x own multiplier x upper multiplier
  function demand(g: string, p: string) {
    const {demand: a, demandMul: m} = G[g], up = T[p].upper;
    return ((a[p] || 0) + (a.all || 0) + (up ? a.upper || 0 : 0)) * (m[p] ?? 1) * (up ? m.upper ?? 1 : 1);
  }
  const wanted = Object.keys(G).filter(g => POPS.some(p => demand(g, p) > 0));
  const colMax = Object.fromEntries(POPS.map(p => [p, Math.max(...wanted.map(g => demand(g, p)))]));
  let sortBy = $state<string | null>(null);
  const rows = $derived(sortBy ? [...wanted].sort((a, b) => demand(b, sortBy!) - demand(a, sortBy!)) : [...wanted].sort((a, b) => G[a].name.localeCompare(G[b].name)));

  const isPct = (k: string) => k.endsWith('_modifier');
  const modVal = (k: string, v: number) => isPct(k) ? pctTxt(v) : signed(v);
  const modName = (k: string) => PI.modNames[k] || k;
  const desiredKey = (p: string) => new RegExp(`^(local|global)_${p}_((city|rural)_)?desired_pop(_scaled)?$`);
  const SPEED = /pop_(promotion|demotion)_speed|tribal_promotion/;
  const srcName = (s: PopSource) => s.kind === 'building_types' ? bChip(s.id)
    : `<span class="tag">${esc(s.tag || KIND[s.kind] || s.kind.replace(/_/g, ' ').replace(/s$/, ''))}</span> ${esc(s.name || s.id)}${s.age ? ` <i>(age ${ROMAN[s.age]})</i>` : ''}`;
  // sources whose modifiers match, buildings first, as [label, [key, value][]]
  const sourcesFor = (re: RegExp) => PI.sources.map(s => [s, Object.entries(s.mods).filter(([k]) => re.test(k))] as const).filter(([, m]) => m.length)
    .sort(([a], [b]) => +(b.kind === 'building_types') - +(a.kind === 'building_types') || a.kind.localeCompare(b.kind));
  const promotedFrom = (p: string) => POPS.filter(q => T[q].promoteTo.includes(p));
  const pLink = (p: string) => `<a class="chip" href="#p/${p}">${pIcon(p)}${esc(P[p])}</a>`;
  let mainEl = $state<HTMLElement>();
  $effect(() => { void id; mainEl?.scrollTo(0, 0); });
  const toggle = (e: MouseEvent) => (e.target as Element).closest('section.card > h4')?.parentElement!.classList.toggle('shut');

  // buildings that employ this pop, by category
  const employs = (p: string) => Object.entries(Object.entries(B).filter(([, b]) => b.pop === p)
    .reduce((m, [bid, b]) => ((m[CATS[b.cat] || b.cat || 'Other'] ??= []).push(bid), m), {} as Record<string, string[]>)).sort(([a], [b]) => a.localeCompare(b));
</script>

{#snippet sources(list: ReturnType<typeof sourcesFor>)}
  {#each list as [s, ms]}
    <div class="dm src"><span class="v">{#each ms as [k, v]}<span class={v > 0 === !k.includes('demotion') ? 'up' : 'down'} title={modName(k)}>{modVal(k, v)}</span>{/each}</span><span>{@html srcName(s)}{#if ms.length > 1 || !/desired_pop$|promotion_speed$|tribal_promotion$/.test(ms[0][0])}{' '}<i>{ms.map(([k]) => modName(k)).join(', ')}</i>{/if}</span></div>
  {/each}
{/snippet}

<div class="layout">
  <aside>
    <h3>Pops</h3>
    <div class="blist">
      <a href="#pops" class:on={!id}><img class="ic" src="icons/misc/all_pops.png" alt="">Overview</a>
      {#each POPS as p}<a href="#p/{p}" class:on={id === p}>{@html icon('pops', p, P[p])}{P[p]}{#if T[p].upper}<span class="tag up-tag">upper</span>{/if}</a>{/each}
    </div>
  </aside>
  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
  <main bind:this={mainEl} onclick={toggle}>
    {#if id && T[id]}
      {@const t = T[id]}
      <div class="title lg">{@html icon('pops', id, P[id])}<div><h2>{P[id]}</h2>
        <div class="meta"><span>{t.upper ? 'Upper class' : 'Lower class'}</span>{#if t.estate}<span>{t.estate} estate</span>{/if}</div>
        <p class="desc">{t.desc}</p></div>
        <div class="popbar"><span class="flbl">Per pop</span><div class="row">
          <span class="pd" title="Estate tax base per pop"><span class="big">{fmt(t.tax)}</span><b>tax</b></span>
          <span class="pd" title="Estate power per pop"><span class="big">{fmt(t.power)}</span><b>power</b></span>
          <span class="pd food" title="Food eaten per pop"><span class="big">{fmt(t.food)}</span><b>food</b></span>
        </div></div>
      </div>
      <div class="pcards">
        <section class="card"><h4 class="pop">What they buy (per pop)</h4>
          {#each wanted.filter(g => demand(g, id!) > 0).sort((a, b) => demand(b, id!) - demand(a, id!)) as g}
            <div class="bar-row">{@html gChip(g)}<span class="bar"><span style="width:{100 * demand(g, id) / colMax[id]}%"></span></span><span class="n">{fmt(demand(g, id))}</span>{#if G[g].cond}<span class="tag" title="Demand changes with where they live: see the good's page">varies</span>{/if}</div>
          {:else}<p class="meta">No base demand.</p>{/each}
          {#if Object.keys(G).some(g => G[g].demandMul[id!] === 0)}
            <div class="dsec"><span class="flbl">Never buys</span> {@html Object.keys(G).filter(g => G[g].demandMul[id!] === 0).map(g => gChip(g)).join('')}</div>
          {/if}
        </section>
        <section class="card"><h4 class="gold">Promotion</h4>
          <div class="dm"><span class="v">From</span><span>{@html promotedFrom(id).map(pLink).join('') || '<i>nobody promotes into them</i>'}</span></div>
          <div class="dm"><span class="v">Into</span><span>{@html t.promoteTo.map(pLink).join('') || '<i>they don\'t promote</i>'}</span></div>
          {#if t.promo != null}<div class="dm"><span class="v">{fmt(t.promo)}×</span><span>promotion factor</span></div>{/if}
          {#if t.assim != null}<div class="dm"><span class="v">{fmt(t.assim)}×</span><span>assimilation &amp; conversion factor</span></div>{/if}
          {#if t.migration != null}<div class="dm"><span class="v">{fmt(t.migration)}×</span><span>migration factor</span></div>{/if}
          {#if id === 'tribesmen'}<div class="dsec"><span class="flbl">Settles them faster</span>{@render sources(sourcesFor(/tribal_promotion/))}</div>{/if}
          {#if !t.cap}<p class="meta">No location cap: there is no "Possible {P[id]}" limit.</p>{/if}
        </section>
        {#if t.cap}
          <section class="card"><h4 class="out">Room for them (Possible {P[id]})</h4>
            <p class="meta">How many {P[id]} a location can hold.</p>
            {#each Object.entries(PI.base).filter(([k]) => desiredKey(id!).test(k)) as [k, v]}
              <div class="dm"><span class="v up">{signed(v)}</span><span><span class="tag">Every location</span> <i>{modName(k)}</i></span></div>
            {/each}
            {#each PI.ranks.filter(r => Object.keys(r.mods).some(k => desiredKey(id!).test(k))) as r}
              {#each Object.entries(r.mods).filter(([k]) => desiredKey(id!).test(k)) as [, v]}
                <div class="dm"><span class="v up">{signed(v)}</span><span><span class="tag">Rank</span> {r.name}{#if r.minPop}{' '}<i>(population {fmt(r.minPop)}+)</i>{/if}</span></div>
              {/each}
            {/each}
            {@render sources(sourcesFor(desiredKey(id)))}
          </section>
        {/if}
        {#if t.literacy.length || t.share.length}
          <section class="card"><h4 class="gold">Their literacy gives the location</h4>
            {#each t.literacy as [n, v]}<div class="dm"><span class="v">{v != null ? signed(v) : ''}</span><span>{n}</span></div>{/each}
            {#if t.share.length}<div class="dsec"><span class="flbl">Scaled by their share of the population</span>
              {#each t.share as [n, v]}<div class="dm"><span class="v">{v != null ? signed(v) : ''}</span><span>{n}</span></div>{/each}</div>{/if}
          </section>
        {/if}
        {#if employs(id).length}
          <section class="card"><h4 class="in">Work in</h4>
            {#each employs(id) as [c, bs]}<details open={bs.length < 10}><summary>{c} ({bs.length})</summary>{@html bs.sort((a, b) => B[a].name.localeCompare(B[b].name)).map(bChip).join('')}</details>{/each}
          </section>
        {/if}
      </div>
    {:else}
      <div class="title"><div><h2>Pops &amp; social classes</h2>
        <p class="desc">Every pop buys goods from its market. The upper classes (nobles, clerics, burghers) want far more per head and far more kinds of goods, so growing them grows demand.
        Towns, cities and some buildings make room for them, and pops promote into that room. Use the table below to see which class buys what, and grow the class that buys what you can make.</p></div></div>
      <section class="card"><h4 class="gold">Social classes</h4>
        <table class="ptab"><thead><tr><th></th><th>Estate</th><th>Class</th><th title="Estate tax base per pop">Tax</th><th title="Estate power per pop">Power</th><th title="Food eaten per pop">Food</th><th>Goods wanted</th><th>Promote into</th></tr></thead>
          <tbody>{#each POPS as p}<tr><td>{@html pLink(p)}</td><td>{T[p].estate}</td><td>{T[p].upper ? 'Upper' : 'Lower'}</td><td class="n">{fmt(T[p].tax)}</td><td class="n">{fmt(T[p].power)}</td><td class="n">{fmt(T[p].food)}</td>
            <td class="n">{wanted.filter(g => demand(g, p) > 0).length}</td><td>{@html T[p].promoteTo.map(q => pIcon(q)).join('')}</td></tr>{/each}</tbody></table>
      </section>
      <div class="pgrid">
      <section class="card"><h4 class="pop">Demand by class (per pop, before modifiers)</h4>
        <p class="meta">Click a class to sort by it. Brighter cells mean more of what that class buys. Demand also grows with the location's development.</p>
        <div class="mtx-wrap"><table class="ptab mtx"><thead><tr><th><button onclick={() => sortBy = null} class:on={!sortBy}>Good</button></th>
          {#each POPS as p}<th><button onclick={() => sortBy = p} class:on={sortBy === p} title="Sort by {P[p]}">{@html pIcon(p)}</button></th>{/each}</tr></thead>
          <tbody>{#each rows as g}<tr><td>{@html gChip(g)}</td>{#each POPS as p}{@const d = demand(g, p)}
            <td class="n" style={d ? `background: rgba(143, 209, 111, ${(0.08 + 0.5 * d / colMax[p]).toFixed(2)})` : ''}>{d ? fmt(d) : ''}</td>{/each}</tr>{/each}</tbody></table></div>
      </section>
      <div class="pside">
        <section class="card"><h4 class="out">Location rank: room for each class</h4>
          <table class="ptab"><thead><tr><th>Rank</th><th>Pop.</th>{#each ['burghers', 'laborers', 'soldiers', 'nobles', 'clergy'] as p}<th>{@html pIcon(p)}</th>{/each}<th title="Promotion speed">Promo</th></tr></thead>
            <tbody>{#each PI.ranks as r}<tr><td>{r.name}</td><td class="n">{r.minPop ? fmt(r.minPop) + '+' : ''}</td>
              {#each ['burghers', 'laborers', 'soldiers', 'nobles', 'clergy'] as p}<td class="n">{fmt(r.mods[`local_${p}_desired_pop`]) || '–'}</td>{/each}
              <td class="n">{r.mods.local_pop_promotion_speed_modifier ? pctTxt(r.mods.local_pop_promotion_speed_modifier) : '–'}</td></tr>{/each}</tbody></table>
          <p class="meta">"Possible" pops added by the rank. Every location also has room for {fmt(PI.base.local_clergy_desired_pop_scaled)} clerics and {fmt(PI.base.local_nobles_desired_pop_scaled)} nobles per 1,000 population.</p>
        </section>
        <section class="card"><h4 class="gold">How pops promote</h4>
          {#each POPS.filter(p => T[p].promoteTo.length) as p}
            <div class="dm"><span class="v">{@html pIcon(p)}</span><span>{P[p]} → {@html T[p].promoteTo.map(pLink).join('')}</span></div>
          {/each}
          <p class="meta">Base speed in every location: promotion {signed(PI.base.local_pop_promotion_speed)}, demotion {signed(PI.base.local_pop_demotion_speed)}. Pops fill the room ("Possible X") that ranks and buildings create.</p>
        </section>
        <section class="card"><h4 class="pop">Promotion speed</h4>
          {@render sources(sourcesFor(SPEED))}
        </section>
      </div>
      </div>
    {/if}
  </main>
</div>
