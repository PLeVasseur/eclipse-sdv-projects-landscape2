"""
generate_data.py
================

This script reads project data from the Eclipse SDV API or from a local
JSON file and generates a `data.yml` file in the Landscape2 configuration
format. The generated YAML can then be used as input for the
`PLeVasseur/eclipse‑sdv‑projects‑landscape2` repository.

Usage::

    python generate_data.py --input projects.json --output data.yml

If no input JSON is provided, the script attempts to fetch the data
directly from the API (`https://projects.eclipse.org/api/projects?working_group=sdv&pagesize=90000`).

The script groups projects according to the `category` field in the
JSON data. If the category follows the pattern ``A / B`` then ``A`` is
used as the category and ``B`` as the subcategory. Fields that are not
present in the input are omitted.
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


def build_landscape_data(
    projects: List[Dict[str, Any]], logo_dir: Path | None = None
) -> Dict[str, Any]:
    """Transform project data into Landscape2 YAML structure.

    The resulting structure contains top‑level categories, each with
    subcategories and items. The ``category`` field of each project is
    split on ``/`` to determine category and subcategory names.

    If ``logo_dir`` is provided, logo URLs are downloaded into this directory
    and the ``logo`` field references the downloaded file. Otherwise, the
    original URL is used or a placeholder if no URL exists.
    """
    categories: Dict[str, Dict[str, Any]] = {}

    # Ensure logo directory exists if specified
    if logo_dir is not None:
        logo_dir.mkdir(parents=True, exist_ok=True)

    def download_logo(url: str, dest: Path) -> str:
        """Download a logo from a URL and save it into dest.

        Returns the path to the saved file. On failure, returns a placeholder name.
        """
        try:
            # Use last segment of URL as filename, strip query parameters
            file_name = url.split("/")[-1].split("?")[0]
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            file_path = dest / file_name
            with file_path.open("wb") as f:
                f.write(response.content)
            return str(file_path)
        except Exception:
            return str(dest / "placeholder.svg")

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

        # Map project state to the ``project`` field
        state = proj.get("state")
        if state:
            item["project"] = state

        # Add first GitHub repo URL if available
        repos = proj.get("github_repos") or []
        if repos:
            repo_url = repos[0].get("url")
            if repo_url:
                item["repo_url"] = repo_url

        # Handle logo
        logo_url = proj.get("logo")
        if logo_dir is not None and logo_url:
            # Download logo and store relative path
            path = download_logo(logo_url, logo_dir)
            # Try to make path relative to current working directory
            try:
                item["logo"] = str(Path(path).relative_to(Path.cwd()))
            except Exception:
                item["logo"] = path
        else:
            # Without download, keep full URL or fallback
            if logo_url:
                item["logo"] = logo_url
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
        help="Path to a local JSON file containing project data (optional)",
    )
    parser.add_argument(
        "--output",
        default="data.yml",
        help="Name of the YAML file to generate (default: data.yml)",
    )
    args = parser.parse_args()

    # Load projects
    if args.input:
        projects = load_projects_from_file(Path(args.input))
    else:
        projects = fetch_projects_from_api()

    # Download logos into a local 'logos' directory and reference them in YAML
    logo_dir = Path("logos")
    landscape_data = build_landscape_data(projects, logo_dir=logo_dir)

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