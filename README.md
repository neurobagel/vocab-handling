# vocab-handling
Code for processing external vocabularies for Neurobagel

## Preparation

Before you can start extracting the terms we use from existing
vocabularies, you first have to obtain the vocabulary files.
The easiest way we have found so far to do this is to 

1. Make an account on https://athena.ohdsi.org/search-terms/start
2. Navigate to https://athena.ohdsi.org/vocabulary/list and select the vocabularies you want to download
   - In the download window, provide an alias for your selected vocab collection under "name bundle"
3. Unzip the downloaded files and place them in the `/data` directory here in this repo

The scripts in this repo will assume that you have already downloaded the vocabularies (e.g. SNOMED)
and placed them in the `/data` directory.
