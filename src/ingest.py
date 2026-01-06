import os
import json
import time
import hashlib
import logging
from dataclasses import dataclass
from typing import List, Dict, Any
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone, ServerlessSpec
from langchain.text_splitter import RecursiveCharacterTextSplitter

# =============================
# Configuration
# =============================

# Chunking configuration
CHUNK_SIZE = 800  # Optimal for legal text density
CHUNK_OVERLAP = 150  # Maintains context between chunks
CHUNK_SEPARATORS = ["\n\n", "\n", ".", " "]  # Split on natural breaks

# Batch sizes
EMBEDDING_BATCH_SIZE = 500  # Process embeddings in batches to avoid memory issues
PINECONE_BATCH_SIZE = 100  # Max recommended by Pinecone

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# =============================
# Logging Setup
# =============================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================
# Configuration Class
# =============================

@dataclass
class Config:
    """Configuration for the ingestion pipeline."""
    openai_key: str
    pinecone_key: str
    pinecone_env: str
    index_name: str
    data_dir: str
    chunk_size: int = CHUNK_SIZE
    chunk_overlap: int = CHUNK_OVERLAP
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables."""
        load_dotenv()
        
        openai_key = os.environ.get("OPENAI_API_KEY")
        pinecone_key = os.environ.get("PINECONE_API_KEY")
        pinecone_env = os.environ.get("PINECONE_ENV", "us-east-1")
        index_name = os.environ.get("PINECONE_INDEX", "criminallaw")
        
        if not openai_key or not pinecone_key:
            raise EnvironmentError(
                "Missing required environment variables: OPENAI_API_KEY and/or PINECONE_API_KEY"
            )
        
        data_dir = os.path.join(
            os.path.dirname(__file__), 
            "../data/Criminal Law Data"
        )
        
        return cls(
            openai_key=openai_key,
            pinecone_key=pinecone_key,
            pinecone_env=pinecone_env,
            index_name=index_name,
            data_dir=data_dir
        )

# =============================
# Text Splitter
# =============================

def create_text_splitter(config: Config) -> RecursiveCharacterTextSplitter:
    """Create configured text splitter."""
    return RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        separators=CHUNK_SEPARATORS
    )

def chunk_text(text: str, splitter: RecursiveCharacterTextSplitter) -> List[str]:
    """Split long text into smaller overlapping chunks."""
    if not text or not isinstance(text, str):
        return []
    return splitter.split_text(text)

# =============================
# Helper Functions
# =============================

def load_json_file(path: str) -> dict:
    """Load and parse a JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data)}")
        
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error reading {path}: {e}")
        raise

def detect_type(fname: str) -> str:
    """Detect document type from filename."""
    name = fname.lower()
    if "amendment" in name:
        return "amendment"
    elif "schedule" in name:
        return "schedule"
    elif "footnote" in name:
        return "footnote"
    elif "main" in name or "clean" in name:
        return "main"
    else:
        return "misc"

