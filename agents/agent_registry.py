from typing import Annotated, Any, List, TypedDict  # noqa

from langgraph.graph.message import add_messages  # noqa


# Define AgentRegistry as a TypedDict with total=False to allow extra keys
class AgentRegistry(TypedDict, total=False):
    # SerperDevAgent: Annotated[Any, add_messages]
    # WebScraperAgent: Annotated[Any, add_messages]
    # MetaAgent: Annotated[Any, add_messages]
    # ReporterAgent: Annotated[Any, add_messages]
    user: List[Any]


# Define a dictionary to store agent descriptions
AgentRegistry = {}
