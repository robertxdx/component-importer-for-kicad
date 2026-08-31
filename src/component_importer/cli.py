# Command line interface for importing KiCad component ZIP files.
# This module is Qt-free and must never import any gui_* module except the
# Qt-free gui_config_manager helper used for part-name inference.

import argparse
import configparser
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

from component_importer.cad_zip_importer import check_existing_component
from component_importer.cad_zip_importer import import_cad_zip
from component_importer.file_discovery import iter_zip_files
from component_importer.gui_config_manager import infer_part_name_from_zip
from component_importer.import_summary import print_import_summary
from component_importer.import_validator import (
    print_validation_summary,
    validate_imported_part,
)
from component_importer.models import AssetType
from component_importer.symbol_style import SymbolStyle
from component_importer.zip_inspector import inspect_zip_contents


# Name of the per-project INI configuration file
CONFIG_FILENAME = ".kicad-importer"

# INI section holding the importer settings
CONFIG_SECTION = "kicad-importer"

# Per-ZIP outcome of attempt_import.
#   IMPORT_OK        the component was imported (eligible for --delete)
#   IMPORT_CANCELLED the user declined to overwrite an existing part; the ZIP is
#                    kept and never deleted, but this still counts as success
#   IMPORT_FAILED    the import raised an error
IMPORT_OK = "imported"
IMPORT_CANCELLED = "cancelled"
IMPORT_FAILED = "failed"


# Print an error message to stderr
def error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


# Print a warning message to stderr
def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


# Walk up from a directory to find the nearest .kicad-importer config file
def find_config_file(start: str | Path) -> Path | None:
    current = Path(start).resolve()

    for directory in [current, *current.parents]:
        candidate = directory / CONFIG_FILENAME

        if candidate.is_file():
            return candidate

    return None


# Walk up from a directory to find the nearest folder holding a .kicad_pro file
def find_kicad_pro_root(start: str | Path) -> Path | None:
    current = Path(start).resolve()

    for directory in [current, *current.parents]:
        if any(directory.glob("*.kicad_pro")):
            return directory

    return None


# Read the library and downloads values from a config file
def read_config(config_path: str | Path) -> dict:
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")

    if not parser.has_section(CONFIG_SECTION):
        return {}

    section = parser[CONFIG_SECTION]

    return {
        "library": section.get("library", "").strip(),
        "downloads": section.get("downloads", "").strip(),
    }


# Write the library and downloads values to a config file
def write_config(config_path: str | Path, library: str, downloads: str) -> None:
    parser = configparser.ConfigParser()
    parser[CONFIG_SECTION] = {}

    if library:
        parser[CONFIG_SECTION]["library"] = library

    if downloads:
        parser[CONFIG_SECTION]["downloads"] = downloads

    with open(config_path, "w", encoding="utf-8") as handle:
        parser.write(handle)


# Show a path relative to cwd when it lives under cwd, otherwise absolute
def display_path(path: str | Path, cwd: Path) -> str:
    resolved = Path(path).resolve()

    try:
        return str(resolved.relative_to(cwd.resolve()))
    except ValueError:
        return str(resolved)


# Report whether a ZIP holds at least one symbol library or footprint asset
def is_eligible_zip(zip_path: str | Path) -> bool:
    try:
        inspection = inspect_zip_contents(zip_path)
    except Exception:
        return False

    counts = inspection.get("asset_type_counts", {})

    return (
        counts.get(AssetType.SYMBOL_LIB.value, 0) > 0
        or counts.get(AssetType.FOOTPRINT.value, 0) > 0
    )


# Build a deduplicated, sorted list of ZIP files from several directories
def aggregate_zips(search_dirs: list[Path]) -> list[Path]:
    seen = set()
    result = []

    for directory in search_dirs:
        for zip_path in iter_zip_files(directory):
            key = zip_path.resolve()

            if key in seen:
                continue

            seen.add(key)
            result.append(zip_path)

    return sorted(result, key=lambda path: str(path).lower())


