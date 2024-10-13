# Script for registering agents.
# add_message creates this
# [
# HumanMessage(content='Hello', id='1'),
# AIMessage(content='Hi there!', id='2')
# ]
from typing import Annotated, Any, List, TypedDict  # noqa

from langgraph.graph.message import add_messages  # noqa


# Define AgentRegistry as a TypedDict with total=False to allow extra keys
class AgentRegistry(TypedDict, total=False):
    # WebSearchAgent: Annotated[Any, add_messages]
    user: List[Any]
    # RAGAgent: Annotated[Any, add_messages]
    # total=False allows us to add additional agents dynamically


# Initialize the agent_workpad as an empty AgentWorkpad
# agent_workpad: AgentWorkpad = {}
# AgentWorkpad is a shared dictionary instance
