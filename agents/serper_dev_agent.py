import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict

from langsmith import traceable

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)

from agents.agent_base import StateT, ToolCallingAgent  # noqa: E402
from tools.google_serper import format_search_results, serper_search  # noqa: E402, E501


class SerperDevAgent(ToolCallingAgent[StateT]):
    """
    # Functionality:
    This agent performs Google web searches based on a list of queries you
    provide. It returns a formatted list of organic search results, including
    the query, title, link, and sitelinks for each result.

    ## Inputs:
    - **queries**: A list of search query strings.
    - **location**: Geographic location code for the search
    (e.g., 'us', 'gb','nl', 'ca'). Defaults to 'us'.

    ## Outputs:
    - A formatted string representing the organic search engine results
    page (SERP), including:
        - Query
        - Title
        - Link
        - Sitelinks

    ## When to Use:
    - When you need to retrieve search engine results for specific queries.
    - When you require URLs from search results for further investigation.

    ## Important Notes:
    - This tool **only** provides search result summaries; it does **not**
    access or retrieve content from the linked web pages.
    - To obtain detailed content or specific information from the web pages
    listed in the search results, you should use the **WebScraperAgent** or
    the **OfflineRAGWebsearchAgent** with the URLs obtained from this tool.

    ## Example Workflow:
    1. **Search**: Use this agent with queries like
    `["latest advancements in AI"]`.
    2. **Retrieve URLs**: Extract the list of URLs from the search results.
    3. **Deep Dive**:
        - Use web scraping with the extracted URLs to get the full content of
        the pages.
        - Use RAG to extract specific data from web pages.

    # Remember
    You should provide the inputs as suggested.

    --------------------------------
    """

    def __init__(
        self,
        name: str,
        model: str = "gpt-4o-mini",
        server: str = "openai",
        temperature: float = 0,
    ) -> None:
        """
        Initialize the SerperDevAgent with common parameters.

        :param name: The name to register the agent
        :param model: The name of the language model to use
        :param server: The server hosting the language model
        :param temperature: Controls randomness in model outputs
        """
        super().__init__(
            name,
            model,
            server,
            temperature,
        )
        self.location = "us"  # Default location for search
        print(f"SerperDevAgent '{self.name}' initialized.")

    @traceable
    def get_guided_json(self, state: StateT = None) -> Dict[str, Any]:
        """
        Define the guided JSON schema expecting a list of search queries.

        :param state: The current state of the agent.
        :return: Guided JSON schema as a dictionary.
        """
        guided_json_schema = {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "A search query string.",
                    },
                    "description": "A list of search query strings.",
                },
                "location": {
                    "type": "string",
                    "description": (
                        "The geographic location for the search results. "
                        "Available locations: 'us' (United States), "
                        "'gb' (United Kingdom), 'nl' (The Netherlands), "
                        "'ca' (Canada)."
                    ),
                },
            },
            "required": ["queries", "location"],
            "additionalProperties": False,
        }
        return guided_json_schema

    @traceable
    def execute_tool(
        self,
        tool_response: Dict[str, Any],
        state: StateT = None,
    ) -> Any:
        """
        Execute the search tool using the provided tool response,
        handling multiple queries concurrently.
        Returns the search results as a concatenated string.

        :param tool_response: The response from the tool.
        :param state: The current state of the agent.
        :return: The search results as a concatenated string.
        """
        queries = tool_response.get("queries")
        loc = tool_response.get("location", self.location)
        if not queries:
            raise ValueError("Search queries missing from the tool response")
        print(f"{self.name} is searching for queries: {queries} in loc: {loc}")

        # Define a function for searching a single query
        def search_query(query) -> str:
            """
            Perform a search for a single query.

            :param query: The search query string.
            :return: The formatted search result string.
            """
            print(f"Searching for '{query}' in location '{loc}'")
            result = serper_search(query=query, location=loc)
            formatted_result_str = format_search_results(search_results=result)
            print(f"Obtained search results for query: '{query}'")
            return formatted_result_str  # Return only formatted result str

        # Collect all formatted result strings
        search_results_list = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_query = {
                executor.submit(search_query, query): query
                for query in queries  # noqa: E501
            }
            for future in as_completed(future_to_query):
                query = future_to_query[future]
                try:
                    result = future.result()
                    search_results_list.append(
                        result
                    )  # Append the result string directly
                except Exception as exc:
                    print(f"Exc while searching for query '{query}': {exc}")
                    error_message = f"Error for query '{query}': {exc}"
                    search_results_list.append(error_message)

        # Combine all search results into a single string
        combined_results = "\n".join(search_results_list)
        # print(
        #     colored(
        #         text=(
        #             f"DEBUG: {self.name} search res: {combined_results} \n\n"
        #             f"Type:{type(combined_results)}"
        #         ),
        #         color="green",
        #     )
        # )

        # Return the combined search results as a string
        return combined_results


# if __name__ == "__main__":
#     # Create an instance of SerperDevAgent for testing
#     agent = SerperDevAgent(name="TestSerperAgent")

#     # Create a sample tool response
#     test_tool_response = {
#         "queries": ["Python programming", "Machine learning basics"],
#         "location": "us",
#     }

#     # Create a sample state (can be None or an empty dict for this test)
#     test_state = {}

#     # Execute the tool and print the results
#     try:
#         results = agent.execute_tool(
#             tool_response=test_tool_response,
#             state=test_state,
#         )
#         print("Search Results:")
#         print(results)
#     except Exception as e:
#         print(f"An error occurred: {e}")

#     # You can add more test cases or assertions
#     # here to verify the functionality
