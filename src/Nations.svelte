<script lang="ts">
  // Nations page: pick a country at the 1337 start and read what its land suggests you build your economy on.
  import { DATA } from './lib/data';
  import { gChip, pIcon, pName, fmt, esc, popDemand, icon } from './lib/production';
  import NationMap from './NationMap.svelte';
  import { loadNations, loadUnique, loadStart, analyse, subjectsOf, UPPER, type NationData, type Unique, type StartData } from './lib/nations';
  import { preloadCards } from './lib/cards';
  preloadCards();

  let { tag }: { tag: string | null } = $props();
  const G = DATA.goods;
  let N = $state<NationData>();
  loadNations().then(d => N = d);
  let S = $state<StartData | null>(null);
  loadStart().then(d => S = d);
  const st = $derived(tag ? S?.countries[tag] : undefined);
  const sn = (id: string) => S?.names[id] ?? id;
  // starting privileges by estate, in the game's estate order
  const ESTATES = ['crown_estate', 'nobles_estate', 'clergy_estate', 'burghers_estate', 'peasants_estate'];
  const ESTATE_POP: Record<string, string> = {nobles_estate: 'nobles', clergy_estate: 'clergy', burghers_estate: 'burghers', peasants_estate: 'peasants'};
  const privByEstate = $derived.by(() => {
    const by: Record<string, string[]> = {};
    for (const p of st?.privileges ?? []) (by[S!.estateOf[p] ?? 'other'] ??= []).push(p);
    return Object.entries(by).sort((a, b) => (ESTATES.indexOf(a[0]) + 1 || 99) - (ESTATES.indexOf(b[0]) + 1 || 99));
  });
  let U = $state<Record<string, Unique[]>>({});
  loadUnique().then(d => U = d);
  // what only this nation (or a handful) gets, grouped; advances last and folded
  const KINDS: [string, string][] = [['reform', 'Government reforms'], ['privilege', 'Estate privileges'], ['law', 'Laws'], ['policy', 'Law policies'], ['unit', 'Units'], ['', 'Other'], ['advance', 'Advances']];
  const uniq = $derived.by(() => {
    const list = tag ? U[tag] ?? [] : [], known = new Set(KINDS.map(k => k[0]));
    return KINDS.map(([k, label]) => ({k, label, items: list.filter(u => k ? u.kind === k : !known.has(u.kind))})).filter(g => g.items.length);
  });
  const shareName = (t: string) => N?.countries[t]?.name ?? t;

  let filter = $state('');
  let withSubjects = $state(true);
  const RADII = [[150, 'Close', '~250 km'], [300, 'Nearby', '~500 km'], [500, 'Wider', '~800 km']] as const;
  let radius = $state(150);
  let sel = $state<string | null>(null);  // raw good highlighted on the map
  $effect(() => { tag; sel = null; });

  // remember the nation so the tab opens on it next time
  $effect(() => { if (tag && N?.countries[tag]) localStorage.setItem('nation', tag); });
  $effect(() => { if (!tag && N && localStorage.getItem('nation') && N.countries[localStorage.getItem('nation')!]) location.replace('#n/' + localStorage.getItem('nation')); });

  const size = (t: string) => N!.countries[t].locs.length;
  const list = $derived(N ? Object.keys(N.countries).filter(t => !filter || N!.countries[t].name.toLowerCase().includes(filter.toLowerCase()) || t.toLowerCase() === filter.toLowerCase())
    .sort((a, b) => size(b) - size(a) || N!.countries[a].name.localeCompare(N!.countries[b].name)) : []);
  const A = $derived(N && tag && N.countries[tag] ? analyse(N, tag, withSubjects) : null);  // re-runs when the age changes (popDemand reads it)
  const subs = $derived(N && tag && N.countries[tag] ? subjectsOf(N, tag) : []);
  const nearList = $derived(A ? A.near(radius) : []);

  const swatch = (t: string) => { const c = N?.countries[t]?.color; return c ? `rgb(${c.join(',')})` : '#4a5260'; };
  // flags come from public/flags (flags.py); the nation's map colour shows when one is missing
  const flag = (t: string) => `<span class="fl" style="background:${swatch(t)}"><img src="flags/${t}.png" alt="" loading="lazy" onerror="this.remove()"></span>`;
  const nLink = (t: string) => `<a class="chip nat" href="#n/${t}">${flag(t)}${esc(N!.countries[t].name)}</a>`;
  const pct = (x: number) => Math.round(x * 100) + '%';
  const rgoList = $derived(A ? Object.entries(A.rgo).sort((a, b) => b[1] - a[1] || G[b[0]].price - G[a[0]].price) : []);
  const ranked = $derived(A ? [...A.classes].sort((a, b) => b.lean - a.lean) : []);
  const lq = (g: string) => A?.spec.find(x => x.g === g)?.lq;
  const times = (x: number) => '×' + (x >= 10 ? Math.round(x) : x.toFixed(1));
  const specChip = (g: string) => `<span class="nw">${gChip(g)}${lq(g)! >= 1.5 ? `<span class="cnt" title="Share of what you make, against the world's">${times(lq(g)!)}</span>` : ''}</span>`;
  // the goods each raw good feeds straight into, that you can fully make
  const feeds = (g: string) => A ? Object.keys(G).filter(x => x in A.amt && G[x].cat === 'produced'
    && Object.values(DATA.buildings).some(b => b.recipes.some(r => r.out === x && g in r.in))) : [];
  // nearby goods you lack, ordered by how much your leading class spends on them
  // (bought directly, or the missing input of something they'd buy)
  const wantNear = $derived(A && ranked[0] ? nearList.filter(e => e.isNew).map(e => ({...e, v: Math.max(0, popDemand(e.g, ranked[0].p) * G[e.g].price,
    ...ranked[0].almost.filter(x => A!.reach[x.g].missing.includes(e.g)).map(x => x.v))})).filter(e => e.v > 0).sort((a, b) => b.v - a.v).slice(0, 4) : []);
  const popTotal = (t: string) => Object.values(N!.countries[t].pops).reduce((s, n) => s + n, 0);
  const kPeople = (k: number) => k >= 1000 ? (k / 1000).toFixed(k >= 10000 ? 0 : 2) + 'M' : Math.round(k) + 'k';  // thousands -> 211k / 1.25M
  const locName = (i: number | null) => i == null ? '' : N!.locs[i][0];
