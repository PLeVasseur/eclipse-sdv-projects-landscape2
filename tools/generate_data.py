"""
generate_data.py
=================

Dieses Skript liest Projektdaten aus der Eclipse‑SDV‑API oder aus einer lokal
bereitgestellten JSON‑Datei und generiert daraus eine `data.yml` im Format
der Landscape‑2‑Konfiguration. Die YAML‑Datei kann anschließend als
Eingabe für das Repository
``PLeVasseur/eclipse‑sdv‑projects‑landscape2`` verwendet werden.

Verwendung:

```
python generate_data.py --input projects.json --output data.yml
```

Wird kein Eingabe‑JSON angegeben, versucht das Skript, die Daten direkt
von der API abzurufen (``https://projects.eclipse.org/api/projects?working_group=sdv&pagesize=90000``).

Das Skript gruppiert die Projekte nach der im JSON enthaltenen
``category``. Wenn die Kategorie den Muster ``A / B`` hat, wird
``A`` als Kategorie und ``B`` als Unterkategorie verwendet. Nicht
vorhandene Felder werden weggelassen.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

import requests
import yaml


API_URL = (
    "https://projects.eclipse.org/api/projects?working_group=sdv&pagesize=90000"
)


def fetch_projects_from_api() -> List[Dict[str, Any]]:
    """Fetch projects from the Eclipse SDV API.

    Returns a list of project dictionaries.
    """
    resp = requests.get(API_URL)
    resp.raise_for_status()
    return resp.json()


def load_projects_from_file(path: Path) -> List[Dict[str, Any]]:
    """Load projects from a local JSON file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_landscape_data(projects: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Transform project data into Landscape2 YAML structure.

    The resulting structure contains top‑level categories, each with
    subcategories and items. The ``category`` field of each project is
    split on ``/`` to determine category and subcategory names.
    """
    categories: Dict[str, Dict[str, Any]] = {}

    for proj in projects:
        # Determine category and subcategory names
        cat_str: str = proj.get("category", "Unknown")
        parts = [part.strip() for part in cat_str.split("/", maxsplit=1)]
        if len(parts) == 2:
            cat_name, subcat_name = parts
        else:
            cat_name = parts[0]
            subcat_name = "Misc"

        # Ensure category entry exists
        category = categories.setdefault(
            cat_name, {"name": cat_name, "subcategories": {}}
        )
        subcats = category["subcategories"]
        # Ensure subcategory entry exists
        subcat = subcats.setdefault(
            subcat_name, {"name": subcat_name, "items": []}
        )

        # Build item record
        item: Dict[str, Any] = {
            "name": proj.get("name"),
            "description": proj.get("summary"),
            "homepage_url": proj.get("url"),
        }
        # Map the project state (e.g. Incubating, Mature, Proposal) to the ``project`` field
        state = proj.get("state")
        if state:
            item["project"] = state

        # Use the first GitHub repo URL if available
        repos = proj.get("github_repos") or []
        if repos:
            repo_url = repos[0].get("url")
            if repo_url:
                item["repo_url"] = repo_url

        # Provide a logo file name for each item. Use the last part of the logo URL
        # if available; otherwise fall back to a placeholder file name. Many tools
        # expect a `logo` field to exist for every item.
        # Use the original logo URL if provided; otherwise fall back to a placeholder.
        # The Landscape2 format accepts a URL for the `logo` field. If you prefer
        # to download and rename logos, adjust this accordingly.
        logo = proj.get("logo")
        if logo:
            item["logo"] = logo  # use full URL from JSON
        else:
            item["logo"] = "placeholder.svg"

        # Append item to subcategory
        subcat["items"].append(item)

    # Convert nested dict of subcategories to list structure required by YAML
    category_list = []
    for cat in categories.values():
        subcat_list = []
        for subcat in cat["subcategories"].values():
            subcat_list.append(subcat)
        cat["subcategories"] = subcat_list
        category_list.append(cat)

    return {"categories": category_list}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate data.yml for landscape2")
    parser.add_argument(
        "--input",
        help="Pfad zu einer lokalen JSON‑Datei mit Projektdaten (optional)",
    )
    parser.add_argument(
        "--output",
        default="data.yml",
        help="Name der zu erzeugenden YAML‑Datei (default: data.yml)",
    )
    args = parser.parse_args()

    # Load projects
    if args.input:
        projects = load_projects_from_file(Path(args.input))
    else:
        projects = fetch_projects_from_api()

    landscape_data = build_landscape_data(projects)

    # Write YAML file
    out_path = Path(args.output)
    with out_path.open("w", encoding="utf-8") as f:
        yaml.dump(
            landscape_data,
            f,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    print(f"Generated {out_path}")


if __name__ == "__main__":
    main()
