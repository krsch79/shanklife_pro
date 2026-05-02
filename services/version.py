from pathlib import Path


APP_VERSION = "1.6.0"


def get_changelog_entries():
    changelog_path = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
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