# Resolve an explicit file argument to a real ZIP file, or None if not found
def resolve_explicit_file(
    name: str,
    cwd: Path,
    search_dirs: list[Path],
) -> Path | None:
    given = Path(name)

    if given.is_absolute():
        return given if given.is_file() else _search_by_name(name, search_dirs)

    relative = cwd / given

    if relative.is_file():
        return relative

    return _search_by_name(name, search_dirs)


# Look for a bare filename inside each search directory
def _search_by_name(name: str, search_dirs: list[Path]) -> Path | None:
    filename = Path(name).name

    for directory in search_dirs:
        candidate = directory / filename

        if candidate.is_file():
            return candidate

    return None


# Run fzf over the display lines and return the selected line, or None
def run_fzf(display_lines: list[str]) -> str | None:
    proc = subprocess.run(
        ["fzf"],
        input="\n".join(display_lines),
        text=True,
        stdout=subprocess.PIPE,
    )

    # Exit 0 means a line was chosen; 130/1 mean the user cancelled
    if proc.returncode == 0:
        return proc.stdout.strip()

    return None


# Minimal stdlib picker used when fzf is not installed
def builtin_picker(candidates: list[Path], cwd: Path) -> Path | None:
    items = list(candidates)

    while True:
        print("Select a ZIP to import:")

        for index, candidate in enumerate(items, start=1):
            print(f"  {index}. {display_path(candidate, cwd)}")

        try:
            choice = input(
                "Enter number, or text to filter (empty to cancel): "
            ).strip()
        except EOFError:
            return None

        if not choice:
            return None

        if choice.isdigit():
            number = int(choice)

            if 1 <= number <= len(items):
                return items[number - 1]

            print("Invalid number.")
            continue

        matches = [
            candidate
            for candidate in candidates
            if choice.lower() in display_path(candidate, cwd).lower()
        ]

        if matches:
            items = matches
        else:
            print("No matches.")
            items = list(candidates)


# Present a fuzzy picker, preferring fzf and falling back to the builtin picker
def pick_zip_file(candidates: list[Path], cwd: Path) -> Path | None:
    if shutil.which("fzf"):
        display_map = {display_path(c, cwd): c for c in candidates}
        selected = run_fzf(list(display_map.keys()))

        if not selected:
            return None

        return display_map.get(selected)

    return builtin_picker(candidates, cwd)


# Ask the user whether to overwrite an existing part. Returns True to overwrite.
#
# --yes overwrites without asking. A non-interactive stdin never blocks: it is
# treated as "no" (keep the part) with a note, so scripts and pipelines do not
# hang waiting for input.
def confirm_overwrite(part_name: str, assume_yes: bool) -> bool:
    if assume_yes:
        print(f"  Overwriting {part_name} (--yes).")
        return True

    if not sys.stdin.isatty():
        warn(
            f"stdin is not a terminal; keeping {part_name} "
            f"(pass --yes to overwrite existing parts)"
        )
        return False

    try:
        answer = input("Overwrite? [y/N] ").strip().lower()
    except EOFError:
        return False

    return answer in ("y", "yes")


