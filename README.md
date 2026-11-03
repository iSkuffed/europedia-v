# Europedia V

**[Open the site: iskuffed.github.io/europedia-v](https://iskuffed.github.io/europedia-v/)**. It's free, runs in your browser, and has no ads and nothing to download.

A reference site for Europa Universalis V (EU5), built from the game's own files.

It covers:

- **Battle simulator.** Set up two land armies and run the battle, alongside a browser for every land unit.
- **Production chains.** What each good takes to make, which buildings produce and use it, and who buys it.
- **Pops.** What each pop type buys, where it works, and how pops grow and promote.
- **Nations.** Every country at the 1337 start: its population, raw goods, and what it can make.
- **Map.** Political, raw materials, settlements, population and development map modes, coloured to match the game.
- **Privileges and Research.** Estate privileges and the advances tree.

The site is in beta. Some data is missing or wrong, and some layouts break. If you spot something, open an issue.

## Running it locally

```sh
npm install
npm run dev
```

The data in `src/` and `public/` is already extracted, so that's all the site needs. To rebuild it from your own install, run `npm run data` (it first merges the base game and its DLC folders into `.game/`, so DLC content is included). The Python scripts look for the game in the default Steam path on Linux; pass a different path as the first argument to `build.py`. Development values come from a 1337 save file, which `build.py` skips with a warning if it can't find one.

## Disclaimer

Fan-made and not affiliated with Paradox Interactive. Game data and art are © Paradox Interactive.
