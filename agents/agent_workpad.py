# agents/agent_workpad.py

from typing import Dict, List, Any, TypedDict

def create_state_typed_dict(agent_team):
    """
    Creates a TypedDict 'State' where keys are agent names and values are List[str].

    Args:
        agent_team (list): A list of agent classes.

    Returns:
        TypedDict: A dynamically created TypedDict 'State' with agent names as keys and List[str] as values.
    """
    from typing import TypedDict, List

    # Build the fields for the TypedDict dynamically
    fields = {}
    for agent_class in agent_team:
        agent_name = agent_class.name  # Access the 'name' attribute
        fields[agent_name] = List[str]

    # Create the TypedDict 'State' with the dynamic fields
    State = TypedDict('State', fields, total=False)
    return State
