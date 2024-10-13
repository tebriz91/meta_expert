import os
from langchain_community.document_loaders import AsyncChromiumLoader
from langchain_community.document_transformers import BeautifulSoupTransformer
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.messages import AIMessage
from fake_useragent import UserAgent

ua = UserAgent()
os.environ["USER_AGENT"] = ua.random

def scraper(url: str, doc_type: str) -> dict:
    """
    Scrape content from a given URL based on the document type.

    :param url: The URL to scrape.
    :param doc_type: The type of document to scrape ('html' or 'pdf').
    :return: A dictionary containing the source URL and the scraped content.
    """
    if doc_type == "html":
        try:
            loader = AsyncChromiumLoader([url])
            html = loader.load()
            # Transform the HTML content
            bs_transformer = BeautifulSoupTransformer()
            docs_transformed = bs_transformer.transform_documents(html, tags_to_extract=["p"])
            print({"source": url, "content": AIMessage(docs_transformed[0].page_content)})
            return {"source": url, "content": AIMessage(docs_transformed[0].page_content)}
        except Exception as e:
            return {"source": url, "content": AIMessage(f"Error scraping website: {str(e)}")}
    elif doc_type == "pdf":
        try:
            loader = PyPDFLoader(url)
            pages = loader.load_and_split()
            # Return the scraped PDF content
            return {"source": url, "content": AIMessage(pages)}
        except Exception as e:
            return {"source": url, "content": AIMessage(f"Error scraping PDF: {str(e)}")}
    else:
        return {"source": url, "content": AIMessage("Unsupported document type, supported types are 'html' and 'pdf'.")}

if __name__ == "__main__":
    scraper("https://python.langchain.com/v0.1/docs/modules/data_connection/document_loaders/pdf/", "html")
