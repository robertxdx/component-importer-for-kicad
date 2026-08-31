
# Usage

If you prefer the terminal, you don't need the desktop application at all.
The `kicad-importer` command drives the same import pipeline as the GUI application.
Download a ZIP, type one command, and the part is in your project library.

```
kicad-importer init [--library NAME] [--downloads PATH]
kicad-importer import [FILE] [--all|-a] [--delete|-d] [--interactive|-i] [--yes|-y] [--debug]
```

# Project workflow

A typical project session configuration looks like this:

```bash
cd ~/projects/my-board          # anywhere inside the KiCad project works
kicad-importer init --library MyBoard_Parts --downloads ~/Downloads   # once
kicad-importer import           # pick a ZIP, done
```

That's the whole workflow. The rest of this page explains what each piece
does and the handful of options you might want.

# Setting up a project: `kicad-importer init`

Every project needs a one-time `init` so the importer knows two things: which
library to put components into, and where you usually download ZIP files.

```bash
kicad-importer init --library MyBoard_Parts --downloads ~/Downloads
```

Run it anywhere inside your KiCad project. The command looks for the folder
containing your `.kicad_pro` file and drops a `.kicad-importer` file
next to it. That file is plain INI, and you can edit it by hand:

```ini
[kicad-importer]
library = MyBoard_Parts
downloads = /home/you/Downloads
```

- `library` is the name of the project library that imports go into. The
  importer creates `libraries/MyBoard_Parts.kicad_sym` and
  `libraries/MyBoard_Parts.pretty` under the project root and registers them
  in the project's library tables.
- `downloads` is optional. If set, `import` also searches this folder, so you
  can import straight from your browser's download directory without moving
  files around.

You can also change individual settings usingthe CLI. Just run `init` again with only the flag
you want to change - everything else is left alone:

```bash
kicad-importer init --downloads ~/parts-inbox   # library name stays as-is
```

Note:
 * `--downloads` understands `~`, is stored as an absolute path, and only warns (rather than failing) if the folder doesn't exist yet.
 *  If you run `init` somewhere that isn't inside a KiCad project (no `.kicad-importer` above you and no `.kicad_pro` to be found) it says so and exits.

# Importing parts: `kicad-importer import`

Once a project is initialised, you can run `import` from the project root or
any subfolder. 

The CLI walks up the directory tree until it finds the
`.kicad-importer` file, and that folder is treated as the project root.
### Import a specific ZIP

```bash
kicad-importer import ul_TPS631000DRLR.zip
```

You can pass filename. It is looked for first in the current directory, then in your
configured downloads folder. So right after downloading a part, this works
from anywhere in the project:

```bash
kicad-importer import ul_TPS631000DRLR.zip     # found in ~/Downloads
```

If the file isn't anywhere to be found, the CLI tells you exactly which
directories it searched and exits with status 1.

## Or just pick one with fuzzy finder

Run `import` with no argument and it gathers every ZIP from the current
directory and the downloads folder, then hands you a fuzzy finder:

```bash
kicad-importer import
```

