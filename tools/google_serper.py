import json
import os
from typing import Any, Dict

import requests


def format_shopping_results(shopping_results: list) -> str:
    """
    Format the shopping results into a readable string.

    :param shopping_results: List of shopping results.
    :return: Formatted string of shopping results.
    """
    result_strings = []
    for result in shopping_results:
        title = result.get("title", "No Title")
        link = result.get("link", "#")
        price = result.get("price", "Price not available")
        source = result.get("source", "Source not available")
        rating = result.get("rating", "No rating")
        rating_count = result.get("ratingCount", "No rating count")
        delivery = result.get("delivery", "Delivery information not available")

        result_strings.append(
            (
                f"Title: {title}\nSource: {source}\nPrice: {price}\n"
                f"Rating: {rating} ({rating_count} reviews)\n"
                f"Delivery: {delivery}\nLink: {link}\n---"
            )
        )

    return "\n".join(result_strings)


def serper_search(query: str, location: str) -> Dict[str, Any]:
    """
    Perform a Google search using the Serper API.

    :param query: The search query string.
    :param location: The geographic location for the search.
    :return: Dictionary containing the search results.
    """
    search_url = "https://google.serper.dev/search"
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": os.environ[
            "SERPER_API_KEY"
        ],  # Ensure this environment variable is set
    }
    payload = json.dumps(obj={"q": query, "gl": location})

    try:
        response = requests.post(search_url, headers=headers, data=payload)
        response.raise_for_status()
        results = response.json()

        simplified_results = []
        if results.get("organic") and isinstance(results["organic"], list):
            for idx, result in enumerate(results["organic"]):
                if isinstance(result, dict):
                    title = result.get("title", "No Title")
                    link = result.get("link", "#")
                    sitelinks = result.get("sitelinks", [])
                    # Extract sitelinks if they exist
                    if isinstance(sitelinks, list):
                        sitelinks = [
                            {"title": s.get("title", ""), "link": s.get("link", "")}  # noqa: E501
                            for s in sitelinks
                        ]
                    else:
                        sitelinks = []
                    simplified_results.append({
                        "query": query,
                        "title": title,
                        "link": link,
                        "sitelinks": sitelinks,
                    })
                else:
                    # Log or handle unexpected entry type
                    print(
                        f"Entry at index {idx} in results['organic'] is not a dict: {type(result)}"  # noqa: E501
                    )
        else:
            print("No 'organic' results found or 'organic' is not a list.")

        return {"organic_results": simplified_results}

    except requests.exceptions.HTTPError as http_err:
        return {"error": f"HTTP error occurred: {http_err}"}
    except requests.exceptions.RequestException as req_err:
        return {"error": f"Request error occurred: {req_err}"}
    except KeyError as key_err:
        return {"error": f"Key error occurred: {key_err}"}
    except json.JSONDecodeError as json_err:
        return {"error": f"JSON decoding error occurred: {json_err}"}
    except Exception as ex:
        return {"error": str(ex)}


def serper_shopping_search(query: str, location: str) -> Dict[str, Any]:
    """
    Perform a Google Shopping search using the Serper API.

    :param query: The shopping query string.
    :param location: The geographic location for the search.
    :return: Dictionary containing the shopping results.
    """
    search_url = "https://google.serper.dev/shopping"
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": os.environ["SERPER_API_KEY"],
    }
    payload = json.dumps(obj={"q": query, "gl": location})

    try:
        response = requests.post(search_url, headers=headers, data=payload)
        response.raise_for_status()
        results = response.json()

        if "shopping" in results:
            # Return the raw results
            return {"shopping_results": results["shopping"]}
        else:
            return {"shopping_results": []}

    except requests.exceptions.RequestException as req_err:
        return f"Request error occurred: {req_err}"
    except json.JSONDecodeError as json_err:
        return f"JSON decoding error occurred: {json_err}"


def serper_scholar_search(query: str, location: str) -> Dict[str, Any]:
    """
    Perform a Google Scholar search using the Serper API.

    :param query: The scholar query string.
    :param location: The geographic location for the search.
    :return: Dictionary containing the scholar results.
    """
    search_url = "https://google.serper.dev/scholar"
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": os.environ[
            "SERPER_API_KEY"
        ],  # Ensure this environment variable is set
    }
    payload = json.dumps(obj={"q": query, "gl": location})

    try:
        response = requests.post(search_url, headers=headers, data=payload)
        response.raise_for_status()
        results = response.json()

        if "organic" in results:
            # Return the raw results
            return {"scholar_results": results["organic"]}
        else:
            return {"scholar_results": []}

    except requests.exceptions.RequestException as req_err:
        return f"Request error occurred: {req_err}"
    except json.JSONDecodeError as json_err:
        return f"JSON decoding error occurred: {json_err}"


def format_search_results(search_results: Dict[str, Any]) -> str:
    """
    Formats the search results dictionary into a readable string.

    :param search_results: The dictionary containing search results.
    :return: A formatted string with the query, title, link, and sitelinks.
    """
    formatted_strings = []
    organic_results = search_results.get("organic_results", [])

    for result in organic_results:
        query = result.get("query", "No Query")
        title = result.get("title", "No Title")
        link = result.get("link", "No Link")

        # Start formatting the result
        result_string = f"Query: {query}\nTitle: {title}\nLink: {link}"

        # Handle sitelinks if they exist
        sitelinks = result.get("sitelinks", [])
        if sitelinks:
            sitelinks_strings = []
            for sitelink in sitelinks:
                sitelink_title = sitelink.get("title", "No Title")
                sitelink_link = sitelink.get("link", "No Link")
                sitelinks_strings.append(f"    - {sitelink_title}: {sitelink_link}")  # noqa: E501
            sitelinks_formatted = "\nSitelinks:\n" + "\n".join(sitelinks_strings)  # noqa: E501
            result_string += sitelinks_formatted
        else:
            result_string += "\nSitelinks: None"

        # Add a separator between results
        formatted_strings.append(result_string + "\n" + "-" * 40)

    # Combine all formatted results into one stringfo
    final_string = "\n".join(formatted_strings)
    return final_string


# # Example usage
# if __name__ == "__main__":
#     search_query = "NVIDIA RTX 6000"
#     results = serper_search(search_query, location="us")
#     formatted_results = format_search_results(results)
#     print(formatted_results)
