<script lang="ts" module>
  // public/advances.json (advances.py). `who` / `req` are clauses ANDed together: a clause is one kind of thing (country, culture...)
  // with the ids that qualify (any of them), `not` for "none of these", or `parts` for a mix (any = or, all = and).
  export interface Clause { type: string; ids?: string[]; names?: string[]; not?: number; cap?: number; parts?: Clause[] }
  export interface Adv {
    id: string; name: string; desc?: string; age: number; focus?: 'adm' | 'dip' | 'mil'; cost?: number; requires?: string[]; icon?: string;
    unlocks?: [string, string, string][]; mods?: [string, string][]; during?: [string, string][];
    who?: Clause[]; whoText?: string; uniq?: string[]; req?: Clause[]; reqText?: string;
  }
  export interface AdvData { ages: Record<string, string>; focus: Record<string, string>; advances: Adv[] }
  let cache: Promise<AdvData> | undefined;
  export const loadAdvances = () => cache ??= fetch('advances.json').then(r => r.json());
  let textCache: Promise<Record<string, string>> | undefined;  // descriptions, only needed on a detail page
  export const loadAdvanceText = () => textCache ??= fetch('advance_text.json').then(r => r.ok ? r.json() : {});
</script>

<script lang="ts">
  import { DATA } from './lib/data';
  import { AGE } from './lib/age.svelte';
  import { loadNations, type NationData } from './lib/nations';
  import { bChip, icon, ROMAN } from './lib/production';

  let { id }: { id: string | null } = $props();
  let D = $state<AdvData>(), N = $state<NationData>();
  loadAdvances().then(d => D = d);
  let T = $state<Record<string, string>>({});
  $effect(() => { if (id) loadAdvanceText().then(t => T = t); });
  loadNations().then(d => N = d);

  // ---- vocabulary --------------------------------------------------------------------------------------------
  const CATS = [['country', 'Country'], ['culture', 'Culture'], ['religion', 'Religion'], ['region', 'Region'], ['other', 'Other']] as const;
  const CAT: Record<string, string> = {tag: 'country', culture: 'culture', culture_group: 'culture', language: 'culture', religion: 'religion',
    religion_group: 'religion', region: 'region', area: 'region', sub_continent: 'region', continent: 'region', capital: 'region'};
  const TL: Record<string, string> = {tag: 'Country', culture: 'Culture', culture_group: 'Culture group', language: 'Language', religion: 'Religion',
    religion_group: 'Religion group', region: 'Region', area: 'Area', sub_continent: 'Sub-continent', continent: 'Continent', capital: 'Capital',
    government: 'Government', reform: 'Reform', subject_type: 'Subject type', status: 'Status', estate: 'Estate', societal: 'Societal value',
    dlc: 'DLC', rank: 'Rank', institution: 'Institution', advance: 'Advance', country_type: 'Country type', other: ''};
  const FOCUS_ORDER = ['adm', 'dip', 'mil'] as const;
  const KIND: Record<string, string> = {unit: 'Units', building: 'Buildings', law: 'Laws', levy: 'Levies', town_rights: 'Town rights', government_reform: 'Government reforms',
    cabinet_action: 'Cabinet actions', production_method: 'Production methods', estate_privilege: 'Estate privileges', policy: 'Law policies', subject_type: 'Subject types',
    chivalric_order: 'Chivalric orders', heir_selection: 'Heir selections', casus_belli: 'Casus belli', road_type: 'Road types', ability: 'Abilities',
    interaction: 'Interactions', country_interaction: 'Country interactions'};
  const KIND_ORDER = Object.keys(KIND);
  const pmBuilding = new Map<string, string>();  // production method id -> building that has it
  for (const [b, v] of Object.entries(DATA.buildings)) for (const r of v.recipes) pmBuilding.set(r.id, b);

  // ---- indexes, built once the data is in ---------------------------------------------------------------------
  const X = $derived.by(() => {
    if (!D) return null;
    const byId = new Map(D.advances.map(a => [a.id, a]));
    const leads = new Map<string, Adv[]>(), sameWho = new Map<string, Adv[]>();
    for (const a of D.advances) {
      for (const r of a.requires ?? []) leads.set(r, [...(leads.get(r) ?? []), a]);
      if (a.whoText) sameWho.set(a.whoText, [...(sameWho.get(a.whoText) ?? []), a]);
    }
    const depth = new Map<string, number>();  // length of the longest prerequisite chain: orders a list like the tree
    const dep = (a: Adv, seen: string[]): number => {
      if (depth.has(a.id)) return depth.get(a.id)!;
      if (seen.includes(a.id)) return 0;
      const d = Math.max(-1, ...(a.requires ?? []).map(r => byId.has(r) ? dep(byId.get(r)!, [...seen, a.id]) : -1)) + 1;
      depth.set(a.id, d);
      return d;
    };
    D.advances.forEach(a => dep(a, []));
    const hay = new Map(D.advances.map(a => [a.id, [a.name, a.id, a.whoText, a.reqText, ...(a.mods ?? []).map(m => m[0]), ...(a.unlocks ?? []).map(u => u[2])].join(' ').toLowerCase()]));
    return {byId, leads, sameWho, depth, hay};
  });
  const cmp = (a: Adv, b: Adv) => (X?.depth.get(a.id) ?? 0) - (X?.depth.get(b.id) ?? 0) || a.name.localeCompare(b.name);

  // ---- filters (sidebar) -------------------------------------------------------------------------------------------
  let q = $state(''), cat = $state('all'), foc = $state('all');
  const textOK = (a: Adv) => !q.trim() || q.toLowerCase().split(/\s+/).every(w => X!.hay.get(a.id)!.includes(w));
  const ageOK = (a: Adv) => !AGE.v || a.age === AGE.v;
  const focOK = (a: Adv) => foc === 'all' || (foc === 'general' ? !a.focus : a.focus === foc);
  const catOK = (a: Adv, c = cat) => c === 'all' || (c === 'everyone' ? !a.who : !!a.uniq?.includes(c));
  // advances matching age + text + focus, whatever the availability filter says (those counts go on the filter buttons)
  const base = $derived(D && X ? D.advances.filter(a => ageOK(a) && textOK(a) && focOK(a)) : []);
  const counts = $derived({all: base.length, everyone: base.filter(a => !a.who).length,
    ...Object.fromEntries(CATS.map(([c]) => [c, base.filter(a => a.uniq?.includes(c)).length]))} as Record<string, number>);
  const filtered = $derived(base.filter(a => catOK(a)));
  const listed = $derived([...filtered].sort((a, b) => a.age - b.age || a.name.localeCompare(b.name)));
  const LIMIT = 300;

  // ---- overview: per age, per focus ----------------------------------------------------------------------------
  const primary = (a: Adv) => CATS.map(c => c[0]).find(c => a.uniq?.includes(c)) ?? 'other';
  const ageBlocks = $derived(!D ? [] : Object.keys(D.ages).map(Number).filter(n => !AGE.v || n === AGE.v).map(n => {
    const l = filtered.filter(a => a.age === n);
    return {n, total: l.length, open: l.filter(a => !a.who && !a.focus).sort(cmp),
      foc: FOCUS_ORDER.map(f => [f, l.filter(a => a.focus === f).sort(cmp)] as const),
      restricted: CATS.map(([c, label]) => [c, label, l.filter(a => a.who && !a.focus && primary(a) === c).sort(cmp)] as const).filter(r => r[2].length)};
  }));

  // ---- overview: unique advances grouped by who they are for ---------------------------------------------------------
  const positive = (c: Clause, neg = false, out: Clause[] = []): Clause[] => {
    neg = neg !== !!c.not;
    if (c.parts) c.parts.forEach(p => positive(p, neg, out)); else if (!neg) out.push(c);
    return out;
  };
  interface Group { key: string; name: string; type: string; cap: boolean; tag?: string; items: Adv[] }
  const groups = $derived.by(() => {
    if (!X || cat === 'all' || cat === 'everyone') return [] as Group[];
    const m = new Map<string, Group>();
    const add = (key: string, name: string, type: string, cap: boolean, a: Adv) => {
      if (!m.has(key)) m.set(key, {key, name, type, cap, tag: type === 'tag' ? key.slice(4) : undefined, items: []});
      const g = m.get(key)!;
      if (!g.items.includes(a)) g.items.push(a);
    };
    for (const a of filtered) {
      let hit = false;
      for (const c of (a.who ?? []).flatMap(c => positive(c)))
        if ((CAT[c.type] ?? 'other') === cat) c.ids!.forEach((i, k) => { hit = true; add(`${c.type}:${i}`, c.names![k], c.type, !!c.cap, a); });
      if (!hit && a.whoText) add('excl:' + a.whoText, a.whoText, 'excl', false, a);
    }
    for (const g of m.values()) g.items.sort((a, b) => a.age - b.age || cmp(a, b));
    return [...m.values()].sort((a, b) => a.name.localeCompare(b.name));
  });

  // details are filled in only when opened: some lists hold hundreds of rows
  let opened = $state<Record<string, boolean>>({});
  const isOpen = (k: string, dflt = false) => opened[k] ?? dflt;

  // ---- text helpers -------------------------------------------------------------------------------------------------
  const clabel = (c: Clause) => (c.cap ? `Capital in ${TL[c.type].toLowerCase()}` : TL[c.type]);
  const shorten = (s: string, n = 46) => s.length > n ? s.slice(0, n - 1) + '…' : s;
  const effects = (a: Adv) => {
    const m = (a.mods ?? []).slice(0, 3), u = (a.unlocks ?? []).slice(0, 2);
    return {m, u, more: (a.mods?.length ?? 0) - m.length + (a.unlocks?.length ?? 0) - u.length};
  };
  const swatch = (t: string) => { const c = N?.countries[t]?.color; return c ? `rgb(${c.join(',')})` : '#4a5260'; };
  const unlockIcon = (kind: string, uid: string, nm: string) => kind === 'unit' && DATA.units[uid] ? icon('units', DATA.units[uid].cat, nm) : '';
  const unlockGroups = (a: Adv) => KIND_ORDER.map(k => [k, (a.unlocks ?? []).filter(u => u[0] === k)] as const).filter(g => g[1].length)
    .concat([...new Set((a.unlocks ?? []).map(u => u[0]).filter(k => !KIND[k]))].map(k => [k, a.unlocks!.filter(u => u[0] === k)] as const));
  const unlockLink = (kind: string, uid: string) => kind === 'building' && DATA.buildings[uid] ? `#b/${uid}` : kind === 'production_method' && pmBuilding.has(uid) ? `#b/${pmBuilding.get(uid)}` : null;
  const ageLine = (n: number) => `Age ${ROMAN[n]}: ${D?.ages[n] ?? ''}`;

  const adv = $derived(id && X ? X.byId.get(id) ?? null : null);
  const also = $derived(adv?.whoText && X ? (X.sameWho.get(adv.whoText) ?? []).filter(a => a.id !== adv.id).sort((a, b) => a.age - b.age || cmp(a, b)) : []);
  const prereq = $derived(adv && X ? (adv.requires ?? []).map(r => X.byId.get(r) ?? r) : []);
  const next = $derived(adv && X ? [...(X.leads.get(adv.id) ?? [])].sort((a, b) => a.age - b.age || cmp(a, b)) : []);
