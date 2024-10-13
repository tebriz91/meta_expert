import os
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)
import concurrent.futures
import functools
import traceback
from typing import Any, Dict, List

import faiss
import numpy as np
from fake_useragent import UserAgent
from flashrank import Ranker, RerankRequest
from langchain.schema import Document
from langchain_anthropic import ChatAnthropic
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_community.graphs import Neo4jGraph
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI
from llmsherpa.readers import LayoutPDFReader
from termcolor import colored

from tools.llm_graph_transformer import LLMGraphTransformer

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)

config_path = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")

ua = UserAgent()
os.environ["USER_AGENT"] = ua.random
os.environ["FAISS_OPT_LEVEL"] = "generic"


def timeout(max_timeout):
    """Timeout decorator, parameter in seconds."""

    def timeout_decorator(item):
        """Wrap the original function."""

        @functools.wraps(item)
        def func_wrapper(*args, **kwargs):
            """Closure for function."""
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(item, *args, **kwargs)
                try:
                    return future.result(max_timeout)
                except concurrent.futures.TimeoutError:
                    return [
                        Document(
                            page_content=f"Timeout occurred while processing URL: {args[0]}",
                            metadata={"source": args[0]},
                        )
                    ]

        return func_wrapper

    return timeout_decorator


def deduplicate_results(results, rerank=True):
    """
    Deduplicate re-ranked results.

    :param results: List of results to deduplicate.
    :param rerank: Boolean indicating if results are re-ranked.
    :return: List of unique results.
    """
    seen = set()
    unique_results = []
    for result in results:
        # Create a tuple of the content and source to use as a unique identifier
        if rerank:
            identifier = (result["text"], result["meta"])
        else:
            # When not reranking, result is a tuple (doc, score)
            doc, score = result
            identifier = (doc.page_content, doc.metadata.get("source", ""))
        if identifier not in seen:
            seen.add(identifier)
            unique_results.append(result)
    return unique_results


