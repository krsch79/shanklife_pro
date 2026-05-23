from pathlib import Path


APP_VERSION = "1.8.33"


def _read_changelog_entries(filename):
    changelog_path = Path(__file__).resolve().parents[1] / filename
    if not changelog_path.exists():
        return []

    entries = []
    current = None
    for raw_line in changelog_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("## ["):
            if current:
                entries.append(current)
            heading = line.removeprefix("## ").strip()
            version_text, _, date_text = heading.partition(" - ")
            current = {
                "version": version_text.strip("[]"),
                "date": date_text.strip(),
                "changes": [],
            }
        elif current and line.startswith("- "):
            current["changes"].append(line[2:].strip())

    if current:
        entries.append(current)
    return entries


def get_changelog_entries():
    return _read_changelog_entries("CHANGELOG.md")


def _filtered_entries(entries, keep_change):
    filtered = []
    for entry in entries:
        changes = [change for change in entry["changes"] if keep_change(change)]
        if not changes:
            continue
        filtered.append({
            "version": entry["version"],
            "date": entry["date"],
            "changes": changes,
        })
    return filtered


def _is_balletour_change(change):
    return "balletour" in change.lower()


def get_shanklife_changelog_entries():
    return _filtered_entries(
        _read_changelog_entries("CHANGELOG.md"),
        lambda change: not _is_balletour_change(change),
    )


def get_balletour_changelog_entries():
    dedicated_entries = _read_changelog_entries("BALLETOUR_CHANGELOG.md")
    legacy_entries = _filtered_entries(
        _read_changelog_entries("CHANGELOG.md"),
        _is_balletour_change,
    )
    return dedicated_entries + legacy_entries