</script>

<div class="layout">
  <aside>
    <h3>Nations in 1337</h3>
    <input class="nfilter" placeholder="Find a nation…" bind:value={filter} autocomplete="off">
    {#if N}
      <div class="blist">
        {#each list as t (t)}<a href="#n/{t}" class:on={tag === t}>{@html flag(t)}{N.countries[t].name}<span class="tag up-tag">{size(t)}</span></a>{/each}
      </div>
    {:else}<p class="meta">Loading nations…</p>{/if}
  </aside>
  <main>{#key tag}<div class="enter">
    {#if !N}
      <p class="meta">Loading nations…</p>
    {:else if A && tag}
      {@const c = A.c}
      <div class="title nation">
        {#key tag}<span class="bigflag" style="background:{swatch(tag)}"><img src="flags/{tag}.png" alt="" onerror={e => (e.currentTarget as HTMLElement).remove()}></span>{/key}
        <div><h2>{c.name}</h2>
          <div class="meta"><span>{c.rank}</span>{#if c.culture}<span>{c.culture}</span>{/if}{#if c.religion}<span>{c.religion}</span>{/if}<span>capital {locName(c.cap)}</span><span>{c.locs.length} locations</span></div>
          {#if c.over}<p class="desc">{c.over[1]} of {@html nLink(c.over[0])}</p>{/if}
          {#if subs.length}<p class="desc">Subjects: {@html subs.map(nLink).join('')}
            <label class="tgl"><input type="checkbox" bind:checked={withSubjects}> count their land</label></p>{/if}
        </div>
        <div class="popbar"><span class="flbl">Starting pops</span><div class="row">
          <span class="pd tot" title="All pops: {Math.round(popTotal(tag) * 1000).toLocaleString('en')} people in {c.name}'s own locations (subjects not counted)"><img class="ic" src="icons/misc/all_pops.png" alt="All pops"><b>{kPeople(popTotal(tag))}</b></span>
          {#each Object.entries(c.pops).sort((a, b) => b[1] - a[1]) as [p, n]}
            <span class="pd" class:top={UPPER.includes(p)} title="{pName(p)}: {fmt(n * 1000)} people, {(100 * n / popTotal(tag)).toPrecision(2)}% of your population">{@html pIcon(p)}<b>{n >= 1 ? Math.round(n) + 'k' : fmt(n * 1000)}</b></span>
          {/each}
        </div></div>
      </div>

      <div class="ncols">
        <div>
          <section class="card"><h4 class="gold">Reading your start<small>from the land you own in 1337</small></h4>
            <div class="reading">
              {#if ranked[0]?.lean >= 0.15}
                {@const k = ranked[0]}
                <p><b>Grow {pName(k.p)}.</b> Your land has more than its share of goods they stand out as buyers of:
                  {@html k.supplied.slice(0, 3).map(x => specChip(x.g)).join(' ')}. Every one you grow is a customer for something you already make.</p>
                {#if ranked[1]?.lean >= 0.15}
                  <p><b>{pName(ranked[1].p)} too</b>, for {@html ranked[1].supplied.slice(0, 3).map(x => specChip(x.g)).join(' ')}.</p>
                {/if}
              {:else}
                <p><b>No class stands out.</b> Your land is close to the world's mix{#if A.spec.length}; its specialties, {@html A.spec.slice(0, 3).map(x => specChip(x.g)).join(' ')}, are goods most classes buy alike{/if}.</p>
              {/if}
              {#if rgoList.length}
                <p><b>Build on your biggest stocks.</b>
                  {#each rgoList.slice(0, 3) as [g, n], i}{i ? (i === 2 ? ' and ' : ', ') : ''}<span class="nw">{@html gChip(g)}<span class="cnt">×{n}</span></span>{#if feeds(g).length} into {@html feeds(g).slice(0, 3).map(x => gChip(x)).join(' ')}{/if}{/each}.
                  What your own classes don't buy, sell to your neighbours' markets.</p>
              {/if}
              {#if wantNear.length}
                <p><b>Look next door for</b> {@html wantNear.map(e => gChip(e.g)).join(' ')}: you have none, {pName(ranked[0].p)} buy them or what they make, and they're within {RADII.find(r => r[0] === radius)?.[2]} of {locName(c.cap)}.</p>
              {/if}
            </div>
          </section>

          {#if st}
            <section class="card"><h4 class="gold">Starting position<small>{st.gov ? sn(st.gov) : ''}</small></h4>
              {#if st.reforms.length}<div class="flbl">Government reforms</div>
                <div class="minicards sp-reforms">{#each st.reforms as r}<span class="minicard" data-reform={r}><span class="art sm"><img src="icons/reforms/{r}.webp" alt="" loading="lazy"></span>{sn(r)}</span>{/each}</div>{/if}
              <div class="flbl">Estate privileges</div>
              {#each privByEstate as [e, ps] (e)}
                <div class="sp"><span class="who">{#if ESTATE_POP[e]}{@html pIcon(ESTATE_POP[e])}{/if}{sn(e)}</span>
                  <div class="minicards">{#each ps as p}<a class="minicard" href="#e/{p}"><span class="art sm"><img src="icons/privileges/{p}.webp" alt="" loading="lazy"></span>{sn(p)}</a>{/each}</div></div>
              {:else}<p class="meta">None.</p>{/each}
              <details class="ugroup"><summary>Laws<span class="cnt">{Object.keys(st.laws).length}</span></summary>
                <div class="laws">{#each Object.entries(st.laws) as [l, pol]}<span>{sn(l)}</span><b>{sn(pol)}</b>{/each}</div>
              </details>
              <details class="ugroup"><summary>Societal values<span class="cnt">{st.values.filter(v => v != null).length}</span></summary>
                {#each S!.axes as a, i}{#if st.values[i] != null}
                  <div class="sv"><span>{S!.axisNames[i][0]}</span><span class="svbar"><i style="left:{(st.values[i]! + 100) / 2}%"></i></span><span>{S!.axisNames[i][1]}</span></div>
                {/if}{/each}
              </details>
              <p class="meta">From a save of the 1337 start: privileges, laws and reforms as granted at setup; societal values as of {S!.date}.
                Crown power and estate power aren't stored in saves (the game works them out as it runs), so they aren't shown.</p>
            </section>
          {/if}

          <section class="card"><h4 class="pop">Who your land is built for<small>your surplus of each class's goods</small></h4>
            {#each ranked as k (k.p)}
              <div class="fit">
                <span class="who">{@html pIcon(k.p)}{pName(k.p)}</span>
                <span class="bar"><span style="width:{Math.min(100, 100 * k.lean)}%"></span></span>
                <span class="n">{k.lean >= 0.5 ? 'strong' : k.lean >= 0.15 ? 'some' : 'little'}</span>
              </div>
              {#if k.supplied.length || k.almost.length}
                <div class="fitd">
                  {@html k.supplied.slice(0, 5).map(x => specChip(x.g)).join('')}
                  {#if k.almost.length}<span class="miss">almost: {@html k.almost.slice(0, 3).map(x => gChip(x.g) + `<i> needs ${A!.reach[x.g].missing.map(m => esc(G[m]?.name || m)).join(', ')}</i>`).join(' ')}</span>{/if}
                </div>
              {/if}
            {/each}
            <p class="meta">Goods count for a class when its pops buy clearly more of them than the other upper classes: nobles for most luxuries,
              clergy for cloth, paper, books and incense, burghers only for pottery. The bar is how much more of those goods your land makes than the
              world's mix in 1337 (every location you own plus what you can make from them, at base prices), against how big they are worldwide.
              Demand follows the age you picked.</p>
          </section>

          {#if uniq.length}
            <section class="card"><h4 class="gold">Only {c.name}<small>content locked to this nation, or a few</small></h4>
              {#each uniq as grp (grp.k)}
                <details class="ugroup" open={grp.k !== 'advance'}><summary>{grp.label}<span class="cnt">{grp.items.length}</span></summary>
                  {#each grp.items as u (u.kind + u.id)}
                    <div class="uq" class:withart={u.kind === 'privilege' || u.kind === 'reform'}>
                      {#if u.kind === 'privilege'}<a class="art sm" href="#e/{u.id}"><img src="icons/privileges/{u.id}.webp" alt="" loading="lazy"></a>
                      {:else if u.kind === 'reform'}<span class="art sm" data-reform={u.id}><img src="icons/reforms/{u.id}.webp" alt="" loading="lazy"></span>{/if}
                      <div>
                      <div class="uh"><b title={u.desc}>{u.name}</b>
                        {#if grp.k === ''}<span class="tag">{u.kind}</span>{/if}
                        {#if u.estate}<span class="tag">{u.estate}</span>{/if}{#if u.law}<span class="tag">{u.law}</span>{/if}{#if u.age}<span class="tag">{u.age}</span>{/if}
                        {#if u.gated}<span class="tag gated" title="Needs something else first: an event, a decision or an advance">unlocked later</span>{/if}
                        {#if u.shared?.length}<i class="also">also {u.shared.map(shareName).join(', ')}</i>{/if}</div>
                      {#if u.mods.length}<div class="um">{#each u.mods as [l, v]}<span>{l} <b>{v}</b></span>{/each}</div>{/if}
                      </div>
                    </div>
                  {/each}
                </details>
              {/each}
              <p class="meta">Hover a name for its description. Found by the tag conditions in the game files; content unlocked by culture, religion or region isn't listed.</p>
            </section>
          {/if}

        </div>
        <div>
          <section class="card"><h4 class="in">Around {locName(c.cap)}<small>raw goods you don't own yet</small></h4>
            <div class="radii">{#each RADII as [r, l, km]}<button class:on={radius === r} onclick={() => radius = r} title={km}>{l} <i>{km}</i></button>{/each}</div>
            <NationMap {N} {tag} mine={A.mine} {radius} bind:sel />
            <div class="mgoods">Show on map:
              {#each rgoList as [g]}<button class:on={sel === g} onclick={() => sel = sel === g ? null : g} title={G[g].name}>{@html icon('goods', g, G[g].name)}</button>{/each}
              {#if nearList.some(e => e.isNew)}<span class="sep" title="Nearby goods you don't have"></span>{/if}
              {#each nearList.filter(e => e.isNew) as e}<button class:on={sel === e.g} onclick={() => sel = sel === e.g ? null : e.g} title="{G[e.g].name} (nearby, new to you)">{@html icon('goods', e.g, G[e.g].name)}</button>{/each}
            </div>
            {#each nearList as e (e.g)}
              <div class="dm nr"><span class="v">{e.n}×</span><span>{@html gChip(e.g)}{#if e.isNew}<span class="tag new">new to you</span>{/if}
                <i class="mk">nearest: {e.best[0]} · {e.best[4] ? N.countries[e.best[4]]?.name : 'unowned'}</i></span></div>
            {:else}<p class="meta">Nothing in range.</p>{/each}
          </section>

          <section class="card"><h4 class="out">Your raw goods<small>locations producing each</small></h4>
            <div class="rgos">{#each rgoList as [g, n]}<span class="rg" class:spec={lq(g)! >= 1.5} title={lq(g) ? `${times(lq(g)!)} the world's share` : undefined}>{@html gChip(g)}<b>{n}</b></span>{/each}</div>
            <p class="meta">Highlighted goods are specialties: at least 1.5× the world's share.</p>
          </section>

          {#if Object.keys(A.reach).length}
            <section class="card"><h4 class="out">What you can make<small>from your own raw goods</small></h4>
              <div class="rgos">{@html Object.keys(A.amt).filter(g => G[g]?.cat === 'produced').sort((a, b) => G[b].price - G[a].price).map(g => gChip(g)).join('') || '<i class="none">Nothing without imports.</i>'}</div>
            </section>
          {/if}
        </div>
      </div>
    {:else}
      <div class="title"><div><h2>Pick your nation</h2>
        <p class="desc">Choose the country you're playing to see what its starting land produces, which social class it's best placed to supply,
          and which valuable raw goods sit near your capital. It reads the 1337 start; the choice is remembered.</p></div></div>
      <div class="natgrid">{@html list.slice(0, 40).map(nLink).join('')}</div>
    {/if}
  </div>{/key}</main>
</div>