</script>

{#snippet aicon(a: Adv, cls = 'aic')}{#if a.icon}<img class={cls} src="icons/advances/{a.icon}.png" alt="" loading="lazy">{:else}<span class={cls}></span>{/if}{/snippet}

{#snippet row(a: Adv, skip = '')}
  {@const e = effects(a)}
  <a class="advrow" class:uniq={!!a.who} href="#r/{a.id}">
    {@render aicon(a)}
    <span class="an"><b>{a.name}</b>
      {#if a.who && !(skip && a.whoText?.endsWith(': ' + skip))}<span class="tag who" title={a.whoText}>{shorten(a.whoText ?? '')}</span>{/if}
      <span class="fxs">
        {#each e.m as [l, v], i}{i ? ' · ' : ''}{l} <b>{v}</b>{/each}{#if e.m.length && e.u.length} · {/if}{#if e.u.length}unlocks {e.u.map(u => u[2]).join(', ')}{/if}{#if e.more > 0}<i> +{e.more} more</i>{/if}
        {#if !e.m.length && !e.u.length}<i>no direct modifiers</i>{/if}
      </span>
    </span>
  </a>
{/snippet}

{#snippet clause(c: Clause)}
  {#if c.parts}
    <span class="og">{#if c.not}<span class="or">none of</span>{/if}
      {#each c.parts as p, i}{#if i}<span class="or">{c.type === 'any' ? 'or' : 'and'}</span>{/if}{@render clause(p)}{/each}</span>
  {:else}
    <span class="cl" class:not={c.not}>
      {#if c.type !== 'other'}<span class="tl">{c.not ? 'Not ' + clabel(c).toLowerCase() : clabel(c)}</span>{:else if c.not}<span class="tl">Not</span>{/if}
      {#each c.ids ?? [] as i, k}
        {#if c.type === 'tag' && N?.countries[i]}
          <a class="chip nat" href="#n/{i}"><span class="fl" style="background:{swatch(i)}"><img src="flags/{i}.png" alt="" loading="lazy" onerror={e => e.currentTarget.remove()}></span>{c.names![k]}</a>
        {:else}<span class="tag big">{c.names![k]}</span>{/if}
      {/each}
    </span>
  {/if}
{/snippet}

{#snippet advchip(a: Adv | string)}
  {#if typeof a === 'string'}<span class="chip">{a}</span>
  {:else}<a class="chip" href="#r/{a.id}">{@render aicon(a, 'ic')}{a.name}<span class="tag age">{ROMAN[a.age]}</span></a>{/if}
{/snippet}

<div class="layout">
  <aside>
    <h3>Research</h3>
    <input class="nfilter" placeholder="Find an advance, effect, country…" bind:value={q} autocomplete="off">
    {#if D}
      <div class="flbl">Available to</div>
      <div class="pills">
        {#each [['all', 'All'], ['everyone', 'Everyone'], ...CATS] as [c, label]}
          <button class:on={cat === c} onclick={() => cat = c} title="Advances {c === 'all' ? 'of any kind' : c === 'everyone' ? 'open to every country' : 'restricted by ' + label.toLowerCase()}">{label}<span class="n">{counts[c]}</span></button>
        {/each}
      </div>
      <div class="flbl">Focus</div>
      <div class="pills">
        <button class:on={foc === 'all'} onclick={() => foc = 'all'}>All</button>
        <button class:on={foc === 'general'} onclick={() => foc = 'general'} title="Advances every country can research">General</button>
        {#each FOCUS_ORDER as f}<button class:on={foc === f} onclick={() => foc = f} title={D.focus[f]}>{D.focus[f].replace(' Focus', '')}</button>{/each}
      </div>
      <p class="meta note">{AGE.v ? ageLine(AGE.v) + ' (change it in the header)' : 'All ages'} · {filtered.length} advances</p>
      <div class="blist">
        {#each listed.slice(0, LIMIT) as a (a.id)}
          <a href="#r/{a.id}" class:on={id === a.id}>{@render aicon(a, 'sic')}<span class="nm">{a.name}</span>
            {#if a.who}<span class="dot" title={a.whoText}></span>{/if}<span class="tag up-tag">{ROMAN[a.age]}</span></a>
        {/each}
        {#if listed.length > LIMIT}<p class="meta">+{listed.length - LIMIT} more: narrow the filters.</p>{/if}
        {#if !listed.length}<p class="meta">Nothing matches.</p>{/if}
      </div>
    {:else}<p class="meta">Loading advances…</p>{/if}
  </aside>

  <main>{#key id}<div class="enter">
    {#if !D || !X}
      <p class="meta">Loading advances…</p>
    {:else if id && !adv}
      <div class="title"><div><h2>Unknown advance</h2><p class="desc">There is no advance called "{id}". <a class="chip" href="#r">Back to Research</a></p></div></div>
    {:else if adv}
      <!-- ================= one advance ================= -->
      <div class="title adv">
        {#if adv.icon}<img class="bigic" src="icons/advances/{adv.icon}.png" alt="">{/if}
        <div><h2>{adv.name}</h2>
          <div class="meta"><span>{ageLine(adv.age)}</span>{#if adv.focus}<span>{D.focus[adv.focus]}</span>{/if}
            {#if adv.cost}<span>research cost {adv.cost}</span>{/if}<span>{adv.who ? 'restricted' : 'open to everyone'}</span></div>
          {#if T[adv.id]}<p class="desc">{T[adv.id]}</p>{/if}
        </div>
        <a class="chip back" href="#r">All research</a>
      </div>

      <div class="ncols">
        <div>
          <section class="card"><h4 class="out">What it gives<small>once researched</small></h4>
            {#each adv.mods ?? [] as [l, v]}<div class="mrow"><span>{l}</span><b>{v}</b></div>{/each}
            {#each unlockGroups(adv) as [k, us]}
              <div class="ugr"><span class="tl">Unlocks {(KIND[k] ?? k.replace(/_/g, ' ')).toLowerCase()}</span>
                {#each us as [, uid, nm]}
                  {@const href = unlockLink(k, uid)}
                  {#if k === 'building' && DATA.buildings[uid]}{@html bChip(uid)}
                  {:else if href}<a class="chip" href={href}>{nm}</a>
                  {:else}<span class="chip">{@html unlockIcon(k, uid, nm)}{nm}</span>{/if}
                {/each}
              </div>
            {/each}
            {#if !adv.mods?.length && !adv.unlocks?.length}<p class="none">No modifiers of its own: it is a stepping stone in the tree.</p>{/if}
          </section>
          {#if adv.during?.length}
            <section class="card"><h4 class="in">While researching<small>applies as long as it is being researched</small></h4>
              {#each adv.during as [l, v]}<div class="mrow"><span>{l}</span><b>{v}</b></div>{/each}
            </section>
          {/if}
          <section class="card"><h4 class="in">Prerequisites<small>research these first</small></h4>
            {#if prereq.length}<div class="chips">{#each prereq as p}{@render advchip(p)}{/each}</div>{:else}<p class="none">None: it starts a branch.</p>{/if}
          </section>
          <section class="card"><h4 class="out">Leads to<small>advances that need this one</small></h4>
            {#if next.length}<div class="chips">{#each next as p}{@render advchip(p)}{/each}</div>{:else}<p class="none">Nothing builds on it.</p>{/if}
          </section>
        </div>
        <div>
          <section class="card"><h4 class="pop">Who can get it<small>{adv.who ? 'restricted' : 'everyone'}</small></h4>
            {#if adv.who}
              {#each adv.who as c}<div class="wrow">{@render clause(c)}</div>{/each}
              <p class="meta">All of the above must hold. Country chips link to nations on the map in 1337.</p>
            {:else}<p>Every country can research it{adv.focus ? ', if it took the ' + D.focus[adv.focus] + ' at the start of the age' : ''}.</p>{/if}
            {#if adv.focus}<p class="meta">{D.focus[adv.focus]}: each age opens with a choice of Administrative, Diplomatic or Military Focus. Only the 10 advances of the chosen focus appear in that age, on top of the general ones.</p>{/if}
          </section>
          {#if adv.req}
            <section class="card"><h4 class="in">To research it<small>conditions beyond the prerequisites</small></h4>
              {#each adv.req as c}<div class="wrow">{@render clause(c)}</div>{/each}
            </section>
          {/if}
          {#if also.length}
            <section class="card"><h4 class="gold">Same restriction<small>{also.length} more only for {shorten(adv.whoText ?? '', 60)}</small></h4>
              <div class="chips">{#each also.slice(0, 60) as p}{@render advchip(p)}{/each}</div>
              {#if also.length > 60}<p class="meta">+{also.length - 60} more.</p>{/if}
            </section>
          {/if}
        </div>
      </div>
    {:else}
      <!-- ================= overview ================= -->
      <div class="title"><div><h2>Research</h2>
        <p class="desc">Every advance in the game, {D.advances.length} of them, with what it gives, what it needs and who can get it. Each age has the same general tree for
          everyone, plus advances tied to a country, culture, religion or region. From the Renaissance on, each age also opens with a <b>focus</b> choice: Administrative, Diplomatic or Military.
          A country that picks one gets that focus's 10 extra advances for the age.</p>
        <div class="meta"><span>{AGE.v ? ageLine(AGE.v) : 'all ages (pick one in the header)'}</span>
          <span>{counts.everyone} open to everyone</span><span>{base.length - counts.everyone} restricted</span></div>
      </div></div>

      {#if cat === 'all' || cat === 'everyone'}
        {#each ageBlocks as b (b.n)}
          <section class="card"><h4 class="gold">{ageLine(b.n)}<small>{b.total} advances</small></h4>
            {#if b.foc.some(f => f[1].length)}
              <div class="ncols">
                {#each b.foc as [f, list]}
                  {#if list.length}<div><div class="fhead">{D.focus[f]}<span class="cnt">{list.length}</span></div>{#each list as a (a.id)}{@render row(a)}{/each}</div>{/if}
                {/each}
              </div>
            {/if}
            {#if b.open.length}
              <details class="ugroup" open={isOpen(b.n + 'open', !!AGE.v)} ontoggle={e => opened[b.n + 'open'] = e.currentTarget.open}>
                <summary>Open to everyone<span class="cnt">{b.open.length}</span></summary>
                {#if isOpen(b.n + 'open', !!AGE.v)}<div class="advs">{#each b.open as a (a.id)}{@render row(a)}{/each}</div>{/if}
              </details>
            {/if}
            {#each b.restricted as [c, label, list]}
              {@const k = b.n + c}
              <details class="ugroup" open={isOpen(k)} ontoggle={e => opened[k] = e.currentTarget.open}>
                <summary>{label}-specific advances<span class="cnt">{list.length}</span></summary>
                {#if isOpen(k)}<div class="advs">{#each list as a (a.id)}{@render row(a)}{/each}</div>{/if}
              </details>
            {/each}
            {#if !b.total}<p class="none">Nothing matches the filters.</p>{/if}
          </section>
        {/each}
        {#if cat === 'all'}
          <section class="card"><h4 class="pop">Unique advances<small>browse them by who gets them</small></h4>
            <div class="chips">{#each CATS as [c, label]}<button class="chip" onclick={() => cat = c}>By {label.toLowerCase()} <span class="n">{counts[c]}</span></button>{/each}</div>
          </section>
        {/if}
      {:else}
        <section class="card"><h4 class="pop">Unique advances by {CATS.find(c => c[0] === cat)?.[1].toLowerCase()}<small>{groups.length} {groups.length === 1 ? 'group' : 'groups'} · {filtered.length} advances · {AGE.v ? ageLine(AGE.v) : 'all ages'}</small></h4>
          <p class="meta">An advance restricted to several {cat === 'other' ? 'things' : cat === 'country' ? 'countries' : cat === 'culture' ? 'cultures' : cat === 'religion' ? 'religions' : 'regions'} is listed under each of them.
            {#if cat === 'other'}Government types, reforms, subject status and exclusions ("everyone except…") land here.{/if}</p>
          {#each groups as g (g.key)}
            {@const k = 'g' + cat + g.key}
            <details class="ugroup" open={isOpen(k, groups.length <= 6)} ontoggle={e => opened[k] = e.currentTarget.open}>
              <summary>{#if g.tag && N?.countries[g.tag]}<span class="fl" style="background:{swatch(g.tag)}"><img src="flags/{g.tag}.png" alt="" loading="lazy" onerror={e => e.currentTarget.remove()}></span>{/if}{g.name}
                {#if g.type !== 'tag' && g.type !== 'excl' && g.type !== 'other'}<span class="tag">{g.cap ? 'capital in ' : ''}{TL[g.type].toLowerCase()}</span>{/if}<span class="cnt">{g.items.length}</span>
                {#if g.tag && N?.countries[g.tag]}<a class="gl" href="#n/{g.tag}" onclick={e => e.stopPropagation()}>nation page</a>{/if}</summary>
              {#if isOpen(k, groups.length <= 6)}<div class="advs">{#each g.items as a (a.id)}
                <div class="agrow"><span class="tag age">{ROMAN[a.age]}</span>{@render row(a, g.name)}</div>{/each}</div>{/if}
            </details>
          {:else}<p class="none">Nothing matches the filters.</p>{/each}
        </section>
      {/if}
    {/if}
  </div>{/key}</main>
</div>

<style>
  .pills { display: flex; flex-wrap: wrap; gap: 4px; margin: 0 0 10px; }
  .pills button { cursor: pointer; font-family: var(--serif); font-size: 12.5px; color: var(--gold); padding: 2px 8px; border-radius: 3px;
    border: 1px solid var(--line); background: linear-gradient(#2a3542, #1d2631); }
  .pills button:hover { border-color: var(--frame-hi); }
  .pills button.on { border-color: var(--frame-hi); background: linear-gradient(#5a4a22, #2e2410); color: #fff6d8; box-shadow: 0 0 6px #f0d58c55; }
  .pills .n { margin-left: 5px; color: var(--dim); font-size: 11px; font-variant-numeric: tabular-nums; }
  .note { margin: 0 0 6px; font-size: 12.5px; }
  .blist .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .blist .dot { flex: none; width: 6px; height: 6px; border-radius: 50%; background: var(--frame-hi); }
  .sic { width: 22px; height: 22px; flex: none; object-fit: contain; }
  span.sic { display: inline-block; }
  .aic { width: 34px; height: 34px; flex: none; object-fit: contain; filter: drop-shadow(0 1px 1px #000c); }
  span.aic { display: inline-block; }
  .advrow { display: flex; gap: 8px; align-items: flex-start; padding: 4px 6px; border-bottom: 1px solid #ffffff0d; }
  .advrow:hover { background: var(--panel2); }
  .advrow.uniq { border-left: 2px solid var(--frame-hi); padding-left: 4px; }
  .advrow .an > b { color: var(--text); font-weight: 600; margin-right: 6px; }
  .advrow:hover .an > b { color: var(--gold); }
  .tag.who { color: var(--gold); border-color: #6b5a33; white-space: nowrap; }
  .fxs { display: block; font-size: 12.5px; color: var(--dim); }
  .fxs b { color: var(--out); font-weight: normal; }
  .advs { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 0 14px; margin-top: 4px; }
  .agrow { display: flex; align-items: flex-start; gap: 4px; }
  .agrow > .advrow { flex: 1; min-width: 0; }
  .agrow > .tag { margin-top: 8px; flex: none; min-width: 26px; text-align: center; }
  .fhead { color: var(--gold); font-size: 13px; letter-spacing: 1px; text-transform: uppercase; padding: 4px 6px; margin-bottom: 2px;
    border-bottom: 1px solid var(--frame); background: linear-gradient(90deg, var(--band), transparent); }
  .fhead .cnt { margin-left: 8px; }
  .ugroup { margin-top: 10px; }
  .ugroup > summary .tag { margin-left: 8px; font-variant: normal; letter-spacing: 0; }
  .ugroup > summary :global(.fl) { margin-right: 8px; }
  .gl { margin-left: 10px; font-size: 12px; color: var(--dim); font-variant: normal; }
  .gl:hover { color: var(--gold); }
  .title.adv { position: relative; }
  .bigic { width: 72px; height: 72px; flex: none; object-fit: contain; filter: drop-shadow(0 2px 3px #000c); }
  .back { margin-left: auto; align-self: flex-start; }
  .mrow { display: flex; justify-content: space-between; gap: 12px; padding: 3px 0; border-bottom: 1px solid #ffffff0d; }
  .mrow b { color: var(--out); font-weight: normal; white-space: nowrap; }
  .ugr { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; padding: 6px 0 2px; }
  .tl { font-size: 11px; letter-spacing: 1.2px; text-transform: uppercase; color: var(--gold); margin-right: 6px; }
  .ugr .tl { flex-basis: 100%; }
  .chips { display: flex; flex-wrap: wrap; gap: 1px; }
  .chips button.chip { cursor: pointer; font: inherit; color: var(--gold); padding: 4px 10px; }
  .chips .tag.age { margin-left: 3px; }
  .wrow { padding: 5px 0; border-bottom: 1px solid #ffffff0d; }
  .cl { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 3px; }
  .cl.not .tl { color: var(--in); }
  .tag.big { font-size: 13px; padding: 2px 8px; color: var(--text); }
  .og { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 3px 4px; }
</style>
