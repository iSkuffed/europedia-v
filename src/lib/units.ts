// Contract between units.py (public/units.json), the battle engine (battle.ts) and the Units page (Units.svelte).
// Stat names follow the game's unit_types fields; every value is the RESOLVED total (copy_from chain + category, additive).
import type { WhoItem } from './fit';

export type Cat = 'heavy_infantry' | 'light_infantry' | 'heavy_cavalry' | 'light_cavalry' | 'artillery' | 'auxiliary';

export interface Unit {
  id: string; name: string; desc?: string;
  cat: Cat; age: number;            // 1..6
  levy: boolean; buildable: boolean;
  str: number;                      // max_strength, thousands of men (0.5 = 500)
  cp: number;                       // combat_power
  init: number;                     // initiative
  speed: number;                    // combat_speed
  front: number;                    // frontage
  flank: number;                    // flanking_ability
  secure: number;                   // secure_flanks_defense
  move: number;                     // movement_speed
  sdd: number; sdt: number;         // strength_damage_done / _taken modifiers (+0.1 = +10%)
  mdd: number; mdt: number;         // morale_damage_done / _taken modifiers
  taken: number;                    // category damage_taken multiplier (infantry 1, cavalry 0.3, artillery/auxiliary 1.25)
  bombard?: number;                 // bombard_efficiency, artillery only
  terrain: Record<string, number>;  // `combat` block: topography / vegetation / 'river' id -> damage-done modifier
  combinedArms: boolean;            // false for exclude_from_combined_arms (auxiliary)
  upgrades?: string;                // upgrades_to
  who: WhoItem[]; whoText: string;  // country_potential etc., for fits(); [] = everyone
  unlock?: { id: string; name: string }[];  // advances that unlock it (unlock_unit / unlock_levy)
  unique: boolean;                  // not one of the generic 2_unlocked_through_tech line / age templates
  icon?: string;                    // public/icons/units/<icon>.webp (art picked the way the game's unit_illustrations do)
}

export interface Terrain { id: string; name: string; dice: number; front: number }  // dice = `defender` (attacker's dice penalty), front = local_frontage_allowed

export interface Trait { id: string; name: string; kind: 'general' | 'ruler'; mods: Record<string, number> }  // traits that touch combat, modifier key -> value

export interface UnitsData {
  units: Unit[];                    // land units only, templates excluded (hide = yes / pure bases)
  topography: Terrain[]; vegetation: Terrain[];
  ranks: { id: string; name: string; front: number }[];  // location rank frontage (rural 0, town -1, city -2, megalopolis -3)
  baseFrontage: number;             // location_base_values local_frontage_allowed (10)
  defines: Record<string, number>;  // NCombat.* plus NUnit.LAND_MORALE, MIN_FRONTAGE_AFTER_TERRAIN; verbatim define names
  traits: Trait[];
  ageMods: Record<number, Record<string, number>>;  // generic (everyone's) advances, cumulative up to and including that age: modifier key -> total
  focusMods: Record<'adm' | 'dip' | 'mil', Record<number, Record<string, number>>>;  // the same, for each age focus's otherwise-generic advances (for = adm/dip/mil), cumulative
  general: Record<'adm' | 'dip' | 'mil', Record<string, number>>;  // per ability point, from static_modifiers/character.txt
  levyMods: Record<string, number>; regularMods: Record<string, number>;  // is_army_levy / is_army_regular static modifiers
  base: Record<string, number>;     // country auto_modifiers: military_tactics, combined_* , land_morale_recovery ...
}

let cache: Promise<UnitsData> | undefined;
export const loadUnits = (): Promise<UnitsData> => cache ??= fetch('units.json').then(r => r.json());

// ---- battle engine API (implemented in battle.ts) -----------------------------------------------------------------
export interface General { adm: number; dip: number; mil: number; traits: string[] }  // abilities 0..100
export interface SideInput {
  regs: { unit: string; n: number }[];  // unit id, number of regiments
  general: General | null;
  // country-level modifiers; the UI pre-fills them from an age (ageMods) and lets the user edit
  discipline: number;               // +0.05 = +5%
  tactics: number;                  // military_tactics (base 1)
  moraleFlat: number;               // land_morale added to NUnit.LAND_MORALE
  moraleMod: number;                // land_morale_modifier (tradition, war exhaustion, general dip folded in by the engine)
  experience: number;               // 0..100
  levyEff: number;                  // levy_combat_efficiency_modifier
  initiativeMod: number; speedMod: number; frontageMod: number;
  combinedPerType: number;          // combined_bonus_per_type
  catPower: Partial<Record<Cat, number>>;  // army_<cat>_power
  armyTradition: number;            // 0..100
  formation: 'balanced_army' | 'cav_inf_cav';
}
export interface BattleInput {
  att: SideInput; def: SideInput;
  topography: string; vegetation: string; rank: string;
  river: boolean; strait: boolean; landing: boolean;
  dice: 'random' | 'fixed'; fixed?: { att: number; def: number };  // fixed roll 0..9
  seed?: number;
}
export interface SideState { men: number; morale: number; maxMorale: number; front: number; reserve: number; broken: number }  // men in units, morale as average over living regiments
// Per-regiment replay data for the battle animation, in each side's own order (strongest first), so index i is the same regiment in every frame.
export interface RegInfo { unit: string; max: number; maxMorale: number }
export type RegState = [men: number, morale: number, sec: number, flags: number]  // sec: lane 0..2 (faces the enemy's lane of the same number), 3 = reserve; flags: 1 engaged, 2 broken or routed
export interface BattleLog {
  winner: 'att' | 'def' | 'draw'; days: number;
  regs: { att: RegInfo[]; def: RegInfo[] };
  frames: { att: RegState[]; def: RegState[] }[];  // frames[0] is the start, frames[d] the end of day d (one more than daily)
  start: { att: SideState; def: SideState };
  daily: { att: SideState; def: SideState; diceAtt: number; diceDef: number }[];
  losses: { att: number; def: number };  // men
  notes: string[];                  // e.g. "Defender overrun on day 1 (10:1)"
}
export interface Summary {
  n: number; attWin: number; defWin: number; draw: number;  // fractions
  days: { avg: number; min: number; max: number };
  losses: { att: { avg: number; min: number; max: number }; def: { avg: number; min: number; max: number } };
  sample: BattleLog;                // one representative run for the day-by-day view
}
