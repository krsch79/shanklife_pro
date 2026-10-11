#!/usr/bin/env python3
"""Keep the static maintenance page available while the Flask port restarts.

Run as root on the Pi. Only vhosts that proxy to this app's exact local port
are modified, with timestamped backups and rollback if nginx validation fails.
"""
import argparse
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    root = str(Path(args.app_dir).resolve())
    if not re.fullmatch(r"/[A-Za-z0-9_/.-]+", root):
        raise SystemExit("Unsupported app directory")
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    changed = []
    plans = {}
    backups = Path("/var/backups/shanklife-nginx") / stamp
    for link in Path("/etc/nginx/sites-enabled").iterdir():
        path = link.resolve()
        original = path.read_text()
        if f"proxy_pass http://127.0.0.1:{args.port};" not in original:
            continue
        if "# shanklife-static-maintenance" in original:
            continue
        pattern = r"(?P<indent>[ \t]*)location / \{\n"
        matches = list(re.finditer(pattern, original))
        if len(matches) != 1:
            raise SystemExit("Maintenance setup needs exactly one root proxy location in " + link.name)
        match = matches[0]
        indent = match.group("indent")
        replacement = (indent + "# shanklife-static-maintenance\n" + indent + "error_page 503 =503 /__shanklife_maintenance.html;\n" + indent + "location = /__shanklife_maintenance.html {\n" + indent + "    internal;\n" + indent + "    alias " + root + "/static/maintenance.html;\n" + indent + "    add_header Cache-Control \"no-store\" always;\n" + indent + "}\n" + match.group(0) + indent + "    if (-f " + root + "/instance/maintenance.lock) { return 503; }\n")
        updated = original[:match.start()] + replacement + original[match.end():]
        plans[path] = updated
    if not plans:
        print("Static maintenance proxy already installed or no matching vhosts.")
        return
    try:
        backups.mkdir(parents=True, mode=0o700, exist_ok=True)
        # Preflight all vhosts before any write. Backup all before modifying one.
        for index, path in enumerate(plans):
            backup = backups / (str(index) + "-" + path.name)
            shutil.copy2(path, backup)
            changed.append((path, backup))
        for path, updated in plans.items():
            path.write_text(updated)
        subprocess.run(["/usr/sbin/nginx", "-t"], check=True)
        subprocess.run(["systemctl", "reload", "nginx"], check=True)
    except BaseException:
        for path, backup in changed:
            shutil.copy2(backup, path)
        subprocess.run(["/usr/sbin/nginx", "-t"], check=True)
        raise
    print("Static maintenance proxy installed for", len(changed), "vhosts; backups:", backups)


if __name__ == "__main__":
    main()
