<script lang="ts">
  // Nations page: pick a country at the 1337 start and read what its land suggests you build your economy on.
  import { DATA } from './lib/data';
  import { gChip, pIcon, pName, fmt, esc, popDemand } from './lib/production';
  import { loadNations, analyse, subjectsOf, UPPER, type NationData } from './lib/nations';

  let { tag }: { tag: string | null } = $props();
  const G = DATA.goods;
  let N = $state<NationData>();
  loadNations().then(d => N = d);

  let filter = $state('');
  let withSubjects = $state(true);
  const RADII = [[150, 'Close', '~250 km'], [300, 'Nearby', '~500 km'], [500, 'Wider', '~800 km']] as const;
  let radius = $state(300);

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
  const nLink = (t: string) => `<a class="chip nat" href="#n/${t}"><span class="sw" style="background:${swatch(t)}"></span>${esc(N!.countries[t].name)}</a>`;
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
  const locName = (i: number | null) => i == null ? '' : N!.locs[i][0];
</script>

<div class="layout">
  <aside>
    <h3>Nations in 1337</h3>
    <input class="nfilter" placeholder="Find a nation…" bind:value={filter} autocomplete="off">
    {#if N}
      <div class="blist">
        {#each list as t (t)}<a href="#n/{t}" class:on={tag === t}><span class="sw" style="background:{swatch(t)}"></span>{N.countries[t].name}<span class="tag up-tag">{size(t)}</span></a>{/each}
      </div>
    {:else}<p class="meta">Loading nations…</p>{/if}
  </aside>
  <main>{#key tag}<div class="enter">
    {#if !N}
      <p class="meta">Loading nations…</p>
    {:else if A && tag}
      {@const c = A.c}
      <div class="title nation">
        <span class="shield" style="--c:{swatch(tag)}"></span>
        <div><h2>{c.name}</h2>
          <div class="meta"><span>{c.rank}</span>{#if c.culture}<span>{c.culture}</span>{/if}{#if c.religion}<span>{c.religion}</span>{/if}<span>capital {locName(c.cap)}</span><span>{c.locs.length} locations</span></div>
          {#if c.over}<p class="desc">{c.over[1]} of {@html nLink(c.over[0])}</p>{/if}
          {#if subs.length}<p class="desc">Subjects: {@html subs.map(nLink).join('')}
            <label class="tgl"><input type="checkbox" bind:checked={withSubjects}> count their land</label></p>{/if}
        </div>
        <div class="popbar"><span class="flbl">Starting pops</span><div class="row">
          {#each Object.entries(c.pops).sort((a, b) => b[1] - a[1]) as [p, n]}
            <span class="pd" class:top={UPPER.includes(p)} title="{pName(p)}: {fmt(n * 1000)} people, {(100 * n / popTotal(tag)).toPrecision(2)}% of your population">{@html pIcon(p)}<b>{n >= 1 ? Math.round(n) + 'k' : fmt(n * 1000)}</b></span>
          {/each}
        </div></div>
      </div>

      <div class="pcards two">
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

        <section class="card"><h4 class="out">Your raw goods<small>locations producing each</small></h4>
          <div class="rgos">{#each rgoList as [g, n]}<span class="rg" class:spec={lq(g)! >= 1.5} title={lq(g) ? `${times(lq(g)!)} the world's share` : undefined}>{@html gChip(g)}<b>{n}</b></span>{/each}</div>
          <p class="meta">Highlighted goods are specialties: at least 1.5× the world's share.</p>
        </section>

        <section class="card"><h4 class="in">Near {locName(c.cap)}<small>raw goods you don't own yet</small></h4>
          <div class="radii">{#each RADII as [r, l, km]}<button class:on={radius === r} onclick={() => radius = r} title={km}>{l} <i>{km}</i></button>{/each}</div>
          {#each nearList as e (e.g)}
            <div class="dm nr"><span class="v">{e.n}×</span><span>{@html gChip(e.g)}{#if e.isNew}<span class="tag new">new to you</span>{/if}
              <i class="mk">nearest: {e.best[0]} · {e.best[4] ? N.countries[e.best[4]]?.name : 'unowned'}</i></span></div>
          {:else}<p class="meta">Nothing in range.</p>{/each}
        </section>

        {#if Object.keys(A.reach).length}
          <section class="card"><h4 class="out">What you can make<small>from your own raw goods</small></h4>
            <div class="rgos">{@html Object.keys(A.amt).filter(g => G[g]?.cat === 'produced').sort((a, b) => G[b].price - G[a].price).map(g => gChip(g)).join('') || '<i class="none">Nothing without imports.</i>'}</div>
          </section>
        {/if}
      </div>
    {:else}
      <div class="title"><div><h2>Pick your nation</h2>
        <p class="desc">Choose the country you're playing to see what its starting land produces, which social class it's best placed to supply,
          and which valuable raw goods sit near your capital. It reads the 1337 start; the choice is remembered.</p></div></div>
      <div class="natgrid">{@html list.slice(0, 40).map(nLink).join('')}</div>
    {/if}
  </div>{/key}</main>
</div>
