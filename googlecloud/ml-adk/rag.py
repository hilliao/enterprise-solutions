# pip install --upgrade google-cloud-aiplatform

from vertexai import rag
import vertexai

PROJECT_ID = "adb-gcp-devteam-dev" # Your Project ID
CORPUS_NAME = "hil-liao-fsi-2025-09-30"
# RAG Engine in us-central1 is for allow list only
LOCATION = "us-east4"
MODEL_ID = "publishers/google/models/gemini-2.5-flash"
MODEL_NAME = MODEL_ID

# Cloud storage folder path to all the PDF documents
PATHS = ["gs://hil-liao-vertex-ai-adk/2025-09-30"]

# Initialize Vertex AI API once per session
vertexai.init(project=PROJECT_ID, location=LOCATION)

transformation_config = rag.TransformationConfig(
    chunking_config=rag.ChunkingConfig(
        chunk_size=1024, # Optional
        chunk_overlap=200, # Optional
    ),
)

# https://cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/llm-parser#import-files-with-llmparser
llm_parser_config = rag.LlmParserConfig(
    model_name = MODEL_NAME,
)

# Configure embedding model, for example "text-embedding-005".
embedding_model_config = rag.RagEmbeddingModelConfig(
    vertex_prediction_endpoint=rag.VertexPredictionEndpoint(
        publisher_model="publishers/google/models/text-embedding-005"
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