<script lang="ts">
  // Plays one recorded battle (BattleLog.frames) day by day: regiments in their lanes, red as they bleed, solid red once broken.
  import type { BattleLog, Cat, Unit, UnitsData } from './lib/units';

  let { log, D, where, onagain, onclose }: { log: BattleLog; D: UnitsData; where: string; onagain: () => void; onclose: () => void } = $props();

  const U = $derived(new Map(D.units.map(u => [u.id, u])));
  const days = $derived(log.days);
  const bombard = $derived(log.notes.some(n => n.startsWith('Bombard')) ? D.defines.BOMBARD_DAYS : 0);
  const SIDES = ['att', 'def'] as const;
  const NAME = { att: 'Attacker', def: 'Defender' };
  const art = (u: Unit) => `icons/units/${u.icon ?? u.id}.webp`;
  const catIc = (c: Cat) => `icons/units/army_${c}.png`;
  const men = (v: number) => Math.round(v).toLocaleString('en');

  let day = $state(0), playing = $state(true), speed = $state(1);
  const MS = 1100;
  // a fresh battle starts again from day 0
  $effect(() => { log; day = 0; playing = true; });
  $effect(() => {
    if (!playing) return;
    const t = setInterval(() => { if (day >= days) playing = false; else day++; }, MS / speed);
    return () => clearInterval(t);
  });
  const done = $derived(day >= days);

  const states = $derived([log.start, ...log.daily]);
  const frame = $derived(log.frames[day]), prev = $derived(log.frames[Math.max(0, day - 1)]);
  const now = $derived(states[day]);

  // token size by army size, so a 200-regiment stack still fits
  const size = $derived(Math.max(log.regs.att.length, log.regs.def.length) <= 24 ? 46 : Math.max(log.regs.att.length, log.regs.def.length) <= 70 ? 34 : 24);
  const lane = (w: 'att' | 'def', p: number) => frame[w].flatMap((r, i) => r[2] === p ? [i] : []);

  const hurt = (w: 'att' | 'def', i: number) => 1 - frame[w][i][0] / Math.max(1, log.regs[w][i].max);
  const broken = (w: 'att' | 'def', i: number) => (frame[w][i][3] & 2) !== 0;
  const unitOf = (w: 'att' | 'def', i: number) => U.get(log.regs[w][i].unit);

  // what happened today, from the frame before to this one
  function events(d: number): string[] {
    if (d < 1) return [];
    const a = log.frames[d - 1], b = log.frames[d], out: string[] = [];
    const m = (w: 'att' | 'def') => states[d - 1][w].men - states[d][w].men;
    out.push(`<b class="ca">Attacker</b> loses ${men(m('att'))} men, <b class="cd">Defender</b> ${men(m('def'))}`);
    for (const w of SIDES) {
      const br = b[w].flatMap((r, i) => (r[3] & 2) && !(a[w][i][3] & 2) ? [unitOf(w, i)?.name ?? '?'] : []);
      if (br.length) out.push(`<b class="${w === 'att' ? 'ca' : 'cd'}">${NAME[w]}</b>: ${br.length > 3 ? `${br.length} regiments break` : `${br.join(', ')} ${br.length > 1 ? 'break' : 'breaks'}`}`);
      const up = b[w].filter((r, i) => a[w][i][2] === 3 && r[2] < 3).length;
      if (up) out.push(`<b class="${w === 'att' ? 'ca' : 'cd'}">${NAME[w]}</b>: ${up} ${up > 1 ? 'regiments move' : 'regiment moves'} up from reserve`);
    }
    return out;
  }
  const feed = $derived(Array.from({ length: Math.min(day, 4) }, (_, k) => day - k).map(d => ({ d, e: events(d) })));

  const share = (w: 'att' | 'def') => Math.max(0, Math.min(1, now[w].men / Math.max(1, log.start[w].men)));
  const mshare = (w: 'att' | 'def') => now[w].maxMorale ? Math.max(0, Math.min(1, now[w].morale / now[w].maxMorale)) : 0;
  const dice = (w: 'att' | 'def') => day ? log.daily[day - 1][w === 'att' ? 'diceAtt' : 'diceDef'] : null;
  const phase = $derived(day === 0 ? 'The armies deploy' : day <= bombard ? 'Bombardment' : done ? 'The field is decided' : 'Battle joined');
  const sw = (w: 'att' | 'def') => w === 'att' ? 'The attacker' : 'The defender';

  function key(e: KeyboardEvent) {
    if (e.key === 'Escape') onclose();
    else if (e.key === ' ' && !(e.target instanceof HTMLButtonElement)) { e.preventDefault(); toggle(); }
  }
  function toggle() { if (done) { day = 0; playing = true; } else playing = !playing; }
