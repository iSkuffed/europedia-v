<script module lang="ts">
  // public/privileges.json (privileges.py): every estate privilege and government reform (route #e/reform:<id>), their modifiers, and who can get them
  export interface WItem {
    type: string; kind: string; text: string; ids?: string[]; names?: string[]; not?: boolean; any?: WItem[]; all?: WItem[];
    priv?: string; reform?: string; derived?: boolean;
  }
  type Mod = [string, string];
  interface Group { kind: string; when?: string; mods: Mod[]; estate: Mod[] }
  interface Source { kind: 'advance' | 'decision' | 'event'; id: string; name: string; age?: string; tags?: string[] }
  interface Priv {
    id: string; name: string; estate: string; estateName: string; desc?: string; groups: Group[]; sum: string[];
    who: WItem[]; whoText: string; requires?: WItem[]; revoke: WItem[]; canRevoke: boolean; unlock?: Source[];
    conflicts?: string[]; needs?: string[]; onActivate?: string[]; onDeactivate?: string[]; months?: number;
    types: string[]; availability: string[];
  }
  interface Reform {
    id: string; name: string; gov: string | null; govName: string; group: string; age: string | null; ageName: string; ageIdx: number;
    major: boolean; unique?: boolean; noRebel?: boolean; desc?: string; groups: Group[]; sum: string[]; slots?: string; values?: string[];
    who: WItem[]; whoText: string; requires?: WItem[]; locked?: WItem[]; conflicts?: string[]; needs?: string[]; unlock?: Source[];
    onActivate?: string[]; onDeactivate?: string[]; months?: number; types: string[]; availability: string[];
  }
  interface PData {
    estates: { id: string; name: string; count: number }[]; privileges: Priv[];
    reformGroups: { id: string; name: string; count: number }[]; ages: { id: string; name: string }[]; reforms: Reform[];
  }
</script>

