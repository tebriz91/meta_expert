# Script for registering agents.

# add_message creates this  [HumanMessage(content='Hello', id='1'), AIMessage(content='Hi there!', id='2')]
from typing import Annotated, Any, List, TypedDict  # noqa

from langgraph.graph.message import add_messages  # noqa


# Define AgentRegistry as a TypedDict with total=False to allow extra keys
class AgentRegistry(TypedDict, total=False):
    """
    A registry for agents, allowing dynamic addition of agents.

    e.g.
    Jar3d: Annotated[Any, add_messages]
    RAGAgent: Annotated[Any, add_messages]
    total=False allows us to add additional agents dynamically
    """

    user: List[Any]


# Initialize the AgentRegistry as an empty dictionary
AgentRegistry = {}
# AgentRegistry is a shared dictionary instance
