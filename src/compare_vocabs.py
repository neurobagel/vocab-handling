"""
When a new version of a vocabulary list has been extracted using generate_vocab.py, 
this script can be used to identify differences in terms between versions and any duplicates in the new version.

This script assumes you have already run generate_vocab.py to create the vocab/ subdirectory and a new vocabulary list
"""
import json
from pathlib import Path
import pandas as pd
from collections import Counter
import argparse


def load_json(path: Path):
    """Load a JSON file as a dict"""
    with open(path, "r") as f:
        return json.load(f)


def save_json(data: dict, path: Path):
    """Save a dict to a JSON file"""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_concept_csv(filepath: Path) -> pd.DataFrame:
    """Load Athena concept table as a DataFrame"""
    return pd.read_csv(filepath, sep="\t", dtype=str, keep_default_na=False)


def flatten_terms(vocab_data: list[dict]) -> list[dict]:
    """Extract and flatten all terms from a list of vocabulary-group objects.

    generate_vocab.py outputs a list of vocab groups, each with a "terms" key.
    This helper concatenates all those term lists into a single flat list of
    {"id": ..., "name": ...} dicts for use by downstream comparison functions.
    """
    terms = []
    for vocab_group in vocab_data:
        terms.extend(vocab_group.get("terms", []))
    return terms


def get_diff_terms(old_terms: list[dict], new_terms: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Classify differences between two flat term lists by ID.

    Returns:
        deleted: terms whose ID exists only in old_terms (true removals)
        added:   terms whose ID exists only in new_terms (true additions)
        renamed: terms whose ID exists in both but with a different name
    """
    old_by_id = {term["id"]: term["name"] for term in old_terms}
    new_by_id = {term["id"]: term["name"] for term in new_terms}

    old_ids = set(old_by_id)
    new_ids = set(new_by_id)

    deleted = [{"id": id_, "name": old_by_id[id_]} for id_ in sorted(old_ids - new_ids)]
    added   = [{"id": id_, "name": new_by_id[id_]} for id_ in sorted(new_ids - old_ids)]
    renamed = [
        {"id": id_, "old_name": old_by_id[id_], "new_name": new_by_id[id_]}
        for id_ in sorted(old_ids & new_ids)
        if old_by_id[id_] != new_by_id[id_]
    ]

    print(f"Terms only in old (deleted):                   {len(deleted)}")
    print(f"Terms only in new (added):                     {len(added)}")
    print(f"Terms in both but with different name (renamed): {len(renamed)}")
    return deleted, added, renamed


def get_diff_terms_as_table(diff_terms: list[dict]) -> pd.DataFrame:
    """Return a DataFrame of the different terms with additional info about concept validity.

    Terms whose IDs have no namespace prefix (e.g. ncit extension terms like "C94342")
    are included in the output but skipped during the CONCEPT.csv validity lookup since
    that table only covers SNOMED/Athena concepts.
    """
    df = pd.DataFrame(diff_terms)
    # Extract concept_code from prefixed IDs (e.g. "snomed:123456" -> "123456").
    # Terms without a ":" (e.g. bare ncit IDs) will produce NaN here.
    df["concept_code"] = df["id"].where(~df["id"].str.contains(":"), other=None)
    df.loc[df["id"].str.contains(":"), "concept_code"] = df.loc[df["id"].str.contains(":"), "id"].str.split(":").str[1]

    concepts = load_concept_csv(Path(__file__).parents[1] / "data/CONCEPT.csv")
    concepts_validity_info = concepts[["concept_code", "valid_end_date", "invalid_reason"]]

    df_validity_info = df.merge(concepts_validity_info, on="concept_code", how="left")
    df_validity_info.drop(columns=["concept_code"], inplace=True)

    return df_validity_info


def get_duplicates(new_terms: list[dict]) -> dict:
    """Return a dict of label duplicates in the new terms, with values being the number of occurrences."""
    terms_dict = {
        term["id"]: term["name"] for term in new_terms
    }
    name_duplicates = {name: count for name, count in Counter(terms_dict.values()).items() if count > 1}
    print("Number of labels with duplicates in the new terms: ", len(name_duplicates))
    return name_duplicates


def main(old_terms_path: Path, new_terms_path: Path, output_dir: Path):
    old_terms = flatten_terms(load_json(old_terms_path))
    new_terms = flatten_terms(load_json(new_terms_path))

    print("Number of terms in the old terms list: ", len(old_terms))
    print("Number of terms in the new terms list: ", len(new_terms))

    deleted, added, renamed = get_diff_terms(old_terms, new_terms)
    deleted_df = get_diff_terms_as_table(deleted)
    new_term_duplicates = get_duplicates(new_terms)

    if deleted:
        save_json(deleted, output_dir / "deleted_terms.json")
        deleted_df.to_csv(output_dir / "deleted_terms.tsv", sep="\t", index=False)

    if added:
        save_json(added, output_dir / "added_terms.json")

    if renamed:
        save_json(renamed, output_dir / "renamed_terms.json")

    if new_term_duplicates:
        save_json(new_term_duplicates, output_dir / "new_term_duplicates.json")


if __name__ == "__main__":
    VOCAB_DIR = Path(__file__).parents[1] / "vocab"

    parser = argparse.ArgumentParser(description="Compare two versions of a list of vocabulary terms")
    parser.add_argument("--old-terms", required=True, help="Path to the old vocabulary JSON file")
    parser.add_argument("--new-terms", required=True, help="Path to the new vocabulary JSON file")
    parser.add_argument("--output-dir", default=VOCAB_DIR, help="Directory for comparison output files.")

    args = parser.parse_args()

    main(old_terms_path=Path(args.old_terms), new_terms_path=Path(args.new_terms), output_dir=Path(args.output_dir))
