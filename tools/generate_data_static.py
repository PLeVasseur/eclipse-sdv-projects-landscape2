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


def load_static_categories(path: Path) -> List[Dict[str, Any]]:
    """Load static category definitions from a YAML file.

    The file must contain a mapping with a top‑level `categories` key. Each
    category entry should define `name`, `subcategories` and `items` as
    illustrated in `static_categories.yml`.

    Returns the list of categories.
    """
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("categories", [])


def download_logo(url: str, dest: Path) -> str:
    """Download a logo from a URL and save it into dest.

    Returns the file name of the saved logo. On failure, returns the
    placeholder file name. The file is saved in ``dest``.
    """
    try:
        file_name = url.split("/")[-1].split("?")[0]
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        file_path = dest / file_name
        with file_path.open("wb") as f:
            f.write(response.content)
        return file_name
    except Exception:
        return "placeholder.svg"


def build_landscape_from_static(
    projects: List[Dict[str, Any]],
    static_categories: List[Dict[str, Any]],
    logo_dir: Path | None = None,
) -> Dict[str, Any]:
    """Build landscape data using a static category mapping.

    Projects are looked up by name according to the items lists in the
    supplied `static_categories`. Any project not found in the mapping
    will be placed into a fallback "Misc" subcategory under an
    automatically created "Unmapped" category.

    If ``logo_dir`` is provided, logos are downloaded into this directory
    and only the file name is referenced in the YAML. Otherwise, full
    URLs or the placeholder value are used.
    """
    # Prepare lookup of projects by name
    projects_by_name: Dict[str, Dict[str, Any]] = {p.get("name"): p for p in projects}
    assigned: set[str] = set()

    # Ensure logo directory exists if specified
    if logo_dir is not None:
        logo_dir.mkdir(parents=True, exist_ok=True)

    output_categories: List[Dict[str, Any]] = []

    def build_item(project: Dict[str, Any]) -> Dict[str, Any]:
        """Construct a landscape item record from project data."""
        item: Dict[str, Any] = {
            "name": project.get("name"),
            "description": project.get("summary"),
            "homepage_url": project.get("url"),
        }
        state = project.get("state")
        if state:
            item["project"] = state
        repos = project.get("github_repos") or []
        if repos:
            repo_url = repos[0].get("url")
            if repo_url:
                item["repo_url"] = repo_url
        logo_url = project.get("logo")
        if logo_dir is not None and logo_url:
            file_name = download_logo(logo_url, logo_dir)
            item["logo"] = file_name
        else:
            if logo_url:
                item["logo"] = logo_url
            else:
                item["logo"] = "placeholder.svg"
        return item

    # Build categories and subcategories according to static mapping
    for cat in static_categories:
        cat_name: str = cat.get("name", "")
        new_cat: Dict[str, Any] = {"name": cat_name, "subcategories": []}
        for sub in cat.get("subcategories", []):
            sub_name: str = sub.get("name", "")
            new_sub: Dict[str, Any] = {"name": sub_name, "items": []}
            for proj_name in sub.get("items", []):
                proj_data = projects_by_name.get(proj_name)
                if proj_data:
                    new_sub["items"].append(build_item(proj_data))
                    assigned.add(proj_name)
            new_cat["subcategories"].append(new_sub)
        output_categories.append(new_cat)

    # Handle projects that were not assigned to any static category
    unassigned_items: List[Dict[str, Any]] = []
    for proj_name, proj_data in projects_by_name.items():
        if proj_name not in assigned:
            unassigned_items.append(build_item(proj_data))

    if unassigned_items:
        misc_category = {
            "name": "Unmapped",
            "subcategories": [
                {
                    "name": "Misc",
                    "items": unassigned_items,
                }
            ],
        }
        output_categories.append(misc_category)

    return {"categories": output_categories}


def build_landscape_from_dynamic(
    projects: List[Dict[str, Any]],
    logo_dir: Path | None = None,
) -> Dict[str, Any]:
    """Fallback dynamic grouping using the project's 'category' field.

    This function replicates the original behaviour of grouping projects by
    their `category` field. Each project may define its category as
    "Parent / Subcategory"; if no slash is present, the project is
    placed under a subcategory named "Misc". Projects lacking a
    category are placed under "Unknown/Misc".

    If ``logo_dir`` is provided, logo URLs are downloaded into this
    directory and the ``logo`` field references only the file name.
    Otherwise, the full URL or placeholder is used.
    """
    categories: Dict[str, Dict[str, Any]] = {}

    # Ensure logo directory exists if specified
    if logo_dir is not None:
        logo_dir.mkdir(parents=True, exist_ok=True)

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
            # Download logo and use only the file name in YAML
            file_name = download_logo(logo_url, logo_dir)
            item["logo"] = file_name
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
    parser.add_argument(
        "--categories",
        default="static_categories.yml",
        help=(
            "Path to a YAML file defining static categories. If provided, the script"
            " will organise projects according to this file. If not present,"
            " projects are grouped using their 'category' field."
        ),
    )
    args = parser.parse_args()

    # Load projects
    if args.input:
        projects = load_projects_from_file(Path(args.input))
    else:
        projects = fetch_projects_from_api()

    # Download logos into a local 'logos' directory and reference them in YAML
    logo_dir = Path("logos")
    # If a categories file exists, load it; otherwise use dynamic grouping
    categories_path = Path(args.categories)
    if categories_path.exists():
        static_categories = load_static_categories(categories_path)
        landscape_data = build_landscape_from_static(
            projects, static_categories, logo_dir=logo_dir
        )
    else:
        # Fall back to dynamic grouping if no categories file is provided
        landscape_data = build_landscape_from_dynamic(
            projects, logo_dir=logo_dir
        )

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
