import argparse
from pathlib import Path
import logging

import pandas as pd
from rdflib import Graph, RDFS, Literal
import tqdm


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("generate_diagnosis")


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


def load_concept_csv(filepath):
    """Load table for mapping an (Athena) concept_id to concept_code (equivalent to BioPortal term ID)"""
    log.info("Loading the CONCEPT.csv")
    return pd.read_csv(filepath, sep="\t", dtype=str, keep_default_na=False)


def filter_terms(df, diagnosis_concept_ids):
    log.info("Filtering diagnosis terms")
    return df.query("domain_id == 'Condition' and standard_concept == 'S' and concept_id in @diagnosis_concept_ids")


def structure_for_json(df):
    log.info("Structuring dataframe for JSON output")
    df = df[['concept_code', 'concept_name']]
    df = df.rename(columns={'concept_code': 'identifier', 'concept_name': 'label'})
    df = df.reset_index(drop=True)
    df['identifier'] = 'snomed:' + df['identifier'].astype(str)
    return df


def save_to_json(df, filepath):
    log.info(f"Saving to JSON file {filepath}")
    df.to_json(filepath, orient="records", indent=2)
    
    
def main(concept_relationship_path, concept_csv_path, graph_path, out_json_path, mode):
    df_relationships = load_concept_relationships(concept_relationship_path)
    df_concepts = load_concept_csv(concept_csv_path)
    
    if graph_path.exists():
        graph = load_graph(graph_path)
    else:
        graph = create_graph(df_relationships)
        save_graph(graph, graph_path)
    
    if mode == "diagnosis":
        query = """
        SELECT ?child
        WHERE {
        {?child rdfs:subClassOf* 432586}
        UNION
        {?child rdfs:subClassOf* 376106}
        }
        """
    elif mode == "assessment":
        query = """
        SELECT ?child
        WHERE {
        ?child rdfs:subClassOf* 4157120 
        }
        """
    
    concept_ids = run_query(graph, query)
    terms_df = filter_terms(df_concepts, concept_ids)

    terms_dict = structure_for_json(terms_df)
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
    
    concept_relationship_path = FILE_PATH / "../data/CONCEPT_RELATIONSHIP.csv"
    concept_csv_path = FILE_PATH / "../data/CONCEPT.csv"
    graph_path = FILE_PATH / "../snomed_graph.ttl"
    main(concept_relationship_path, concept_csv_path, graph_path, out_json_path, args.mode)