</script>

<svelte:window onkeydown={key} />

{#snippet token(w: 'att' | 'def', i: number)}
  {@const u = unitOf(w, i)}
  {@const r = frame[w][i]}
  {@const h = hurt(w, i)}
  {@const br = broken(w, i)}
  <div class="tk {w}" class:eng={(r[3] & 1) !== 0 && !br} class:dead={br} class:res={r[2] === 3} style:--red={br ? 1 : Math.min(0.85, h * 1.15)} style:--mor={log.regs[w][i].maxMorale ? Math.max(0, r[1] / log.regs[w][i].maxMorale) : 0}
       title="{u?.name ?? '?'}: {br ? 'broken' : `${men(r[0])} of ${men(log.regs[w][i].max)} men, morale ${r[1].toFixed(2)} of ${log.regs[w][i].maxMorale.toFixed(2)}`}">
    {#if u}<img src={art(u)} alt="" draggable="false">{/if}
    <i class="red"></i>
    {#if br}<span class="x">✕</span>{/if}
    <span class="bar"><b class="men" style:width="{(1 - h) * 100}%"></b></span>
    <span class="bar thin"><b class="mor" style:width="{br ? 0 : 'calc(var(--mor) * 100%)'}"></b></span>
  </div>
{/snippet}

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="back" onclick={e => e.target === e.currentTarget && onclose()}>
  <div class="th" role="dialog" aria-modal="true" aria-label="Battle replay" style:--spd={speed}>
    <div class="top">
      <h3><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 3.5L16 16M12 16l4-4M16 16l3 3"/><circle cx="20.3" cy="20.3" r="1"/><path d="M20.5 3.5L8 16M12 16 8 12M8 16l-3 3"/><circle cx="3.7" cy="20.3" r="1"/></svg>Battle</h3>
      <span class="where">{where}</span>
      <span class="phase">{phase}</span>
      <button class="close" onclick={onclose} title="Close (Esc)" aria-label="Close">✕</button>
    </div>

    <div class="score">
      {#each SIDES as w}
        <div class="sc {w}">
          <div class="nm"><span>{NAME[w]}</span><b>{men(now[w].men)}<small> / {men(log.start[w].men)} men</small></b></div>
          <div class="trk" title="Men still standing"><span class="fill" style:width="{share(w) * 100}%"></span></div>
          <div class="trk m" title="Average morale of the regiments still fighting"><span class="fill" style:width="{mshare(w) * 100}%"></span></div>
          <div class="sub"><span>morale {now[w].morale.toFixed(2)}</span><span>{now[w].broken} broken</span>{#if dice(w) !== null}<span title="Effective dice roll for the day, after the base roll and every modifier">dice {dice(w)}</span>{/if}</div>
        </div>
        {#if w === 'att'}<div class="dayc"><b>{day}</b><span>{day === 0 ? 'start' : day === 1 ? 'day' : 'days'}</span></div>{/if}
      {/each}
    </div>

    <div class="field">
      {#each [0, 1, 2] as p}
        <div class="ln" style:--t="{size}px">
          <div class="cell att">{#each lane('att', p) as i (i)}{@render token('att', i)}{/each}</div>
          <div class="mid" class:hot={lane('att', p).some(i => frame.att[i][3] & 1) && lane('def', p).some(i => frame.def[i][3] & 1)}><span></span></div>
          <div class="cell def">{#each lane('def', p) as i (i)}{@render token('def', i)}{/each}</div>
        </div>
      {/each}
      {#if lane('att', 3).length || lane('def', 3).length}<div class="ln rsv" style:--t="{size}px">
        <div class="cell att"><em>reserve</em>{#each lane('att', 3) as i (i)}{@render token('att', i)}{/each}</div>
        <div class="mid"></div>
        <div class="cell def">{#each lane('def', 3) as i (i)}{@render token('def', i)}{/each}<em>reserve</em></div>
      </div>{/if}
    </div>

    <div class="feed" aria-live="polite">
      {#if done}
        <div class="verdict {log.winner}"><b>{log.winner === 'draw' ? 'Neither side holds the field' : `${sw(log.winner)} wins`}</b> after {days} {days === 1 ? 'day' : 'days'}.
          Losses: <span class="ca">{men(log.losses.att)}</span> attacker, <span class="cd">{men(log.losses.def)}</span> defender.
          {#each log.notes.filter(n => !n.startsWith('Bombard')) as n}<i>{n}.</i> {/each}</div>
      {/if}
      {#each feed as f (f.d)}<p class:old={!done && f.d !== day}><span class="dn">Day {f.d}</span>{#each f.e as e, k}{#if k}<i class="sep">·</i>{/if}{@html e}{/each}</p>{/each}
    </div>

    <div class="ctl">
      <button class="play" onclick={toggle} title="Space">{done ? '↻ Replay' : playing ? '❚❚ Pause' : '▶ Play'}</button>
      <input type="range" min="0" max={days} bind:value={day} oninput={() => playing = false} aria-label="Day">
      <div class="spd">{#each [1, 2, 4] as s}<button class:on={speed === s} onclick={() => speed = s}>{s}×</button>{/each}</div>
      <button class="again" onclick={onagain} title="Roll the dice again: a new battle with the same armies">Fight again</button>
    </div>
    <p class="fine">One possible outcome of the rolls, played out from the same estimate as the odds above. Dead and routed regiments stay on the field in red.</p>
  </div>
</div>

<style>
  .back { position: fixed; inset: 0; z-index: 30; display: grid; place-items: start center; overflow-y: auto; padding: 4vh 16px; background: #05070bd9; backdrop-filter: blur(3px); animation: fade .25s; }
  @keyframes fade { from { opacity: 0; } }
  .th { width: min(1180px, 100%); border: 1px solid var(--frame); border-radius: 3px; box-shadow: 0 0 0 1px #000, 0 12px 48px #000c; padding: 0 0 12px;
    background: radial-gradient(ellipse at 50% 0, #26303f 0, #121820 70%); }
  .top { display: flex; align-items: center; gap: 14px; padding: 9px 14px; border-bottom: 1px solid var(--frame); background: linear-gradient(90deg, #3d3320, #1b232e 70%); }
  .top h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 17px; letter-spacing: 3px; text-transform: uppercase; color: var(--gold); text-shadow: 0 1px 2px #000; }
  .where { color: var(--dim); font-style: italic; font-size: 13px; }
  .phase { margin-left: auto; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; color: var(--gold); }
  .close { cursor: pointer; font: inherit; color: var(--dim); background: none; border: 1px solid transparent; border-radius: 3px; padding: 0 8px; }
  .close:hover { color: var(--text); border-color: var(--frame); }

  .score { display: grid; grid-template-columns: minmax(0, 1fr) 76px minmax(0, 1fr); gap: 14px; align-items: center; padding: 12px 16px 4px; }
  .sc { --c: var(--in); display: flex; flex-direction: column; gap: 4px; }
  .sc.def { --c: var(--pop); text-align: right; }
  .nm { display: flex; justify-content: space-between; align-items: baseline; }
  .sc.def .nm { flex-direction: row-reverse; }
  .nm span { font-size: 12px; letter-spacing: 2px; text-transform: uppercase; color: var(--c); }
  .nm b { font-size: 22px; font-variant-numeric: tabular-nums; color: var(--text); }
  .nm small { font-size: 12px; font-weight: 400; color: var(--dim); }
  .trk { height: 12px; border: 1px solid #000; outline: 1px solid var(--frame); border-radius: 2px; background: #0d1117; overflow: hidden; display: flex; }
  .sc.def .trk { justify-content: flex-end; }
  .trk .fill { display: block; height: 100%; background: linear-gradient(color-mix(in srgb, var(--c) 70%, #fff), color-mix(in srgb, var(--c) 70%, #000)); transition: width calc(1100ms / var(--spd, 1)) cubic-bezier(.3, .7, .3, 1); }
  .trk.m { height: 6px; outline-width: 0; border-color: #0008; }
  .trk.m .fill { background: color-mix(in srgb, var(--c) 55%, #8a8a8a); }
  .sub { display: flex; gap: 12px; font-size: 11.5px; color: var(--dim); font-variant-numeric: tabular-nums; }
  .sc.def .sub { justify-content: flex-end; }
  .dayc { display: flex; flex-direction: column; align-items: center; line-height: 1.1; }
  .dayc b { font-size: 34px; color: var(--gold); text-shadow: 0 1px 3px #000; font-variant-numeric: tabular-nums; }
  .dayc span { font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; color: var(--dim); }

  .field { display: flex; flex-direction: column; gap: 6px; margin: 10px 16px 0; padding: 10px 8px; border: 1px solid var(--line); border-radius: 3px;
    background: repeating-linear-gradient(90deg, #ffffff05 0 2px, transparent 2px 6px), linear-gradient(#1c2430, #151b24); box-shadow: inset 0 0 24px #0009; }
  .ln { display: grid; grid-template-columns: minmax(0, 1fr) 30px minmax(0, 1fr); align-items: center; min-height: calc(var(--t) + 10px); }
  .cell { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
  .cell.att { justify-content: flex-end; } .cell.def { justify-content: flex-start; }
  .cell em { font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; color: var(--dim); opacity: .7; margin: 0 6px; }
  .mid { display: grid; place-items: center; height: 100%; }
  .mid span { width: 2px; height: calc(var(--t, 40px) * .8); background: linear-gradient(transparent, #8a6d3b88, transparent); transition: .4s; }
  .mid.hot span { background: linear-gradient(transparent, #ff6a4aaa, transparent); box-shadow: 0 0 10px #ff6a4a88; animation: clash .5s infinite alternate; }
  @keyframes clash { to { opacity: .45; } }
  .rsv { border-top: 1px dashed var(--line); padding-top: 6px; margin-top: 2px; }

  .tk { --c: var(--in); position: relative; width: var(--t); height: var(--t); flex: none; border: 1px solid #000; outline: 1px solid #3a3426; border-radius: 3px; overflow: hidden; background: #0d1117;
    transition: opacity .4s, outline-color .4s, box-shadow .4s, transform .3s; }
  .tk.def { --c: var(--pop); }
  .tk.res { opacity: .55; }
  .tk.eng { outline-color: var(--c); box-shadow: 0 0 8px color-mix(in srgb, var(--c) 55%, transparent); }
  .tk img { display: block; width: 100%; height: 100%; object-fit: cover; transition: filter .5s; }
  .tk.def img { transform: scaleX(-1); }  /* face the enemy */
  .tk .red { position: absolute; inset: 0; background: #e0201a; mix-blend-mode: multiply; opacity: var(--red); transition: opacity calc(1100ms / var(--spd, 1)); }
  .tk.dead { opacity: .9; outline-color: #7a1713; transform: scale(.94); }
  .tk.dead img { filter: grayscale(.5) brightness(.75); }
  .tk.dead .red { background: #c1150f; mix-blend-mode: normal; opacity: .72; }
  .x { position: absolute; inset: 0; display: grid; place-items: center; font-size: calc(var(--t) * .5); color: #ffd9d0; text-shadow: 0 1px 3px #000; }
  .bar { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: #000a; }
  .bar.thin { bottom: 4px; height: 2px; }
  .bar b { display: block; height: 100%; transition: width calc(1100ms / var(--spd, 1)); }
  .men { background: #8fd16f; } .mor { background: #e6cf7a; }

  .feed { margin: 10px 16px 0; min-height: 4.6em; font-size: 13px; }
  .feed p { margin: 2px 0; transition: opacity .3s; } .feed p.old { opacity: .55; }
  .sep { margin: 0 8px; color: var(--dim); font-style: normal; }
  .dn { display: inline-block; min-width: 3.8em; color: var(--gold); font-variant: small-caps; letter-spacing: .5px; }
  .verdict { padding: 6px 10px; margin-bottom: 4px; border: 1px solid var(--frame); border-left-width: 3px; background: #0d1117aa; animation: fade .5s; }
  .verdict.att { border-left-color: var(--in); } .verdict.def { border-left-color: var(--pop); }
  .verdict b { font-size: 15px; color: var(--gold); } .verdict i { color: var(--dim); }
  .feed :global(.ca), .verdict .ca { color: var(--in); } .feed :global(.cd), .verdict .cd { color: var(--pop); }

  .ctl { display: flex; align-items: center; gap: 12px; margin: 10px 16px 0; }
  .ctl button { cursor: pointer; font: inherit; font-size: 13px; color: var(--text); background: #0d1117; border: 1px solid var(--frame); border-radius: 3px; padding: 3px 12px; }
  .ctl button:hover { border-color: var(--frame-hi); color: var(--gold); }
  .play { min-width: 92px; }
  .ctl input { flex: 1; accent-color: var(--frame-hi); }
  .spd { display: flex; } .spd button { border-radius: 0; padding: 3px 9px; margin-left: -1px; }
  .spd button:first-child { border-radius: 3px 0 0 3px; margin: 0; } .spd button:last-child { border-radius: 0 3px 3px 0; }
  .spd button.on { background: #3d3320; color: var(--gold); border-color: var(--frame-hi); position: relative; }
  .again { background: linear-gradient(#6b5426, #3b2c10) !important; color: var(--gold) !important; }
  .fine { margin: 8px 16px 0; font-size: 11.5px; color: var(--dim); font-style: italic; }
  @media (max-width: 700px) { .score { grid-template-columns: 1fr; } .dayc { flex-direction: row; gap: 6px; justify-content: center; } .ctl { flex-wrap: wrap; } }
</style>