<script lang="ts">
  import { loadPrivileges, preloadCards } from './lib/cards';

  let { id }: { id: string | null } = $props();
  let D = $state<PData>();
  loadPrivileges().then(d => D = d as unknown as PData);
  preloadCards();

  const TYPE_LABEL: Record<string, string> = {tag: 'Country', culture: 'Culture', religion: 'Religion', region: 'Region', government: 'Government', unlock: 'Unlock', other: 'Other', any: 'Any of', all: 'Everyone'};
  const AVAIL: [string, string][] = [['', 'Any'], ['all', 'Everyone'], ['tag', 'Country-specific'], ['culture', 'Culture'], ['religion', 'Religion'], ['region', 'Region'], ['other', 'Other']];

  let filter = $state(''), estSel = $state<string[]>([]), avail = $state(''), kind = $state('');
  // privileges and government reforms share the page: reforms live at #e/reform:<id>
  const RP = 'reform:';
  let mode = $state<'priv' | 'reform'>('priv');
  $effect.pre(() => { if (id) mode = id.startsWith(RP) ? 'reform' : 'priv'; });
  const setMode = (m: 'priv' | 'reform') => { mode = m; if (id) location.hash = 'e'; };
  let grpSel = $state<string[]>([]), ageSel = $state<string[]>([]), rkind = $state('');
  let cards = $state(localStorage.getItem('privView') === 'cards');
  $effect(() => localStorage.setItem('privView', cards ? 'cards' : 'list'));
  let mainEl = $state<HTMLElement>();
  $effect(() => { id; mainEl?.scrollTo(0, 0); });
  const toggle = (e: MouseEvent) => (e.target as Element).closest('section.card > h4')?.parentElement!.classList.toggle('shut');

  const byId = $derived(D ? Object.fromEntries(D.privileges.map(p => [p.id, p])) : {} as Record<string, Priv>);
  const isR = $derived(!!id?.startsWith(RP));
  const P = $derived(id && !isR ? byId[id] : undefined);
  const rById = $derived(D ? Object.fromEntries(D.reforms.map(r => [r.id, r])) : {} as Record<string, Reform>);
  const R = $derived(isR ? rById[id!.slice(RP.length)] : undefined);
  const rshown = $derived.by(() => {
    if (!D) return [];
    const q = filter.trim().toLowerCase();
    return D.reforms.filter(r => (!grpSel.length || grpSel.includes(r.group)) && (!ageSel.length || (r.age && ageSel.includes(r.age))) && (!avail || r.availability.includes(avail))
      && (!rkind || (rkind === 'major') === r.major) && (!kind || (kind === 'all' ? r.availability.includes('all') : r.types.includes(kind)))
      && (!q || (r.name + ' ' + r.id + ' ' + r.govName + ' ' + r.ageName + ' ' + r.whoText + ' ' + r.groups.flatMap(g => g.mods.concat(g.estate).map(m => m[0])).join(' ')).toLowerCase().includes(q)));
  });
  const rgroupsShown = $derived(D ? D.reformGroups.map(g => ({g, list: rshown.filter(r => r.group === g.id)})).filter(g => g.list.length) : []);
  const toggleIn = (a: string[], v: string) => a.includes(v) ? a.filter(x => x !== v) : [...a, v];
  const shown = $derived.by(() => {
    if (!D) return [];
    const q = filter.trim().toLowerCase();
    return D.privileges.filter(p => (!estSel.length || estSel.includes(p.estate)) && (!avail || p.availability.includes(avail)) && (!kind || (kind === 'all' ? p.availability.includes('all') : p.types.includes(kind)))
      && (!q || (p.name + ' ' + p.id + ' ' + p.estateName + ' ' + p.whoText + ' ' + p.groups.flatMap(g => g.mods.concat(g.estate).map(m => m[0])).join(' ')).toLowerCase().includes(q)));
  });
  const groupsShown = $derived(D ? D.estates.map(e => ({e, list: shown.filter(p => p.estate === e.id)})).filter(g => g.list.length) : []);
  const toggleEst = (e: string) => estSel = estSel.includes(e) ? estSel.filter(x => x !== e) : [...estSel, e];

  // reverse links: who excludes / needs this privilege
  const excludedBy = $derived(P && D ? D.privileges.filter(p => p.conflicts?.includes(P.id)).map(p => p.id) : []);
  const neededBy = $derived(P && D ? D.privileges.filter(p => p.needs?.includes(P.id)).map(p => p.id) : []);
  const rExcludedBy = $derived(R && D ? D.reforms.filter(r => r.conflicts?.includes(R.id)).map(r => r.id) : []);
  const rNeededBy = $derived(R && D ? D.reforms.filter(r => r.needs?.includes(R.id)).map(r => r.id) : []);
  const siblings = $derived(P && D ? D.privileges.filter(p => p.estate === P.estate && p.id !== P.id && p.who.length === P.who.length && p.whoText === P.whoText && P.who.length).map(p => p.id) : []);

  // overview: one short who badge per top-level condition
  interface Badge { type: string; label: string; title: string; not?: boolean }
  const short = (s: string, n = 56) => s.length > n ? s.slice(0, n - 1) + '…' : s;
  function badge(it: WItem): Badge {
    let label: string;
    if (it.names?.length) {
      const k = it.kind === 'country' || it.kind === 'unlocked for' ? '' : it.kind + ' ';
      label = (it.not ? 'not ' : '') + k + it.names.slice(0, 3).join(', ') + (it.names.length > 3 ? ` +${it.names.length - 3}` : '');
    } else label = short(it.text);
    return {type: it.type, label, title: it.text, not: it.not};
  }
  const badges = (p: Priv | Reform): Badge[] => p.who.length ? p.who.map(badge) : [{type: 'all', label: 'Everyone', title: 'No restriction on who is offered it'}];
  const effLine = (p: Priv | Reform) => p.sum.length ? p.sum.join(' · ') : p.groups.flatMap(g => g.estate).map(m => `${m[0]} ${m[1]}`).slice(0, 2).join(' · ');

  const availCount = $derived(D ? Object.fromEntries(AVAIL.slice(1).map(([k]) => [k, (mode === 'reform' ? D!.reforms : D!.privileges).filter(p => p.availability.includes(k)).length])) : {} as Record<string, number>);
  const shownCount = $derived(mode === 'reform' ? rshown.length : shown.length);
  const flagOff = (e: Event) => (e.currentTarget as HTMLElement).remove();
</script>

