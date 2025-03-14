"""
When a new version of a vocabulary list has been extracted using generate_vocab.py, 
this script can be used to identify differences in terms between versions and any duplicates in the new version.

This script assumes you have already run generate_vocab.py to create the vocab/ subdirectory and a new vocabulary list
"""
import json
from pathlib import Path
import pandas as pd
from collections import Counter


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
    

def get_diff_terms(old_terms: dict, new_terms: dict) -> tuple[list[dict]]:
    old_terms_unique = [term for term in old_terms if term not in new_terms]
    new_terms_unique = [term for term in new_terms if term not in old_terms]
    print("Number of terms unique to the old terms list: ", len(old_terms_unique))
    print("Number of terms unique to the new terms list: ", len(new_terms_unique))
    return old_terms_unique, new_terms_unique


def get_diff_terms_as_table(diff_terms: list[dict]) -> pd.DataFrame:
    """Return a DataFrame of the different terms with additional info about concept validity."""
    df = pd.DataFrame(diff_terms)
    # strip snomed: from the identifiers
    df["concept_code"] = df["identifier"].str.split(":").str[1]

    concepts = load_concept_csv(Path(__file__).parents[1] / "data/CONCEPT.csv")
    concepts_validity_info = concepts[["concept_code", "valid_end_date", "invalid_reason"]]

    df_validity_info = df.merge(concepts_validity_info, on="concept_code", how="left")
    df.drop(columns=["concept_code"], inplace=True)

    return df_validity_info


def get_duplicates(new_terms: list[dict]) -> dict:
    """Return a dict of label duplicates in the new terms, with values being the number of occurrences."""
    terms_dict = {
        term["identifier"]: term["label"] for term in new_terms
    }
    label_duplicates = {label: count for label, count in Counter(terms_dict.values()).items() if count > 1}
    print("Number of labels with duplicates in the new terms: ", len(label_duplicates))
    return label_duplicates


def main(vocab_dir: Path):
    # This assumes there is only one vocabulary JSON file per directory!
    old_terms = load_json(next((vocab_dir / "old").glob("*.json")))
    new_terms = load_json(next((vocab_dir / "new").glob("*.json")))

    old_terms_unique, new_terms_unique = get_diff_terms(old_terms, new_terms)
    old_terms_unique_df = get_diff_terms_as_table(old_terms_unique)
    new_term_duplicates = get_duplicates(new_terms)

    if old_terms_unique:
        save_json(old_terms_unique, vocab_dir / "old_terms_unique.json")
        old_terms_unique_df.to_csv(
            vocab_dir / "old_terms_unique.tsv", sep="\t", index=False
        )

    if new_terms_unique:
        save_json(new_terms_unique, vocab_dir / "new_terms_unique.json")

    if new_term_duplicates:
        save_json(new_term_duplicates, vocab_dir / "new_term_duplicates.json")


if __name__ == "__main__":
    VOCAB_DIR = Path(__file__).parents[1] / "vocab"

    main(vocab_dir=VOCAB_DIR)