def index_and_rank(
    corpus: List[Document], query: str, top_percent: float = 50, batch_size: int = 25
) -> List[Dict[str, str]]:
    """
    Index and rank documents using FastEmbeddings and FAISS.

    :param corpus: List of documents to index and rank.
    :param query: Query string for ranking.
    :param top_percent: Percentage of top results to return.
    :param batch_size: Batch size for processing documents.
    :return: List of ranked results.
    """
    print(
        colored(
            f"\n\nStarting indexing and ranking with FastEmbeddings and FAISS for {len(corpus)} documents\n\n",
            "green",
        )
    )
    CACHE_DIR = "/fastembed_cache"
    embeddings = FastEmbedEmbeddings(
        model_name="jinaai/jina-embeddings-v2-small-en",
        max_length=512,
        cache_dir=CACHE_DIR,
    )

    print(colored("\n\nCreating FAISS index...\n\n", "green"))

    try:
        # Initialize an empty FAISS index
        index = None
        docstore = InMemoryDocstore({})
        index_to_docstore_id = {}

        # Process documents in batches
        for i in range(0, len(corpus), batch_size):
            batch = corpus[i : i + batch_size]
            texts = [doc.page_content for doc in batch]
            metadatas = [doc.metadata for doc in batch]

            print(f"Processing batch {i // batch_size + 1} with {len(texts)} documents")

            # Embed the batch
            batch_embeddings = embeddings.embed_documents(texts)

            # Convert embeddings to numpy array with float32 dtype
            batch_embeddings_np = np.array(batch_embeddings, dtype=np.float32)

            if index is None:
                # Create the index with the first batch
                index = faiss.IndexFlatIP(batch_embeddings_np.shape[1])

            # Normalize the embeddings
            faiss.normalize_L2(batch_embeddings_np)

            # Add embeddings to the index
            start_id = len(index_to_docstore_id)
            index.add(batch_embeddings_np)

            # Update docstore and index_to_docstore_id
            for j, (text, metadata) in enumerate(zip(texts, metadatas)):
                doc_id = f"{start_id + j}"
                docstore.add({doc_id: Document(page_content=text, metadata=metadata)})
                index_to_docstore_id[start_id + j] = doc_id

        print(f"Total documents indexed: {len(index_to_docstore_id)}")

        # Create a FAISS retriever
        retriever = FAISS(embeddings, index, docstore, index_to_docstore_id)

        # Perform the search
        k = min(
            100, len(corpus)
        )  # Ensure we don't try to retrieve more documents than we have

        # Retrieve documents based on query in metadata
        similarity_cache = {}
        docs = []
        for doc in corpus:
            query = doc.metadata.get("query", "")
            # Check if we've already performed this search
            if query in similarity_cache:
                cached_results = similarity_cache[query]
                docs.extend(cached_results)
            else:
                # Perform the similarity search
                search_results = retriever.similarity_search_with_score(query, k=k)

                # Cache the results
                similarity_cache[query] = search_results

                # Add to docs
                docs.extend(search_results)

        docs = deduplicate_results(docs, rerank=False)

        print(colored(f"\n\nRetrieved {len(docs)} documents\n\n", "green"))

        passages = []
        for idx, (doc, score) in enumerate(docs, start=1):
            try:
                passage = {
                    "id": idx,
                    "text": doc.page_content,
                    "meta": doc.metadata.get("source", {"source": "unknown"}),
                    "score": float(score),  # Convert score to float
                }
                passages.append(passage)
            except Exception as e:
                print(colored(f"Error in creating passage: {str(e)}", "red"))
                traceback.print_exc()

        print(colored("\n\nRe-ranking documents...\n\n", "green"))
        # Reranker done based on query in metadata
        CACHE_DIR_RANKER = "/reranker_cache"
        ranker = Ranker(cache_dir=CACHE_DIR_RANKER)
        results = []
        processed_queries = set()

        # Perform reranking with query caching
        for doc in corpus:
            query = doc.metadata.get("query", "")

            # Skip if we've already processed this query
            if query in processed_queries:
                continue

            rerankrequest = RerankRequest(query=query, passages=passages)
            result = ranker.rerank(rerankrequest)
            results.extend(result)

            # Mark this query as processed
            processed_queries.add(query)

        results = deduplicate_results(results, rerank=True)

        print(
            colored(
                f"\n\nRe-ranking complete with {len(results)} documents\n\n", "green"
            )
        )

        # Sort results by score in descending order
        sorted_results = sorted(results, key=lambda x: x["score"], reverse=True)

        # Calculate the number of results to return based on the percentage
        num_results = max(1, int(len(sorted_results) * (top_percent / 100)))
        top_results = sorted_results[:num_results]

        final_results = [
            {"text": result["text"], "meta": result["meta"], "score": result["score"]}
            for result in top_results
        ]

        print(
            colored(
                f"\n\nReturned top {top_percent}% of results ({len(final_results)} documents)\n\n",
                "green",
            )
        )

        # Add debug information about scores
        scores = [result["score"] for result in results]
        print(
            f"Score distribution: min={min(scores):.4f}, max={max(scores):.4f}, mean={np.mean(scores):.4f}, median={np.median(scores):.4f}"
        )
        print(f"Unique scores: {len(set(scores))}")
        if final_results:
            print(
                f"Score range for top {top_percent}% results: {final_results[-1]['score']:.4f} to {final_results[0]['score']:.4f}"
            )

    except Exception as e:
        print(colored(f"Error in indexing and ranking: {str(e)}", "red"))
        traceback.print_exc()
        final_results = [
            {
                "text": "Error in indexing and ranking",
                "meta": {"source": "unknown"},
                "score": 0.0,
            }
        ]

    return final_results


def run_hybrid_graph_retrieval(
    graph: Neo4jGraph = None,
    corpus: List[Document] = None,
    query: str = None,
    rag_mode: str = None,
):
    """
    Run hybrid graph retrieval.

    :param graph: Neo4jGraph instance.
    :param corpus: List of documents.
    :param query: Query string.
    :param rag_mode: Retrieval mode (Hybrid or Dense).
    :return: Retrieved context.
    """
    print(colored("\n\Initiating Retrieval...\n\n", "green"))

    if rag_mode == "Hybrid":
        print(colored("Running Hybrid Retrieval...", "yellow"))
        unstructured_data = index_and_rank(corpus, query)

        query = """
        MATCH p = (n)-[r]->(m)
        WHERE COUNT {(n)--()} > 30
        RETURN p AS Path
        LIMIT 85
        """
        response = graph.query(query)
        retrieved_context = f"Important Relationships:{response}\n\n Additional Context:{unstructured_data}"

    elif rag_mode == "Dense":
        print(colored("Running Dense Only Retrieval...", "yellow"))
        retrieved_context_unformatted = index_and_rank(corpus, query)

    return retrieved_context_unformatted