{#snippet who(it: WItem)}
  {#if it.any}
    <span class="wg">{it.not ? 'None of' : 'Any of'}: {#each it.any as s, i}{#if i}<span class="or">or</span>{/if}{@render who(s)}{/each}</span>
  {:else if it.all}
    <span class="wg">{#if it.kind}<span class="wk">{it.not ? 'not ' : ''}{it.kind}</span>{/if}{#each it.all as s}{@render who(s)}{/each}</span>
  {:else if it.type === 'tag' && it.ids}
    <span class="wb t-tag" class:neg={it.not} class:der={it.derived}><span class="wk">{it.not ? 'not ' : ''}{it.kind}</span>
      {#each it.ids as t, i}<a class="wn" href="#n/{t}"><span class="fl"><img src="flags/{t}.png" alt="" loading="lazy" onerror={flagOff}></span>{it.names?.[i] ?? t}</a>{/each}</span>
  {:else if it.reform}
    <span class="wb t-government" class:neg={it.not}><span class="wk">{it.not ? 'not ' : ''}reform</span><a class="wn" href="#e/{RP}{it.reform}">{it.names?.[0] ?? it.reform}</a></span>
  {:else if it.priv}
    <span class="wb t-other" class:neg={it.not}><span class="wk">{it.not ? 'not ' : ''}privilege</span><a class="wn" href="#e/{it.priv}">{it.names?.[0] ?? it.priv}</a></span>
  {:else}
    <span class="wb t-{it.type}" class:neg={it.not} title={it.text}>{#if it.names?.length}<span class="wk">{it.not ? 'not ' : ''}{it.kind}</span><span class="wn">{it.names.join(', ')}</span>{:else}{it.text}{/if}</span>
  {/if}
{/snippet}

{#snippet wrows(list: WItem[])}
  {#each list as it}<div class="wrow"><span class="wt t-{it.type}">{TYPE_LABEL[it.type] ?? it.type}</span><div class="wc">{@render who(it)}</div></div>{/each}
{/snippet}

{#snippet mods(ms: Mod[])}
  {#each ms as [l, v]}
    <div class="dm"><span class="v">{v === 'Yes' ? '✓' : v}</span><span>{l}</span></div>
  {/each}
{/snippet}

<div class="layout">
  <aside>
    <h3>{mode === 'reform' ? 'Government reforms' : 'Estate privileges'}</h3>
    <div class="pfb mode"><button class:on={mode === 'priv'} onclick={() => setMode('priv')}>Privileges</button><button class:on={mode === 'reform'} onclick={() => setMode('reform')}>Reforms</button></div>
    <input class="nfilter" placeholder={mode === 'reform' ? 'Find a reform…' : 'Find a privilege…'} bind:value={filter} autocomplete="off">
    {#if D}
      <div class="pf">
        {#if mode === 'reform'}
          <div class="pfl">Government</div>
          <div class="pfb">{#each D.reformGroups as g}<button class:on={grpSel.includes(g.id)} onclick={() => grpSel = toggleIn(grpSel, g.id)} title="{g.count} reforms">{g.name}</button>{/each}</div>
          <div class="pfl">Age</div>
          <div class="pfb">{#each D.ages as a}<button class:on={ageSel.includes(a.id)} onclick={() => ageSel = toggleIn(ageSel, a.id)}>{a.name}</button>{/each}</div>
          <div class="pfl">Kind</div>
          <div class="pfb">{#each [['', 'Any'], ['major', 'Major'], ['minor', 'Minor']] as [k, l]}<button class:on={rkind === k} onclick={() => rkind = k} title={k === 'major' ? 'Exclusive: only one major reform per country' : ''}>{l}</button>{/each}</div>
        {:else}
          <div class="pfl">Estate</div>
          <div class="pfb">{#each D.estates as e}<button class:on={estSel.includes(e.id)} onclick={() => toggleEst(e.id)} title="{e.count} privileges">{e.name}</button>{/each}</div>
        {/if}
        <div class="pfl">Available to</div>
        <div class="pfb">{#each AVAIL as [k, l]}<button class:on={avail === k} onclick={() => avail = k} title={k ? `${availCount[k]} ${mode === 'reform' ? 'reforms' : 'privileges'}` : 'No filter'}>{l}</button>{/each}</div>
      </div>
      <div class="blist">
        <a href="#e" class:on={!id}>Overview<span class="tag up-tag">{shownCount}</span></a>
        {#if mode === 'reform'}
          {#each rgroupsShown as g (g.g.id)}
            <h3>{g.g.name}<span class="cnt">{g.list.length}</span></h3>
            {#each g.list as r (r.id)}
              <a href="#e/{RP}{r.id}" class:on={id === RP + r.id}><span class="pn">{r.name}</span>{#if r.who.length}<span class="dot t-{r.types[0] ?? 'other'}" title={r.whoText}></span>{/if}</a>
            {/each}
          {:else}<p class="meta">No reform matches.</p>{/each}
        {:else}
          {#each groupsShown as g (g.e.id)}
            <h3>{g.e.name}<span class="cnt">{g.list.length}</span></h3>
            {#each g.list as p (p.id)}
              <a href="#e/{p.id}" class:on={id === p.id}><span class="pn">{p.name}</span>{#if p.who.length}<span class="dot t-{p.types[0] ?? 'other'}" title={p.whoText}></span>{/if}</a>
            {/each}
          {:else}<p class="meta">No privilege matches.</p>{/each}
        {/if}
      </div>
    {:else}<p class="meta">Loading…</p>{/if}
  </aside>

  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
  <main bind:this={mainEl} onclick={toggle}>{#key id}<div class="enter">
    {#if !D}
      <p class="meta">Loading privileges…</p>
    {:else if isR && !R}
      <div class="title"><div><h2>Unknown reform</h2><p class="desc">There is no government reform called “{id!.slice(RP.length)}”. <a class="wn" href="#e">Back to the overview</a>.</p></div></div>
    {:else if R}
      <div class="title lg"><span class="art big"><img src="icons/reforms/{R.id}.webp" alt=""></span>
        <div><h2>{R.name}</h2>
          <div class="meta"><span>{R.major ? 'Major reform' : 'Government reform'}</span><span>{R.govName}</span>{#if R.age}<span>Age of {R.ageName}</span>{/if}{#if R.months}<span>takes {R.months} months to take effect</span>{/if}{#if R.locked}<span>locked once taken</span>{/if}{#if R.noRebel}<span>not for rebels</span>{/if}</div>
          {#if R.desc}<p class="desc">{R.desc}</p>{/if}
          <div class="wline"><span class="flbl">Who can get it</span>
            {#if R.who.length}{#each R.who as it}{@render who(it)}{/each}{:else}<span class="wb t-all">Everyone</span>{/if}</div>
        </div>
      </div>

      <div class="ncols">
        <div>
          {#each [...new Set(R.groups.filter(g => g.mods.length).map(g => g.kind))] as k}
            <section class="card"><h4 class="out">{k[0].toUpperCase() + k.slice(1)} modifiers<small>{k === 'location' ? 'on each location it applies to' : 'on the whole country'}</small></h4>
              {#each R.groups.filter(g => g.kind === k && g.mods.length) as gr}
                {#if gr.when}<p class="meta cond">only when: {gr.when}</p>{/if}
                {@render mods(gr.mods)}
              {/each}
            </section>
          {/each}
          {#if R.groups.some(g => g.estate.length)}
            <section class="card"><h4 class="pop">Estate effects<small>power and satisfaction</small></h4>
              {#each R.groups.filter(g => g.estate.length) as gr}
                {#if gr.when}<p class="meta">only when: {gr.when}</p>{/if}
                {@render mods(gr.estate)}
              {/each}
            </section>
          {/if}
          {#if R.values?.length}
            <section class="card"><h4 class="gold">Societal focus<small>values this reform pushes</small></h4>
              <div>{#each R.values as v}<span class="chip">{v}</span>{/each}</div>
            </section>
          {/if}
          {#if R.onActivate?.length || R.onDeactivate?.length}
            <section class="card"><h4 class="gold">When adopted or removed</h4>
              {#if R.onActivate?.length}<p class="meta">On adopting</p><ul class="tips">{#each R.onActivate as t}<li>{t}</li>{/each}</ul>{/if}
              {#if R.onDeactivate?.length}<p class="meta">On removing</p><ul class="tips">{#each R.onDeactivate as t}<li>{t}</li>{/each}</ul>{/if}
            </section>
          {/if}
        </div>
        <div>
          <section class="card"><h4 class="gold">Who can get it<small>what makes it available to a country</small></h4>
            {#if R.who.length}
              {@render wrows(R.who)}
              <p class="meta">All of these must hold at once.</p>
            {:else}<p class="none">Nothing restricts it: any country with {R.gov ? `a ${R.govName} government` : 'any government'} can be offered it.</p>{/if}
          </section>

          {#if R.requires?.length}
            <section class="card"><h4 class="in">To adopt it<small>needed before you can pick it</small></h4>{@render wrows(R.requires)}</section>
          {/if}

          <section class="card"><h4 class="in">Removing</h4>
            {#if R.locked?.length}
              <p class="meta">It is locked and cannot be changed by hand while:</p>
              {@render wrows(R.locked)}
            {:else}<p class="none">Not locked: it can be swapped for another reform whenever you like.</p>{/if}
          </section>

          <section class="card"><h4 class="pop">How it unlocks</h4>
            {#if R.unlock?.length}
              {#each R.unlock as s}
                <div class="wrow"><span class="wt t-unlock">{s.kind}</span><div class="wc"><b>{s.name}</b>{#if s.age} <span class="tag">{s.age}</span>{/if}
                  {#each s.tags ?? [] as t}<a class="wn" href="#n/{t}"><span class="fl"><img src="flags/{t}.png" alt="" onerror={flagOff}></span>{t}</a>{/each}</div></div>
              {/each}
            {:else if R.who.some(i => i.type === 'unlock') || R.requires?.some(i => i.type === 'unlock')}
              <p class="none">Granted by a script (an event or a decision flag) that this extractor could not trace.</p>
            {:else}<p class="none">Offered from the start; no advance is needed to unlock it.</p>{/if}
          </section>

          {#if R.conflicts?.length || R.needs?.length || rExcludedBy.length || rNeededBy.length}
            <section class="card"><h4 class="gold">Related reforms</h4>
              {#each [['Cannot be combined with', [...new Set([...(R.conflicts ?? []), ...rExcludedBy])]], ['Needs', R.needs ?? []], ['Needed by', rNeededBy]] as [label, list] (label)}
                {#if list.length}<div class="wrow"><span class="wt t-other">{label}</span><div class="wc">{#each list as r}<a class="chip" href="#e/{RP}{r}">{rById[r]?.name ?? r}</a>{/each}</div></div>{/if}
              {/each}
            </section>
          {/if}
        </div>
      </div>
    {:else if id && !P}
      <div class="title"><div><h2>Unknown privilege</h2><p class="desc">There is no estate privilege called “{id}”. <a class="wn" href="#e">Back to the overview</a>.</p></div></div>
    {:else if P}
      <div class="title lg"><span class="art big"><img src="icons/privileges/{P.id}.webp" alt=""></span>
        <div><h2>{P.name}</h2>
          <div class="meta"><span>{P.estateName}</span>{#if P.months}<span>takes {P.months} months to take effect</span>{/if}{#if !P.canRevoke}<span>cannot be revoked</span>{/if}</div>
          {#if P.desc}<p class="desc">{P.desc}</p>{/if}
          <div class="wline"><span class="flbl">Who can get it</span>
            {#if P.who.length}{#each P.who as it}{@render who(it)}{/each}{:else}<span class="wb t-all">Everyone</span>{/if}</div>
        </div>
      </div>

      <div class="ncols">
        <div>
          {#each [...new Set(P.groups.filter(g => g.mods.length).map(g => g.kind))] as k}
            <section class="card"><h4 class="out">{k[0].toUpperCase() + k.slice(1)} modifiers<small>{k === 'location' ? 'on each location it applies to' : 'on the whole country'}</small></h4>
              {#each P.groups.filter(g => g.kind === k && g.mods.length) as gr}
                {#if gr.when}<p class="meta cond">only when: {gr.when}</p>{/if}
                {@render mods(gr.mods)}
              {/each}
            </section>
          {/each}
          {#if P.groups.some(g => g.estate.length)}
            <section class="card"><h4 class="pop">Estate effects<small>power and satisfaction</small></h4>
              {#each P.groups.filter(g => g.estate.length) as gr}
                {#if gr.when}<p class="meta">only when: {gr.when}</p>{/if}
                {@render mods(gr.estate)}
              {/each}
            </section>
          {/if}
          {#if P.onActivate?.length || P.onDeactivate?.length}
            <section class="card"><h4 class="gold">When granted or removed</h4>
              {#if P.onActivate?.length}<p class="meta">On granting</p><ul class="tips">{#each P.onActivate as t}<li>{t}</li>{/each}</ul>{/if}
              {#if P.onDeactivate?.length}<p class="meta">On removing</p><ul class="tips">{#each P.onDeactivate as t}<li>{t}</li>{/each}</ul>{/if}
            </section>
          {/if}
        </div>
        <div>
          <section class="card"><h4 class="gold">Who can get it<small>what makes it available to a country</small></h4>
            {#if P.who.length}
              {#each P.who as it}
                <div class="wrow"><span class="wt t-{it.type}">{TYPE_LABEL[it.type] ?? it.type}</span><div class="wc">{@render who(it)}</div></div>
              {/each}
              <p class="meta">All of these must hold at once.</p>
            {:else}<p class="none">Nothing restricts it: any country with the {P.estateName} estate can be offered it.</p>{/if}
          </section>

          {#if P.requires?.length}
            <section class="card"><h4 class="in">To enact it<small>needed before you can grant it</small></h4>
              {#each P.requires as it}<div class="wrow"><span class="wt t-{it.type}">{TYPE_LABEL[it.type] ?? it.type}</span><div class="wc">{@render who(it)}</div></div>{/each}
            </section>
          {/if}

          <section class="card"><h4 class="in">Revoking</h4>
            {#if !P.canRevoke}<p>Cannot be revoked once granted.</p>
            {:else if P.revoke.length}
              <p class="meta">It can be removed only while:</p>
              {#each P.revoke as it}<div class="wrow"><span class="wt t-{it.type}">{TYPE_LABEL[it.type] ?? it.type}</span><div class="wc">{@render who(it)}</div></div>{/each}
            {:else}<p class="none">No extra condition: it can be revoked whenever you like.</p>{/if}
          </section>

          <section class="card"><h4 class="pop">How it unlocks</h4>
            {#if P.unlock?.length}
              {#each P.unlock as s}
                <div class="wrow"><span class="wt t-unlock">{s.kind}</span><div class="wc"><b>{s.name}</b>{#if s.age} <span class="tag">{s.age}</span>{/if}
                  {#each s.tags ?? [] as t}<a class="wn" href="#n/{t}"><span class="fl"><img src="flags/{t}.png" alt="" onerror={flagOff}></span>{t}</a>{/each}</div></div>
              {/each}
            {:else if P.who.some(i => i.type === 'unlock') || P.requires?.some(i => i.type === 'unlock')}
              <p class="none">Granted by a script (an event or a decision flag) that this extractor could not trace.</p>
            {:else}<p class="none">Offered from the start; no advance is needed to unlock it.</p>{/if}
          </section>

          {#if P.conflicts?.length || P.needs?.length || excludedBy.length || neededBy.length || siblings.length}
            <section class="card"><h4 class="gold">Related privileges</h4>
              {#each [['Cannot be combined with', [...new Set([...(P.conflicts ?? []), ...excludedBy])]], ['Needs', P.needs ?? []], ['Needed by', neededBy], ['Same restriction', siblings]] as [label, list] (label)}
                {#if list.length}<div class="wrow"><span class="wt t-other">{label}</span><div class="wc">{#each list as r}<a class="chip" href="#e/{r}">{byId[r]?.name ?? r}</a>{/each}</div></div>{/if}
              {/each}
            </section>
          {/if}
        </div>
      </div>
    {:else if mode === 'reform'}
      <div class="title"><div><h2>Government reforms</h2>
        <p class="desc">Every government reform, {D.reforms.length} in all, grouped by the government type that supports it. A reform sets how the state works; a country holds a few at a time, and a
          major reform is exclusive: only one per country. The page shows what each does, who is offered it (any country, or only certain countries, cultures or religions), what it takes to
          adopt, and which reforms rule each other out. Pick one on the left or open it from the lists below.</p>
        <div class="wline"><span class="flbl">Legend</span>
          {#each ['all', 'tag', 'culture', 'religion', 'region', 'government', 'unlock', 'other'] as t}<button class="wb t-{t}" class:on={kind === t} onclick={() => kind = kind === t ? '' : t}
            title={kind === t ? 'Show all again' : t === 'all' ? 'Only reforms open to everyone' : `Only reforms with a ${TYPE_LABEL[t].toLowerCase()} condition`}>{t === 'all' ? 'Everyone' : TYPE_LABEL[t]}</button>{/each}
          {#if kind}<span class="meta">{rshown.length} shown</span>{/if}</div>
        <div class="wline"><span class="flbl">View</span><span class="pfb"><button class:on={!cards} onclick={() => cards = false}>List</button><button class:on={cards} onclick={() => cards = true}>Cards</button></span></div>
      </div></div>
      {#each rgroupsShown as g (g.g.id)}
        <section class="card"><h4 class="gold">{g.g.name}<small>{g.list.length} reforms</small></h4>
          {#if cards}<div class="cardgrid">{#each g.list as r (r.id)}
            <a class="pcard" href="#e/{RP}{r.id}">
              <span class="art"><img src="icons/reforms/{r.id}.webp" alt="" loading="lazy">{#if r.who.length}<span class="dot t-{r.types[0] ?? 'other'}" title={r.whoText}></span>{/if}</span>
              <b class="pn">{r.name}</b>
              <span class="pe">{#if r.major}Major · {/if}{r.age ? r.ageName + ' · ' : ''}{effLine(r)}</span>
            </a>
          {/each}</div>{:else}
          {#each g.list as r (r.id)}
            <a class="prow" href="#e/{RP}{r.id}">
              <b class="pn">{r.name}{#if r.major} <span class="tag">Major</span>{/if}</b>
              <span class="pe">{effLine(r)}</span>
              <span class="pb">{#if r.age}<span class="tag">{r.ageName}</span>{/if}{#each badges(r).slice(0, 3) as b}<span class="wb t-{b.type}" class:neg={b.not} title={b.title}>{b.label}</span>{/each}{#if r.who.length > 3}<span class="tag">+{r.who.length - 3}</span>{/if}</span>
            </a>
          {/each}{/if}
        </section>
      {:else}<p class="meta">No reform matches the filters.</p>{/each}
    {:else}
      <div class="title"><div><h2>Estate privileges</h2>
        <p class="desc">Every privilege you can grant an estate, {D.privileges.length} in all. Each trades the crown's power for estate favour; the page shows what it does, who is offered it
          (everyone, or only certain countries, cultures, religions, regions or governments) and what it takes to grant or revoke. Pick one on the left or open it from the lists below.</p>
        <div class="wline"><span class="flbl">Legend</span>
          {#each ['all', 'tag', 'culture', 'religion', 'region', 'government', 'unlock', 'other'] as t}<button class="wb t-{t}" class:on={kind === t} onclick={() => kind = kind === t ? '' : t}
            title={kind === t ? 'Show all again' : t === 'all' ? 'Only privileges open to everyone' : `Only privileges with a ${TYPE_LABEL[t].toLowerCase()} condition`}>{t === 'all' ? 'Everyone' : TYPE_LABEL[t]}</button>{/each}
          {#if kind}<span class="meta">{shown.length} shown</span>{/if}</div>
        <div class="wline"><span class="flbl">View</span><span class="pfb"><button class:on={!cards} onclick={() => cards = false}>List</button><button class:on={cards} onclick={() => cards = true}>Cards</button></span></div>
      </div></div>
      {#each groupsShown as g (g.e.id)}
        <section class="card"><h4 class="gold">{g.e.name}<small>{g.list.length} privileges</small></h4>
          {#if cards}<div class="cardgrid">{#each g.list as p (p.id)}
            <a class="pcard" href="#e/{p.id}">
              <span class="art"><img src="icons/privileges/{p.id}.webp" alt="" loading="lazy">{#if p.who.length}<span class="dot t-{p.types[0] ?? 'other'}" title={p.whoText}></span>{/if}</span>
              <b class="pn">{p.name}</b>
              <span class="pe">{effLine(p)}</span>
            </a>
          {/each}</div>{:else}
          {#each g.list as p (p.id)}
            <a class="prow" href="#e/{p.id}">
              <b class="pn">{p.name}</b>
              <span class="pe">{effLine(p)}</span>
              <span class="pb">{#each badges(p).slice(0, 3) as b}<span class="wb t-{b.type}" class:neg={b.not} title={b.title}>{b.label}</span>{/each}{#if p.who.length > 3}<span class="tag">+{p.who.length - 3}</span>{/if}</span>
            </a>
          {/each}{/if}
        </section>
      {:else}<p class="meta">No privilege matches the filters.</p>{/each}
    {/if}
  </div>{/key}</main>
</div>

<style>
  .pf { margin: 0 0 10px; }
  .pfl { font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: var(--dim); margin: 6px 0 3px; }
  .pfb { display: flex; flex-wrap: wrap; gap: 3px; }
  .pfb button { cursor: pointer; font-size: 12px; color: var(--text); background: #0d1117; border: 1px solid var(--line); border-radius: 3px; padding: 2px 8px; }
  .pfb button:hover { border-color: var(--frame); }
  .pfb button.on { border-color: var(--frame-hi); color: var(--gold); box-shadow: 0 0 6px #d8b46a55; background: linear-gradient(#3a3017, #1d1a10); }
  aside .blist h3 { display: flex; justify-content: space-between; }
  aside .blist .pn { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mode { margin: 0 0 8px; }
  .cnt { color: var(--gold); font-size: 12px; }
  .dot { margin-left: auto; flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--c); }

  /* who badges: one colour per kind of restriction */
  .t-all { --c: #8fd16f; } .t-tag { --c: #f0d58c; } .t-culture { --c: #e48a5c; } .t-religion { --c: #b79cf0; }
  .t-region { --c: #6fd0c4; } .t-government { --c: #82bde6; } .t-unlock { --c: #c4b48a; } .t-other { --c: #a39a84; } .t-any { --c: #a39a84; }
  .wb { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 3px 6px; margin: 2px 3px 2px 0; padding: 1px 8px; font-size: 13px; line-height: 1.5;
    color: var(--c); border: 1px solid color-mix(in srgb, var(--c) 55%, transparent); border-radius: 10px; background: color-mix(in srgb, var(--c) 12%, #0d1117); }
  button.wb { cursor: pointer; font-family: inherit; }
  button.wb:hover { background: color-mix(in srgb, var(--c) 22%, #0d1117); }
  button.wb.on { background: color-mix(in srgb, var(--c) 30%, #0d1117); border-color: var(--c); box-shadow: 0 0 6px color-mix(in srgb, var(--c) 45%, transparent); }
  .wb.neg { border-style: dashed; text-decoration: none; }
  .wb.neg .wn { text-decoration: line-through; text-decoration-color: color-mix(in srgb, var(--c) 60%, transparent); }
  .wb.der { border-style: dotted; }
  .wk { font-size: 11px; letter-spacing: .6px; text-transform: uppercase; opacity: .75; }
  .wn { color: inherit; }
  a.wn:hover { color: var(--gold); text-decoration: underline; }
  .wb.t-tag a.wn { display: inline-flex; align-items: center; }
  .wb .fl { margin-right: 4px; }
  .wg { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 2px; padding: 1px 6px; border: 1px dashed #6b5a33; border-radius: 6px; color: var(--dim); font-size: 12px; }
  .wline { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; margin-top: 8px; }
  .wline .flbl { margin-right: 8px; }
  .wrow { display: grid; grid-template-columns: 6.5em 1fr; gap: 8px; align-items: start; padding: 5px 0; border-top: 1px solid var(--line); }
  .wrow:first-of-type { border-top: none; }
  .wt { font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: var(--c, var(--dim)); padding-top: 4px; }
  .wc { min-width: 0; }
  .cond { margin: 8px 0 2px; padding-top: 6px; border-top: 1px solid var(--line); font-style: italic; }
  .cond:first-child { border-top: none; margin-top: 0; padding-top: 0; }
  .wc .chip { padding: 2px 7px; }

  /* overview rows */
  .prow { display: grid; grid-template-columns: minmax(10em, 15em) minmax(0, 1fr) minmax(0, 24em); gap: 12px; align-items: center; padding: 5px 4px; border-top: 1px solid var(--line); }
  .cardgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 14px 10px; padding: 8px 2px 4px; }
  .pcard { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px 4px; border-radius: 6px; text-align: center; }
  .pcard:hover { background: var(--panel2); }
  .pcard:hover .pn { color: var(--gold); }
  .pcard:hover .art { border-color: var(--frame-hi); box-shadow: 0 0 10px #d8b46a66, inset 0 0 0 1px #0008; transform: translateY(-2px); }
  .pcard .pn { font-weight: 600; font-size: 14px; line-height: 1.25; }
  .pcard .pe { color: var(--dim); font-size: 12px; line-height: 1.35; display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .art.big { width: 116px; height: 163px; margin-right: 6px; }
  @media (prefers-reduced-motion: reduce) { .pcard:hover .art { transform: none; } }
  .prow:first-of-type { border-top: none; }
  .prow:hover { background: var(--panel2); }
  .prow:hover .pn { color: var(--gold); }
  .prow .pn { font-weight: 600; }
  .prow .pe { color: var(--dim); font-size: 13px; }
  .prow .pn .tag { margin-left: 6px; }
  .prow .pb { display: flex; flex-wrap: wrap; justify-content: flex-end; }
  .prow .wb { font-size: 12px; padding: 0 7px; max-width: 100%; }
  @media (max-width: 1300px) { .prow { grid-template-columns: minmax(8em, 12em) minmax(0, 1fr); } .prow .pb { grid-column: 1 / -1; justify-content: flex-start; } }
</style>