If you have [`fzf`](https://github.com/junegunn/fzf) installed you get the full type-to-narrow experience. Without it, the CLI
falls back to a simple built-in picker: a numbered list you can filter by
typing a substring, or select by number. 

Press Enter on an empty line or Esc / Ctrl-C in fzf to cancel the opration.

## Import process

For each part, the importer:

1. reads the symbol name out of the ZIP to use as the part name,
2. merges the symbol into `libraries/<library>.kicad_sym`,
3. copies footprints into `libraries/<library>.pretty/` and 3D models into
   `libraries/3dmodels/`,
4. links the symbol to its footprint and repairs the footprint's 3D-model
   path (using `${KIPRJMOD}` so the project stays portable),
5. registers the library in the project's `sym-lib-table` and `fp-lib-table`
   if it isn't there yet,
6. keeps a copy of the original ZIP in `libraries/source_zips/`, and
7. validates the result and prints a summary.

## Re-importing a part that is already in the library

If the component is already in the library, the importer stops before touching
any files and asks what to do:

```
Importing ul_TPS631000DRLR.zip ...
  TPS631000DRLR already exists in the library. The Symbol has been modified since it was imported.
Overwrite? [y/N]
```

The first line always says the part already exists. When the importer can tell
that the copy in your library was edited since it was first imported, it adds a
sentence naming what changed: the Symbol, the Footprint, or both. It works this
out by comparing content fingerprints stored at import time against what is on
disk now, so cosmetic reformatting does not count as a change. If the import
metadata is missing or unreadable (for example a part imported by an older
version), it cannot prove the copy is untouched and reports both the Symbol and
Footprint as modified so you are never overwritten by surprise.

Answer `y` to overwrite the existing symbol, footprint and 3D model with the
ones from the ZIP. Anything else (the default) cancels that part and leaves it
exactly as it is. A cancelled part still counts as a success: the command exits
0 and, with `--delete`, the ZIP is kept rather than removed.

Pass `--yes` (or `-y`) to overwrite every existing part without asking:

```bash
kicad-importer import ul_TPS631000DRLR.zip --yes
```

When the command is run without a terminal (for example from a script or a
pipe) and `--yes` is not given, it never waits for input: it treats the answer
as "no", keeps the existing part, and prints a note. Use `--yes` to overwrite
non-interactively.

## Bulk imports: `--all`

The CLI supports bulk-import functionality using the `--all` flag. 
This is best suited when you want to import a bunch of ZIPs when creating a new project. 

Navigate with `cd` to the directory with your ZIPs and then run:

```bash
kicad-importer import --all
```

The CLI first takes a pass over every `*.zip` in the **current directory**
and checks whether it actually looks like a component archive (it
contains at least one KiCad symbol library or footprint). Random ZIPs that
happen to be lying around are listed as skipped and never touched. Then each
candidate is imported in turn, with a per-file `OK` or `FAILED` line and a
final report:

The exit code is 0 only if every candidate imported cleanly, so `--all` is
safe to use in scripts.

Parts that are already in the library are prompted for one at a time, just like
a single import. Add `--yes` to overwrite all of them without prompting, which
is what you usually want in a script:

```bash
kicad-importer import --all --yes
```

Append `--delete` to the import command to also delete the imported zips, so they are not
present in the next bulk import invocation.

```bash
kicad-importer import ul_TPS631000DRLR.zip --delete
kicad-importer import --all --delete
```

Cancelling an overwrite is not a failure, so it never blocks `--delete` for the
rest of the batch: a cancelled part simply keeps its own ZIP, while the parts
that did import are still deleted. A real import failure is different - it skips
the entire delete phase so nothing is lost.

## Interactive pin layout: `--interactive` / `-i`

Downloaded symbols often arrive with their pins in an awkward layout. Add
`--interactive` (or `-i`) to open a small terminal editor for each imported
symbol and reconstruct the pin placement before it is written to the library:

```bash
kicad-importer import ul_BQ28Z610DRZR.zip --interactive
```

The editor draws the symbol as an ASCII chip with pin names inside the body
edge and pin numbers outside. Pins on the top and bottom sides are drawn with
their names stacked vertically, mirroring how KiCad renders them.

- Arrow keys move the cursor between pins (the cursor pin is shown in yellow,
  with its edge marked by a solid block).
- `Space` selects the pin under the cursor (shown in red); arrow keys then move
  the pin: up/down (or left/right on the top/bottom sides) reorder it within its
  side and, past either end, carry it around the corner onto the neighbouring
  side. The arrow pointing into the body jumps the pin straight to the opposite
  side. `Space` again deselects.
- `S` inserts a blank spacer slot at the cursor; `d` deletes a blank (real pins
  are never deleted).
- `y` then `y` accepts and regenerates the symbol; `Esc` then `Enter` cancels
  and imports the symbol exactly as it was merged.

On accept, the body rectangle is auto-sized so no pin names collide, pins are
placed on the 2.54 mm grid with their connection points exactly on the body
edge, and the symbol's properties and footprint links are preserved. With
`--all`, the editor runs once per imported ZIP in turn.

# Quick reference

| I want to... | Run |
|---|---|
| Set up a project | `kicad-importer init --library MyParts --downloads ~/Downloads` |
| Change one setting later | `kicad-importer init --downloads <new-path>` |
| Import a downloaded part | `kicad-importer import <file.zip>` |
| Browse and pick a part | `kicad-importer import` |
| Import everything here | `kicad-importer import --all` |
| …and tidy up the ZIPs | `kicad-importer import --all --delete` |
| Overwrite an existing part without asking | `kicad-importer import <file.zip> --yes` |
| Rework pin layout on import | `kicad-importer import <file.zip> --interactive` |
