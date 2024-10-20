import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from fake_useragent import UserAgent
from langchain_community.document_loaders import (
    AsyncChromiumLoader,
    PyPDFLoader,
)
from langchain_community.document_transformers import BeautifulSoupTransformer
from termcolor import colored

ua = UserAgent()
os.environ["USER_AGENT"] = ua.random


def scraper(url: str) -> dict:
    """
    Scrape content from a given URL. Tries to scrape as HTML first,
    then as PDF if HTML fails.

    :param url: The URL to scrape.
    :return: A dictionary containing the source URL and the scraped content.
    """
    print(colored(f"\nStarting basic scraping with URL: {url}\n", color="green"))  # noqa: E501
    try:
        print(colored(f"Starting HTML scraper with URL: {url}", color="green"))
        loader = AsyncChromiumLoader([url])
        html = loader.load()
        # TODO: Reduce the text size scraped
        # Transform
        bs_transformer = BeautifulSoupTransformer()
        docs_transformed = bs_transformer.transform_documents(
            documents=html, tags_to_extract=["p"]
        )
        # Combine content from all paragraphs
        content = "\n".join([doc.page_content for doc in docs_transformed])
        result = {"source": url, "content": content}
        # print(result)
        return result
    except Exception as html_exc:
        print(
            colored(
                f"HTML scraping failed for URL: {url} with exception: {html_exc}",  # noqa: E501
                color="red",
            )
        )
        try:
            print(colored(f"Starting PDF scraper with URL: {url}", color="green"))  # noqa: E501
            loader = PyPDFLoader(url)
            pages = loader.load_and_split()
            # Combine content from all pages
            content = "\n".join([page.page_content for page in pages])
            result = {"source": url, "content": content}
            # print(result)
            return result
        except Exception as pdf_exc:
            print(
                colored(
                    f"PDF scraping failed for URL: {url} with exception: {pdf_exc}",  # noqa: E501
                    color="red",
                )
            )
            result = {
                "source": url,
                "content": "Unsupported document type, supported types are 'html' and 'pdf'.",  # noqa: E501
            }
            # print(result)
            return result


def scrape_urls(urls: list) -> list:
    """
    Scrape content from a list of URLs concurrently.

    :param urls: A list of URLs to scrape.
    :return: A list of dictionaries containing the sourceURL
    and the scraped content for each URL.
    """
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(scraper, url): url for url in urls}
        for future in as_completed(future_to_url):
            try:
                data = future.result()
                results.append(data)
            except Exception as exc:
                url = future_to_url[future]
                print(f"{url} generated an exception: {exc}")
    return results


# if __name__ == "__main__":
#     urls_to_scrape = [
#         "https://example.com",
#         # Add more URLs as needed
#     ]
#     scrape_results = scrape_urls(urls_to_scrape)
#     for result in scrape_results:
#         print(result)
