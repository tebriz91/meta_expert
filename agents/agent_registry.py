# Script for registering agents.

from typing import TypedDict, Annotated, List, Any
from langgraph.graph.message import add_messages

# add_message creates this  [HumanMessage(content='Hello', id='1'), AIMessage(content='Hi there!', id='2')]
from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages

# Define AgentRegistry as a TypedDict with total=False to allow extra keys
class AgentRegistry(TypedDict, total=False):
    """
    A registry for agents, allowing dynamic addition of agents.
    """
    user: List[Any]

# Initialize the AgentRegistry as an empty dictionary
AgentRegistry = {}
# AgentRegistry is a shared dictionary instance