# Import a single ZIP, printing progress and returning an IMPORT_* status
def attempt_import(
    zip_path: Path,
    project_root: Path,
    library: str,
    debug: bool = False,
    show_summary: bool = True,
    interactive: bool = False,
    assume_yes: bool = False,
) -> str:
    print(f"Importing {zip_path.name} ...")

    try:
        part_name = infer_part_name_from_zip(zip_path)

        # Pre-check existence so the user can confirm an overwrite before any
        # files are touched. Uses the same Qt-free helper as the GUI modal.
        overwrite = False
        existing = check_existing_component(
            zip_path=zip_path,
            project_root=project_root,
            library_name=library,
            part_name=part_name,
        )

        if existing.get("already_exists"):
            print(f"  {existing['message']}")
            overwrite = confirm_overwrite(part_name, assume_yes)

            if not overwrite:
                print(f"  Cancelled: {part_name} left unchanged")
                return IMPORT_CANCELLED

        if interactive:
            # Reconstruct pin layouts interactively; an explicit formatting
            # strategy overrides symbol_style inside import_cad_zip.
            from component_importer.interactive_strategy import (
                InteractiveReconstructionStrategy,
            )

            result = import_cad_zip(
                zip_path,
                project_root,
                library,
                part_name,
                skip_existing_components=not overwrite,
                formatting_strategy=InteractiveReconstructionStrategy(),
            )
        else:
            result = import_cad_zip(
                zip_path,
                project_root,
                library,
                part_name,
                skip_existing_components=not overwrite,
                # Default KiCad-style formatting with theme-adaptive colors
                symbol_style=SymbolStyle(),
            )
    except Exception as exc:
        if debug:
            traceback.print_exc()

        error(f"{zip_path.name}: {exc}")
        print(f"  FAILED: {zip_path.name}")
        return IMPORT_FAILED

    # The pre-check normally handles existing parts; a skipped_existing result
    # here only happens on a race (the part appeared after the check). Report it
    # gracefully rather than treating it as an error.
    if result.get("skipped_existing"):
        print(f"  OK: {part_name} already in library, skipped")
        return IMPORT_OK

    validation = validate_imported_part(project_root, result, library)

    if show_summary:
        print()
        print_import_summary(result, part_name)
        print_validation_summary(validation)

    if not validation.get("passed", False):
        warn(f"validation reported issues for {part_name}")

    print(f"  OK: {part_name}")
    return IMPORT_OK


# Delete a source ZIP and report it
def delete_zip(zip_path: Path) -> None:
    try:
        zip_path.unlink()
        print(f"Deleted {zip_path.name}")
    except OSError as exc:
        warn(f"could not delete {zip_path.name}: {exc}")


# Handle the 'init' command
def cmd_init(args: argparse.Namespace, cwd: Path) -> int:
    cwd = cwd.resolve()
    config_path = find_config_file(cwd)

    if config_path is None:
        pro_root = find_kicad_pro_root(cwd)

        if pro_root is None:
            error("not inside a KiCad project (no .kicad_pro found)")
            return 1

        config_path = pro_root / CONFIG_FILENAME

    existing = read_config(config_path) if config_path.exists() else {}
    library = existing.get("library", "")
    downloads = existing.get("downloads", "")

    if args.library is not None:
        library = args.library.strip()

    if args.downloads is not None:
        expanded = Path(args.downloads).expanduser().resolve()
        downloads = str(expanded)

        if not expanded.exists():
            warn(f"downloads folder does not exist: {expanded}")

    if not library:
        error("first-time init requires --library")
        return 1

    write_config(config_path, library, downloads)

    print("Saved configuration:")
    print(f"  root:      {config_path.parent}")
    print(f"  library:   {library}")
    print(f"  downloads: {downloads or '(not set)'}")
    return 0


# Import every eligible ZIP in the current directory
def import_all(args: argparse.Namespace, cwd: Path, project_root: Path, library: str) -> int:
    zips = sorted(iter_zip_files(cwd), key=lambda path: str(path).lower())

    if not zips:
        error(f"no ZIP files found in {cwd}")
        return 1

    candidates = []
    skipped = []

    for zip_path in zips:
        if is_eligible_zip(zip_path):
            candidates.append(zip_path)
        else:
            skipped.append(zip_path)

    print("Candidate component ZIPs:")

    for zip_path in candidates:
        print(f"  {zip_path.name}")

    if not candidates:
        print("  (none)")

    if skipped:
        print("Skipped (no symbol or footprint assets):")

        for zip_path in skipped:
            print(f"  {zip_path.name}")

    print()

    if not candidates:
        error("no eligible component ZIPs to import")
        return 1

    results = []

    for zip_path in candidates:
        status = attempt_import(
            zip_path,
            project_root,
            library,
            debug=args.debug,
            show_summary=False,
            interactive=getattr(args, "interactive", False),
            assume_yes=getattr(args, "yes", False),
        )
        results.append((zip_path, status))

    imported = [zip_path for zip_path, status in results if status == IMPORT_OK]
    cancelled = [
        zip_path for zip_path, status in results if status == IMPORT_CANCELLED
    ]
    failures = [zip_path for zip_path, status in results if status == IMPORT_FAILED]

    print()
    print(
        f"Imported {len(imported)} of {len(candidates)} component ZIP(s)."
    )

    if cancelled:
        print(
            f"Kept {len(cancelled)} already-in-library ZIP(s) that were not "
            f"overwritten."
        )

    if args.delete:
        # A user-cancelled overwrite is not a failure, so it never blocks the
        # delete phase; it only excludes its own ZIP from deletion. A real
        # failure still skips deletion entirely so nothing is lost.
        if failures:
            print(
                f"{len(failures)} of {len(candidates)} imports failed "
                f"— skipping deletion of imported zips"
            )
        else:
            for zip_path, status in results:
                if status == IMPORT_OK:
                    delete_zip(zip_path)

    return 1 if failures else 0


