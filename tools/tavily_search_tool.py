from tavily import TavilyClient, MissingAPIKeyError, InvalidAPIKeyError, UsageLimitExceededError

def perform_search(query: str) -> dict:
    """
    Perform a search using the Tavily search tool.

    :param query: The search query string.
    :return: A dictionary containing the search results.
    """
    api_key = "tvly-YOUR_API_KEY"  # Replace with your actual API key
    tavily_client = TavilyClient(api_key=api_key)

    try:
        response = tavily_client.search(query)
        simplified_results = []
        if response.get("results") and isinstance(response["results"], list):
            for idx, result in enumerate(response["results"]):
                if isinstance(result, dict):
                    title = result.get("title", "No Title")
                    url = result.get("url", "#")
                    content = result.get("content", "No Content")
                    simplified_results.append({
                        "query": query,
                        "title": title,
                        "url": url,
                        "content": content,
                    })
                else:
                    print(f"Entry at index {idx} in response['results'] is not a dict: {type(result)}")
        else:
            print("No 'results' found or 'results' is not a list.")
        return {"results": simplified_results}
    except MissingAPIKeyError:
        return {"error": "API key is missing. Please provide a valid API key."}
    except InvalidAPIKeyError:
        return {"error": "Invalid API key provided. Please check your API key."}
    except UsageLimitExceededError:
        return {"error": "Usage limit exceeded. Please check your plan's usage limits or consider upgrading."}
    except Exception as e:
        return {"error": str(e)}