@timeout(20)
def intelligent_chunking(url: str, query: str) -> List[Document]:
    """
    Perform intelligent chunking with LLM Sherpa for a given URL and query.

    :param url: URL to process.
    :param query: Query string.
    :return: List of documents.
    """
    try:
        print(
            colored(
                f"\n\nStarting Intelligent Chunking with LLM Sherpa for URL: {url}\n\n",
                "green",
            )
        )
        llmsherpa_api_url = os.environ.get("LLM_SHERPA_SERVER")

        if not llmsherpa_api_url:
            raise ValueError("LLM_SHERPA_SERVER environment variable is not set")

        corpus = []

        try:
            print(colored("Starting LLM Sherpa LayoutPDFReader...\n\n", "yellow"))
            reader = LayoutPDFReader(llmsherpa_api_url)
            doc = reader.read_pdf(url)
            print(colored("Finished LLM Sherpa LayoutPDFReader...\n\n", "yellow"))
        except Exception as e:
            print(colored(f"Error in LLM Sherpa LayoutPDFReader: {str(e)}", "red"))
            traceback.print_exc()
            doc = None

        if doc:
            for chunk in doc.chunks():
                document = Document(
                    page_content=chunk.to_context_text(),
                    metadata={"source": url, "query": query},
                )

                if len(document.page_content) > 0:
                    corpus.append(document)

            print(colored(f"Created corpus with {len(corpus)} documents", "green"))

        if not doc:
            print(colored("No document to append to corpus", "red"))

        return corpus

    except concurrent.futures.TimeoutError:
        print(colored(f"Timeout occurred while processing URL: {url}", "red"))
        return [
            Document(
                page_content=f"Timeout occurred while processing URL: {url}",
                metadata={"source": url},
            )
        ]
    except Exception as e:
        print(colored(f"Error in Intelligent Chunking for URL {url}: {str(e)}", "red"))
        traceback.print_exc()
        return [
            Document(
                page_content=f"Error in Intelligent Chunking for URL: {url}",
                metadata={"source": url},
            )
        ]


def clear_neo4j_database(graph: Neo4jGraph):
    """
    Clear all nodes and relationships from the Neo4j database.

    :param graph: Neo4jGraph instance.
    """
    try:
        print(colored("\n\nClearing Neo4j database...\n\n", "yellow"))
        # Delete all relationships first
        graph.query("MATCH ()-[r]->() DELETE r")
        # Then delete all nodes
        graph.query("MATCH (n) DELETE n")
        print(colored("Neo4j database cleared successfully.\n\n", "green"))
    except Exception as e:
        print(colored(f"Error clearing Neo4j database: {str(e)}", "red"))
        traceback.print_exc()


def create_graph_index(
    documents: List[Document] = None,
    allowed_relationships: List[str] = None,
    allowed_nodes: List[str] = None,
    query: str = None,
    graph: Neo4jGraph = None,
    batch_size: int = 10,
    max_workers: int = 5,
) -> Neo4jGraph:
    """
    Create a graph index from documents.

    :param documents: List of documents.
    :param allowed_relationships: List of allowed relationships.
    :param allowed_nodes: List of allowed nodes.
    :param query: Query string.
    :param graph: Neo4jGraph instance.
    :param batch_size: Batch size for processing documents.
    :param max_workers: Number of threads in the pool.
    :return: Updated Neo4jGraph instance.
    """
    if os.environ.get("LLM_SERVER") == "openai":
        llm = ChatOpenAI(temperature=0, model_name="gpt-4o-mini")
    else:
        llm = ChatAnthropic(temperature=0, model_name="claude-3-haiku-20240307")

    llm_transformer = LLMGraphTransformer(
        llm=llm,
        allowed_nodes=allowed_nodes,
        allowed_relationships=allowed_relationships,
        node_properties=True,
        relationship_properties=True,
    )

    total_docs = len(documents)

    # Prepare batches
    batches = [documents[i : i + batch_size] for i in range(0, total_docs, batch_size)]
    total_batches = len(batches)

    print(
        colored(
            f"\nTotal documents: {total_docs}, Total batches: {total_batches}\n",
            "green",
        )
    )

    graph_documents = []

    def process_batch(batch_docs, batch_number):
        """
        Process a batch of documents.

        :param batch_docs: List of documents in the batch.
        :param batch_number: Batch number.
        :return: List of graph documents.
        """
        print(
            colored(f"\nProcessing batch {batch_number} of {total_batches}\n", "yellow")
        )
        try:
            batch_graph_docs = llm_transformer.convert_to_graph_documents(batch_docs)
            print(colored(f"Finished batch {batch_number}\n", "green"))
            return batch_graph_docs
        except Exception as e:
            print(colored(f"Error processing batch {batch_number}: {str(e)}", "red"))
            traceback.print_exc()
            return []

    # Use ThreadPoolExecutor for parallel processing of batches
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all batches to the executor
        future_to_batch = {
            executor.submit(process_batch, batch, idx + 1): idx + 1
            for idx, batch in enumerate(batches)
        }

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_batch):
            batch_number = future_to_batch[future]
            try:
                batch_graph_docs = future.result()
                graph_documents.extend(batch_graph_docs)
            except Exception as e:
                print(colored(f"Exception in batch {batch_number}: {str(e)}", "red"))
                traceback.print_exc()

    print(colored(f"\nTotal graph documents: {len(graph_documents)}\n", "green"))

    # Add documents to the graph
    graph.add_graph_documents(
        graph_documents,
        baseEntityLabel=True,
        include_source=True,
    )

    return graph


