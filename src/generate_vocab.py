import argparse
from pathlib import Path
import logging
import json

import pandas as pd
from rdflib import Graph, RDFS, Literal
import tqdm


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("generate_vocab")

# Athena concept IDs for parent concepts
# We will only include child terms of these.
# Attention: these are the Athena codes, not the SNOMED codes - , 435524
DIAGNOSIS_PARENT_CONCEPTS = [432586, 376106]
ASSESSMENT_PARENT_CONCEPTS = [4157120]
# Preamble for the vocabularies
DIAGNOSIS_PREAMBLE = {
    "namespace_prefix": "snomed",
    "namespace_url": "http://purl.bioontology.org/ontology/SNOMEDCT/",
    "vocabulary_name": "Neurobagel vocabulary of Disorder terms",
    "version": "1.0.0",
}
DIAGNOSIS_EXTENSION = {
    "namespace_prefix": "ncit",
    "namespace_url": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#",
    "vocabulary_name": "Neurobagel vocabulary of Disorder terms",
    "version": "1.0.0",
    "terms": [
      {
        "name": "Healthy Control",
        "id": "C94342"
      }
    ]
  }
ASSESSMENT_PREAMBLE = {
    "namespace_prefix": "snomed",
    "namespace_url": "http://purl.bioontology.org/ontology/SNOMEDCT/",
    "vocabulary_name": "Neurobagel vocabulary of Assessment terms",
    "version": "1.0.0",
}


def load_concept_relationships(filepath):
    """Load concept relationships and filter for direct hierarchical relationships"""
    log.info(f"Loading the {filepath}")
    df = pd.read_csv(filepath, sep='\t', usecols=['concept_id_1', 'concept_id_2', 'relationship_id'])
    return df[df['relationship_id'] == "Is a"]

def create_graph(df):
    """Save the parent-child relationships as triples to an rdflib Graph object to query over"""
    log.info("Creating the graph")
    graph = Graph()
    for index, row in tqdm.tqdm(df.iterrows(), total=df.shape[0], desc="Creating graph"):
        concept_id_1 = row['concept_id_1']
        concept_id_2 = row['concept_id_2']
        graph.add((Literal(concept_id_1), RDFS.subClassOf, Literal(concept_id_2)))
    return graph

def save_graph(graph, filepath):
    """Save the graph into a .ttl file so we don't have to rebuild it next time"""
    log.info(f"Saving the graph to {filepath}")
    graph.serialize(format="turtle", destination=filepath)
    
    
def load_graph(filepath):
    log.info(f"Loading the graph from {filepath}")
    graph = Graph()
    graph.parse(filepath)
    return graph


def run_query(graph, query):
    """Return ATHENA concept_ids for terms matching a query"""
    log.info("Running the query")
    query_results = graph.query(query)
    return [str(res[0]) for res in query_results]


def build_descendants_query(parent_concept_ids):
    """Build a SPARQL query that selects all descendants of one or more parent concepts.

    Uses rdfs:subClassOf* to include the parent concept itself and all transitive children.
    """
    union_blocks = "\n        UNION\n".join(
        f"        {{?child rdfs:subClassOf* {parent_id}}}" for parent_id in parent_concept_ids
    )
    return f"""
    SELECT ?child
    WHERE {{
{union_blocks}
    }}
    """


def load_concept_csv(filepath):
    """Load table for mapping an (Athena) concept_id to concept_code (equivalent to BioPortal term ID)"""
    log.info("Loading the CONCEPT.csv")
    return pd.read_csv(filepath, sep="\t", dtype=str, keep_default_na=False)


def filter_terms(df, concept_ids, domain_id=None):
    log.info("Filtering terms")
    domain_filter = "domain_id == 'Condition' and " if domain_id else ""
    # NOTE: The invalid_reason filter technically is unnecessary here since invalid concepts cannot be standard,
    # in OHDSI, but we include it here for reference.
    # See also https://ohdsi.github.io/TheBookOfOhdsi/StandardizedVocabularies.html#conceptLifeCycle
    return df.query(
        f"{domain_filter} standard_concept == 'S' and invalid_reason == '' and concept_id in @concept_ids"
    )


def structure_for_json(df, preamble, add_extension=None):
    log.info("Structuring dataframe for JSON output")
    df = df[['concept_code', 'concept_name']]
    df = df.rename(columns={'concept_code': 'id', 'concept_name': 'name'})
    df = df.reset_index(drop=True)
    df['id'] = 'snomed:' + df['id'].astype(str)

    out_json = [preamble]
    out_json[0]['terms'] = df.to_dict('records')

    if add_extension:
        log.info(f"Adding vocab extension")
        out_json.insert(0, add_extension)

    return out_json


def save_to_json(df, filepath):
    log.info(f"Saving to JSON file {filepath}")
    with open(filepath, 'w') as f:
        f.write(json.dumps(df, indent=2))
    
    
def main(concept_relationship_path, concept_csv_path, graph_path, out_json_path, mode):
    df_relationships = load_concept_relationships(concept_relationship_path)
    df_concepts = load_concept_csv(concept_csv_path)
    
    if graph_path.exists():
        graph = load_graph(graph_path)
    else:
        graph = create_graph(df_relationships)
        save_graph(graph, graph_path)
    
    if mode == "diagnosis":
        parent_concepts = DIAGNOSIS_PARENT_CONCEPTS
        preamble = DIAGNOSIS_PREAMBLE
    elif mode == "assessment":
        parent_concepts = ASSESSMENT_PARENT_CONCEPTS
        preamble = ASSESSMENT_PREAMBLE
    else:
        log.error(f"Invalid mode selected: {mode}")
        exit(1)

    query = build_descendants_query(parent_concepts)
    concept_ids = run_query(graph, query)
    terms_df = filter_terms(df_concepts, concept_ids,  domain_id="Condition" if mode == "diagnosis" else None)

    terms_dict = structure_for_json(terms_df, preamble, DIAGNOSIS_EXTENSION if mode == "diagnosis" else None)
    save_to_json(terms_dict, out_json_path)
    log.info("Done!")
    
    
if __name__ == "__main__":
    FILE_PATH = Path(__file__).parent.resolve()
    
    parser = argparse.ArgumentParser(description="Generate diagnosis or assessment terms JSON")
    parser.add_argument("--mode", required=True, choices=["diagnosis", "assessment"], help="Mode to run the script in: 'diagnosis' or 'assessment'")

    args = parser.parse_args()
    if args.mode == "diagnosis":
        out_json_path = FILE_PATH / "../vocab/diagnosis/diagnoses.json"
    elif args.mode == "assessment":
        out_json_path = FILE_PATH / "../vocab/assessment/assessments.json"
    else:
        log.error(f"Invalid mode selected: {args.mode}")
        exit(1)
        
    if not out_json_path.parent.is_dir():
        out_json_path.parent.mkdir(parents=True)
    
    concept_relationship_path = FILE_PATH / "../data/CONCEPT_RELATIONSHIP.csv"
    concept_csv_path = FILE_PATH / "../data/CONCEPT.csv"
    graph_path = FILE_PATH / "../snomed_graph.ttl"

    main(concept_relationship_path, concept_csv_path, graph_path, out_json_path, args.mode)
