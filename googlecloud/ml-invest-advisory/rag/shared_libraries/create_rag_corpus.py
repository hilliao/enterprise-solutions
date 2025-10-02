#!/usr/bin/env python3
# pip install --upgrade google-cloud-aiplatform

from vertexai import rag
import vertexai
import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_env_variable(name):
    """Gets an environment variable or raises an error if it's not set."""
    value = os.getenv(name)
    if value is None:
        raise EnvironmentError(
            f"Environment variable '{name}' is not set. "
            f"Please set it before running the script. "
            f"Example: export {name}='your_value'"
        )
    return value

PROJECT_ID = get_env_variable("GOOGLE_CLOUD_PROJECT")
CORPUS_NAME = 'hil-liao-fsi-2025-09-30'
LOCATION = get_env_variable("GOOGLE_CLOUD_LOCATION")

# Cloud storage folder path to all the PDF documents.
# This variable can contain multiple paths separated by commas.
PATHS_STR = get_env_variable("RAG_INPUT_PATHS")
PATHS = PATHS_STR.split(',')


llm_parser_model = "publishers/google/models/gemini-2.5-flash"
rag_embedding_llm = "publishers/google/models/text-embedding-005"

# Initialize Vertex AI API once per session
vertexai.init(project=PROJECT_ID, location=LOCATION)

transformation_config = rag.TransformationConfig(
    chunking_config=rag.ChunkingConfig(
        chunk_size=1024,  # Optional
        chunk_overlap=200,  # Optional
    ),
)

# https://cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/llm-parser#import-files-with-llmparser
llm_parser_config = rag.LlmParserConfig(
    model_name=llm_parser_model,
)

# Configure embedding model, for example "text-embedding-005".
embedding_model_config = rag.RagEmbeddingModelConfig(
    vertex_prediction_endpoint=rag.VertexPredictionEndpoint(
        publisher_model=rag_embedding_llm
    )
)

# Need to create the corpus first before import
rag_corpus = rag.create_corpus(
    display_name=CORPUS_NAME,
    backend_config=rag.RagVectorDbConfig(
        rag_embedding_model_config=embedding_model_config
    ),
)

# Import throws 400 exception if no RAG corpus is found.
rag.import_files(
    rag_corpus.name,
    PATHS,
    llm_parser=llm_parser_config,
    transformation_config=transformation_config,
)