def sanitize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure Pinecone-safe metadata (string, number, bool, list[str]).
    Flattens nested structures and converts unsupported types.
    """
    safe = {}
    for k, v in meta.items():
        # Skip None values
        if v is None:
            continue
            
        # Direct types
        if isinstance(v, (str, int, float, bool)):
            safe[k] = v
        # List of strings
        elif isinstance(v, list):
            if all(isinstance(x, str) for x in v):
                safe[k] = v
            else:
                # Convert list to pipe-separated string
                safe[k] = " | ".join([str(x) for x in v])
        # Flatten dictionaries
        elif isinstance(v, dict):
            # Option 1: Flatten to string (current approach)
            safe[k] = " | ".join(f"{ik}:{iv}" for ik, iv in v.items() if iv is not None)
            # Option 2: Create separate keys (uncomment if preferred)
            # for dk, dv in v.items():
            #     safe[f"{k}_{dk}"] = str(dv)
        else:
            safe[k] = str(v)
    
    return safe

def generate_doc_id(filename: str, index: int, text: str) -> str:
    """
    Generate unique document ID with content hash to prevent duplicates.
    """
    content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
    return f"{filename}___{index}___{content_hash}"

# =============================
# Data Normalization
# =============================

def validate_data_structure(data: dict) -> None:
    """Validate that the data has the expected structure."""
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data)}")
    
    # Check for required fields (at least one should exist)
    if "chapters" not in data and "preamble" not in data:
        raise ValueError("Data must contain 'chapters' or 'preamble'")

def normalize_docs(data: dict, splitter: RecursiveCharacterTextSplitter) -> List[Dict[str, Any]]:
    """
    Normalize Criminal Law Acts into docs with `text` + metadata.
    Handles: Chapters → Sections → Sub-sections → Clauses → Explanations.
    """
    # Validate input
    validate_data_structure(data)
    
    docs = []

    # Extract act-level metadata
    act_title = data.get("act_title", "")
    act_number = data.get("act_number", "")
    act_date = data.get("date_of_commencement", "")
    preamble = data.get("preamble", "")

    # Process Preamble
    if preamble and preamble.strip():
        docs.append({
            "text": f"Preamble: {preamble}",
            "act_title": act_title,
            "act_number": act_number,
            "date_of_commencement": act_date,
            "doc_type": "preamble"
        })

    # Process Chapters
    for ch in data.get("chapters", []):
        ch_num = ch.get("chapter_number")
        ch_title = ch.get("chapter_title")

        # Process Sections
        for sec in ch.get("sections", []):
            sec_num = sec.get("section_number", "")
            sec_title = sec.get("section_title", "")
            sec_text = sec.get("text", "")

            # Section main text
            if sec_text and sec_text.strip():
                docs.append({
                    "text": f"Section {sec_num} — {sec_title}: {sec_text}",
                    "chapter_number": ch_num,
                    "chapter_title": ch_title,
                    "section_number": sec_num,
                    "section_title": sec_title,
                    "act_title": act_title,
                    "act_number": act_number,
                    "doc_type": "section"
                })

            # Process Sub-sections
            for sub in sec.get("sub_sections", []):
                text = sub.get("text", "")
                if sub.get("term") and sub.get("definition"):
                    text = f"{sub['term']}: {sub['definition']}"
                
                if text and text.strip():
                    docs.append({
                        "text": f"Section {sec_num}{sub.get('sub_section_number','')}: {text}",
                        "chapter_number": ch_num,
                        "chapter_title": ch_title,
                        "section_number": sec_num,
                        "section_title": sec_title,
                        "sub_section_number": sub.get("sub_section_number"),
                        "act_title": act_title,
                        "doc_type": "subsection"
                    })

            # Process Clauses
            for clause in sec.get("clauses", []):
                clause_text = clause.get("text", "")
                if clause_text and clause_text.strip():
                    docs.append({
                        "text": f"Section {sec_num}{clause.get('clause_label','')}: {clause_text}",
                        "chapter_number": ch_num,
                        "chapter_title": ch_title,
                        "section_number": sec_num,
                        "section_title": sec_title,
                        "clause_label": clause.get("clause_label"),
                        "act_title": act_title,
                        "doc_type": "clause"
                    })

            # Process Explanations
            for exp in sec.get("explanations", []):
                if "types" in exp:
                    for t in exp["types"]:
                        type_text = f"{t.get('type','')} — {t.get('definition','')}"
                        if type_text.strip():
                            docs.append({
                                "text": f"Explanation {exp.get('explanation_number','')}: {type_text}",
                                "chapter_number": ch_num,
                                "chapter_title": ch_title,
                                "section_number": sec_num,
                                "section_title": sec_title,
                                "explanation_number": exp.get("explanation_number"),
                                "act_title": act_title,
                                "doc_type": "explanation"
                            })
                else:
                    exp_content = exp.get("content", "")
                    if exp_content and exp_content.strip():
                        docs.append({
                            "text": f"Explanation {exp.get('explanation_number','')}: {exp_content}",
                            "chapter_number": ch_num,
                            "chapter_title": ch_title,
                            "section_number": sec_num,
                            "section_title": sec_title,
                            "explanation_number": exp.get("explanation_number"),
                            "act_title": act_title,
                            "doc_type": "explanation"
                        })

    # Apply chunking and enrich metadata
    cleaned = []
    for d in docs:
        # Ensure document has text
        if isinstance(d, str):
            d = {"text": d}
        elif isinstance(d, dict):
            if "text" not in d or not d["text"]:
                d["text"] = str(d)
        else:
            d = {"text": str(d)}

        # Chunk the text
        chunks = chunk_text(d["text"], splitter)
        
        if chunks:
            for chunk_idx, ch in enumerate(chunks):
                new_doc = d.copy()
                new_doc["text"] = ch
                new_doc["chunk_index"] = chunk_idx
                new_doc["total_chunks"] = len(chunks)
                new_doc["is_chunked"] = True
                new_doc["keywords"] = f"{new_doc.get('section_title','')} {new_doc.get('chapter_title','')}".strip()
                cleaned.append(new_doc)
        else:
            # No chunking needed
            d["chunk_index"] = 0
            d["total_chunks"] = 1
            d["is_chunked"] = False
            d["keywords"] = f"{d.get('section_title','')} {d.get('chapter_title','')}".strip()
            cleaned.append(d)

    logger.info(f"Normalized {len(docs)} documents into {len(cleaned)} chunks")
    return cleaned

# =============================
# Pinecone Operations
# =============================

def create_or_get_index(pc: Pinecone, index_name: str, dimension: int, 
                        environment: str, max_wait: int = 60) -> Any:
    """
    Create Pinecone index if it doesn't exist, or get existing index.
    Waits for index to be ready.
    """
    existing_indexes = pc.list_indexes().names()
    
    if index_name not in existing_indexes:
        logger.info(f"Creating new Pinecone index: {index_name}")
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=environment)
        )
        
        # Wait for index to be ready
        logger.info("Waiting for index to be ready...")
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                status = pc.describe_index(index_name).status
                if status.get('ready', False):
                    logger.info("Index is ready!")
                    break
            except Exception as e:
                logger.warning(f"Error checking index status: {e}")
            
            time.sleep(2)
        else:
            raise TimeoutError(f"Index {index_name} did not become ready within {max_wait}s")
    else:
        logger.info(f"Using existing index: {index_name}")
    
    return pc.Index(index_name)

def embed_documents_in_batches(texts: List[str], embeddings: OpenAIEmbeddings, 
                               batch_size: int = EMBEDDING_BATCH_SIZE) -> List[List[float]]:
    """
    Create embeddings in batches to avoid memory issues and respect rate limits.
    """
    all_embeddings = []
    total_batches = (len(texts) + batch_size - 1) // batch_size
    
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        
        logger.info(f"Creating embeddings for batch {batch_num}/{total_batches} ({len(batch_texts)} texts)")
        
        # Retry logic for API failures
        for attempt in range(MAX_RETRIES):
            try:
                batch_embeddings = embeddings.embed_documents(batch_texts)
                all_embeddings.extend(batch_embeddings)
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.warning(f"Embedding failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to create embeddings after {MAX_RETRIES} attempts")
                    raise
    
    return all_embeddings

def upsert_to_pinecone(index: Any, embeddings: List[List[float]], 
                      metadatas: List[Dict], filename: str, 
                      batch_size: int = PINECONE_BATCH_SIZE) -> None:
    """
    Upsert embeddings to Pinecone in batches with retry logic.
    """
    total_vectors = len(embeddings)
    total_batches = (total_vectors + batch_size - 1) // batch_size
    
    logger.info(f"Uploading {total_vectors} vectors in {total_batches} batches...")
    
    for i in range(0, len(embeddings), batch_size):
        batch_embeddings = embeddings[i:i+batch_size]
        batch_metadatas = metadatas[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        
        # Prepare batch
        vectors = []
        for j, vec in enumerate(batch_embeddings):
            idx = i + j
            _id = generate_doc_id(filename, idx, metadatas[idx].get("text", ""))
            vectors.append((_id, vec, batch_metadatas[j]))
        
        # Upsert with retry logic
        for attempt in range(MAX_RETRIES):
            try:
                index.upsert(vectors=vectors)
                logger.info(f"Uploaded batch {batch_num}/{total_batches} ({len(vectors)} vectors)")
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.warning(f"Upsert failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to upsert batch after {MAX_RETRIES} attempts")
                    raise

# =============================
# Main Ingestion Function
# =============================

def ingest_json(json_path: str, config: Config, pc: Pinecone, 
                embeddings: OpenAIEmbeddings, splitter: RecursiveCharacterTextSplitter,
                dry_run: bool = False) -> None:
    """
    Ingest a JSON file into Pinecone.
    """
    filename = os.path.basename(json_path)
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Processing {filename}")
    
    # Load and normalize data
    try:
        data = load_json_file(json_path)
        docs = normalize_docs(data, splitter)
    except (ValueError, KeyError) as e:
        logger.error(f"Data validation error in {filename}: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing {filename}: {e}", exc_info=True)
        raise
    
    if not docs:
        logger.warning(f"No documents extracted from {filename}")
        return
    
    if not docs[0].get("text", "").strip():
        raise ValueError(f"No usable text found in {filename}")
    
    logger.info(f"Extracted {len(docs)} document chunks from {filename}")
    
    if dry_run:
        logger.info("[DRY RUN] Skipping embedding and upload")
        logger.info(f"[DRY RUN] Would process {len(docs)} documents")
        logger.info(f"[DRY RUN] Sample document: {docs[0]}")
        return
    
    # Get or create index
    sample_vec = embeddings.embed_query(docs[0]["text"])
    dimension = len(sample_vec)
    index = create_or_get_index(pc, config.index_name, dimension, config.pinecone_env)
    
    # Detect document type
    ftype = detect_type(filename)
    
    # Prepare texts and metadata
    all_texts = []
    metadatas = []
    for doc in docs:
        text = doc.get("text", "")
        meta = {k: v for k, v in doc.items() if k != "text"}
        meta["source"] = filename
        meta["type"] = ftype
        meta["text"] = text  # Keep for ID generation
        meta = sanitize_metadata(meta)
        
        all_texts.append(text)
        metadatas.append(meta)
    
    # Create embeddings in batches
    logger.info(f"Creating embeddings for {len(all_texts)} texts...")
    embeddings_list = embed_documents_in_batches(all_texts, embeddings)
    
    # Upload to Pinecone
    upsert_to_pinecone(index, embeddings_list, metadatas, filename)
    
    logger.info(f"Successfully ingested {filename} → {config.index_name}")

# =============================
# Main Entry Point
# =============================

def main(dry_run: bool = False) -> None:
    """
    Main function to ingest all JSON files from the data directory.
    """
    try:
        # Load configuration
        config = Config.from_env()
        
        if dry_run:
            logger.info("🔍 DRY RUN MODE - No data will be uploaded to Pinecone")
        
        # Initialize clients
        pc = Pinecone(api_key=config.pinecone_key)
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large", 
            openai_api_key=config.openai_key
        )
        splitter = create_text_splitter(config)
        
        # Find JSON files
        logger.info(f"Looking for JSON files in: {config.data_dir}")
        
        if not os.path.exists(config.data_dir):
            raise FileNotFoundError(f"Data directory not found: {config.data_dir}")
        
        files = [f for f in os.listdir(config.data_dir) if f.endswith(".json")]
        
        if not files:
            logger.warning(f"No JSON files found in {config.data_dir}")
            return
        
        logger.info(f"Found {len(files)} JSON files: {files}")
        
        # Process each file
        success_count = 0
        failed_files = []
        
        for fname in files:
            fpath = os.path.join(config.data_dir, fname)
            try:
                ingest_json(fpath, config, pc, embeddings, splitter, dry_run)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to process {fname}: {e}", exc_info=True)
                failed_files.append(fname)
        
        # Summary
        logger.info("=" * 60)
        logger.info(f"Ingestion complete!")
        logger.info(f"  Successful: {success_count}/{len(files)}")
        logger.info(f"  Failed: {len(failed_files)}/{len(files)}")
        if failed_files:
            logger.info(f"  Failed files: {', '.join(failed_files)}")
        logger.info(f"  Target index: {config.index_name}")
        logger.info("=" * 60)
        
    except EnvironmentError as e:
        logger.error(f"Configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    import sys
    
    # Support dry-run mode from command line
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)