import json
from typing import Any, Dict

from langsmith import traceable

from agents.agent_base import StateT, ToolCallingAgent
from tools.tavily_search_tool import perform_search


class TavilySearchAgent(ToolCallingAgent[StateT]):
    """
    An agent that performs search operations using the Tavily search tool.
    """

    def __init__(
        self,
        name: str,
        model: str = "gpt-4o-mini",
        server: str = "openai",
        temperature: float = 0,
    ) -> None:
        """
        Initialize the TavilySearchAgent with common parameters.

        :param name: The name to register the agent
        :param model: The name of the language model to use
        :param server: The server hosting the language model
        :param temperature: Controls randomness in model outputs
        """
        super().__init__(
            name=name,
            model=model,
            server=server,
            temperature=temperature,
        )
        print(f"TavilySearchAgent '{self.name}' initialized.")

    @traceable
    def get_guided_json(self, state: StateT = None) -> Dict[str, Any]:
        """
        Get guided JSON schema for the search tool, expecting a search query.

        :param state: The current state of the agent.
        :return: Guided JSON schema as a dictionary.
        """
        guided_json_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string.",
                }
            },
            "required": ["query"],
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
        Execute the search tool using the provided tool response.
        Returns the search results as a JSON-formatted string.

        :param tool_response: The response from the tool.
        :param state: The current state of the agent.
        :return: The search results as a JSON-formatted string.
        """
        query = tool_response.get("query")
        if not query:
            raise ValueError("Search query is missing from the tool response")
        print(f"{self.name} is performing search for query: {query}")

        # Call the perform_search function from tavily_search_tool
        results = perform_search(query=query)

        # Convert the results to JSON string
        results_str = json.dumps(results)
        return results_str