def process_retrieved_context(retrieved_context: List[Dict[str, Any]]) -> str:
    """
    Process retrieved context.

    :param retrieved_context: List of retrieved context entries.
    :return: Processed context as a string.
    """
    output = ""
    for idx, entry in enumerate(retrieved_context, start=1):
        text = entry.get("text", "")
        source = entry.get("meta", {"source": "unknown"})
        output += f"---\nEntry {idx}\nText:\n{text}\nSource:\n{source}\n\n"
    return output


def run_rag(
    urls: List[str],
    allowed_nodes: List[str] = None,
    allowed_relationships: List[str] = None,
    query: List[str] = None,
    rag_mode: str = None,
) -> List[Dict[str, str]]:
    """
    Run Retrieval-Augmented Generation (RAG) process.

    :param urls: List of URLs to process.
    :param allowed_nodes: List of allowed nodes.
    :param allowed_relationships: List of allowed relationships.
    :param query: List of query strings.
    :param rag_mode: Retrieval mode (Hybrid or Dense).
    :return: List of results.
    """
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(len(urls), 5)
    ) as executor:
        futures = [
            executor.submit(intelligent_chunking, url, query)
            for url, query in zip(urls, query)
        ]
        chunks_list = [
            future.result() for future in concurrent.futures.as_completed(futures)
        ]

    corpus = [item for sublist in chunks_list for item in sublist]

    print(
        colored(
            f"\n\nTotal documents in corpus after chunking: {len(corpus)}\n\n", "green"
        )
    )

    print(colored(f"\n\n DEBUG HYBRID VALUE: {rag_mode}\n\n", "yellow"))

    if rag_mode == "Hybrid":
        print(colored("\n\n Creating Graph Index...\n\n", "green"))
        graph = Neo4jGraph()
        clear_neo4j_database(graph)
        graph = create_graph_index(
            documents=corpus,
            allowed_nodes=allowed_nodes,
            allowed_relationships=allowed_relationships,
            query=query,
            graph=graph,
        )
    elif rag_mode == "Dense":
        graph = None

    retrieved_context = run_hybrid_graph_retrieval(
        graph=graph, corpus=corpus, query=query, rag_mode=rag_mode
    )

    processed_context = process_retrieved_context(retrieved_context)

    return processed_context


if __name__ == "__main__":
    # For testing purposes.
    url1 = "https://www.reddit.com/r/microsoft/comments/1bkikl1/regretting_buying_copilot_for_microsoft_365"
    url2 = "'https://www.reddit.com/r/microsoft_365_copilot/comments/1chtqtg/do_you_actually_find_365_copilot_useful_in_your"

    urls = [url1, url2]
    query = ["Co-pilot Microsoft"]
    allowed_nodes = None
    allowed_relationships = None
    rag_mode = "Hybrid"
    results = run_rag(
        urls,
        allowed_nodes=allowed_nodes,
        allowed_relationships=allowed_relationships,
        query=query,
        rag_mode=rag_mode,
    )

    print(colored(f"\n\n RESULTS: {results}", "green"))

    print(f"\n\n RESULTS: {results}")
