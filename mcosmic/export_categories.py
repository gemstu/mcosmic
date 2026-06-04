# -*- coding: utf-8 -*-
"""Excel kategoriak exportalasa YAML-be."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from mcosmic.categories import DEFAULT_CATEGORIES_PATH, load_categories_from_excel


def export_to_yaml(xlsx_path: Path, output_path: Path) -> None:
    categories = load_categories_from_excel(xlsx_path)
    data = {dim: {str(k): v for k, v in sorted(cats.items())} for dim, cats in categories.maps.items()}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="M-COSMIC kategoriak exportalasa Excelbol YAML-be."
    )
    parser.add_argument("xlsx", type=Path, help="Forras Excel (mcosmic_sajat.xlsx)")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_CATEGORIES_PATH)
    args = parser.parse_args()
    if not args.xlsx.exists():
        raise SystemExit(f"A fajl nem talalhato: {args.xlsx}")
    export_to_yaml(args.xlsx, args.output)
    print(f"Exportalva: {args.output}")


if __name__ == "__main__":
    main()
