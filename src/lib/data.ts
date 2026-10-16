// Game data extracted by build.py (`npm run data`). These types mirror the JSON it writes;
// if build.py changes a field, change it here too and `npm run check` shows every use that breaks.
import raw from '../data.json';

export interface Recipe {
  id: string;
  in: Record<string, number>;  // good -> amount per building level
  cat: string;
  name: string;
  out?: string;  // absent for upkeep recipes
  amt?: number;
  age?: number;  // age this method unlocks in, if later than the building
  parts?: string[];  // methods combined from several slots (one per slot, run together)
}
export interface Good {
  name: string;
  cat: 'raw_material' | 'produced';
  method: string | null;  // RGO extraction method (raw materials)
  food: number | null;
  price: number;
  demand: Record<string, number>;     // pop type (or 'all' / 'upper') -> demand per pop
  demandMul: Record<string, number>;
  slave: boolean;
  cond?: GoodCond;  // where pop demand for it is scaled up or down
}
// condition -> place / severity -> demand multiplier
export interface GoodCond {
  winter?: Record<string, number>; climate?: Record<string, number>; topography?: Record<string, number>;
  continent?: Record<string, number>; sub_continent?: Record<string, number>; region?: Record<string, number>;
  only?: string[];  // demanded only in these areas
  disease?: number; literacy?: number; market_unavailability?: number;
}
export interface PopType {
  desc: string;
  estate: string | null;
  upper: boolean;
  cap: boolean;       // their number is limited by "Possible X" (desired pop) in a location
  power: number | null;  // estate power per pop
  tax: number | null;    // estate tax base per pop
  food: number;
  promoteTo: string[];
  promo: number | null;  // promotion factor
  migration: number | null;
  assim: number | null;  // assimilation / conversion factor
  literacy: [string, number | null][];  // what their literacy gives the location
  share: [string, number | null][];     // what their share of the population gives
}
export interface PopSource {
  kind: string; id: string; name?: string; mods: Record<string, number>; age?: number; tag?: string;
  by?: Trigger[];  // static modifiers: events / decisions that apply them (none = the game applies it itself)
  note?: string;   // static modifiers: the game files' comment on how it scales
}
export interface PopInfo {
  types: Record<string, PopType>;
  ranks: {id: string; name: string; mods: Record<string, number>; minPop: number | null}[];  // rural settlement -> megalopolis
  base: Record<string, number>;  // every location
  sources: PopSource[];  // buildings, advances, laws... that make room for pops or change promotion speed
  modNames: Record<string, string>;
  pct: string[];  // modifier keys the game shows as percentages
  food: Record<'FOOD_SURPLUS_POP_GROWTH' | 'FOOD_STORAGE_POP_GROWTH' | 'STARVING_ON_FOOD_DEMAND', number>;
  text: Record<'population_growth' | 'population_capacity', string>;  // the game's concept descriptions
}
export interface Building {
  name: string;
  cat: string;
  pop: string;
  obsolete: string | null;  // the building this one replaces
  recipes: Recipe[];
  build: string | null;  // goods_demand id for construction cost
  foreign: boolean;
  req: [string, string][];  // [kind, name]: Nation/Culture/Religion... restrictions
  event: boolean;  // only granted by events or decisions
  age: number;
}
export interface Unit {
  name: string;
  cat: string;
  hide: boolean;
  age: string | null;
  dem: Record<string, string>;  // maintenance/construction/repair -> goods_demand id
}
export interface Demand { cat: string; in: Record<string, number> }
export interface DemandRef { f: string; id: string; name: string }
// something that changes how much pops want a good: +pct (global_<good>_pop_demand) or x mul (culture / religion)
export interface DemandMod {
  kind: string;  // folder it comes from: age, government_reforms, cultures, religion_groups, modifier, industry_types...
  id: string;
  name: string;
  pct?: number;
  mul?: number;
  clergy?: boolean;  // multiplier applies to clergy pops only
  age?: number;
  side?: string;  // societal value side that gives it
  by?: Trigger[];  // for event modifiers: what applies them
}
export interface Trigger { kind: string; id: string; name: string; tag?: string }  // event / decision / on_action
export interface TempDemand extends Trigger { months: number | null; scale: number }
export interface Data {
  popInfo: PopInfo;
  demandMods: Record<string, DemandMod[]>;  // good ('*' = every good) -> modifiers
  tempDemand: Record<string, TempDemand[]>;  // goods_demand id -> events that add it to a market for a while
  ages: Record<string, string>;
  units: Record<string, Unit>;
  demandRefs: Record<string, DemandRef[]>;
  goods: Record<string, Good>;
  buildings: Record<string, Building>;
  demands: Record<string, Demand>;
  pops: Record<string, string>;
  cats: Record<string, string>;
  icons: Record<string, string[]>;  // icon kind -> ids that have a PNG in public/icons
}

export const DATA = raw as unknown as Data;