# Handle the 'import' command
def cmd_import(args: argparse.Namespace, cwd: Path) -> int:
    cwd = cwd.resolve()
    config_path = find_config_file(cwd)

    if config_path is None:
        error(
            "no .kicad-importer found; run 'kicad-importer init' "
            "inside your KiCad project"
        )
        return 1

    project_root = config_path.parent
    config = read_config(config_path)
    library = config.get("library", "")

    if not library:
        error(
            "no library configured; run "
            "'kicad-importer init --library <name>'"
        )
        return 1

    downloads = config.get("downloads", "")
    search_dirs = [cwd]

    if downloads:
        downloads_dir = Path(downloads)

        if downloads_dir.exists() and downloads_dir.resolve() != cwd.resolve():
            search_dirs.append(downloads_dir)

    if args.all:
        return import_all(args, cwd, project_root, library)

    if args.file:
        target = resolve_explicit_file(args.file, cwd, search_dirs)

        if target is None:
            searched = ", ".join(str(directory) for directory in search_dirs)
            error(f"ZIP not found: {args.file} (searched: {searched})")
            return 1
    else:
        candidates = aggregate_zips(search_dirs)

        if not candidates:
            searched = ", ".join(str(directory) for directory in search_dirs)
            error(f"no ZIP files found (searched: {searched})")
            return 1

        target = pick_zip_file(candidates, cwd)

        if target is None:
            print("Nothing selected.")
            return 0

    status = attempt_import(
        target,
        project_root,
        library,
        debug=args.debug,
        interactive=getattr(args, "interactive", False),
        assume_yes=getattr(args, "yes", False),
    )

    if status == IMPORT_FAILED:
        return 1

    # A cancelled overwrite counts as success but keeps its ZIP in place
    if args.delete and status == IMPORT_OK:
        delete_zip(target)

    return 0


# Build the argument parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kicad-importer",
        description="Import KiCad component ZIP files from the command line.",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser(
        "init",
        help="Create or update the .kicad-importer project config.",
    )
    init_parser.add_argument(
        "--library",
        help="Library name to import components into.",
    )
    init_parser.add_argument(
        "--downloads",
        help="Optional downloads folder to search for ZIP files.",
    )

    import_parser = subparsers.add_parser(
        "import",
        help="Import a component ZIP into the project library.",
    )
    import_parser.add_argument(
        "file",
        nargs="?",
        help="ZIP file to import (path or filename). Omit to pick interactively.",
    )
    import_parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Import every eligible ZIP in the current directory.",
    )
    import_parser.add_argument(
        "--delete",
        "-d",
        action="store_true",
        help="Delete source ZIP(s) after a successful import.",
    )
    import_parser.add_argument(
        "--debug",
        action="store_true",
        help="Show full tracebacks on unexpected errors.",
    )
    import_parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Reconstruct each symbol's pin layout in an interactive editor.",
    )
    import_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Overwrite existing parts without prompting.",
    )

    return parser


# CLI entry point
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 2

    if args.command == "import" and args.all and args.file:
        parser.error("--all cannot be combined with a file argument")

    cwd = Path.cwd()

    if args.command == "init":
        return cmd_init(args, cwd)

    if args.command == "import":
        return cmd_import(args, cwd)

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
