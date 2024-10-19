import json
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from termcolor import colored

from agents.agent_workpad import create_state_typed_dict


def build_workflow(
    agent_team,
    requirements,
) -> tuple[CompiledStateGraph, dict]:
    """
    Builds a workflow for a team of agents based on the given requirements.

    Args:
        agent_team (list): A list of agent classes.
        requirements (dict): A dictionary of requirements for the workflow.

    Returns tuple containing:
        - CompiledStateGraph: The compiled workflow graph.
        - dict: The initial state of the workflow.
    """
    # Ensure 'meta_agent' and 'reporter_agent' are in agent_team
    agent_names = [agent.name for agent in agent_team]
    if "meta_agent" not in agent_names or "reporter_agent" not in agent_names:
        raise ValueError("Both 'meta_agent' and 'reporter_agent' must be in agent_team")  # noqa: E501

    # Create the State subclass
    State = create_state_typed_dict(agent_team)

    # Initialize the state
    state: MessagesState = State()

    # Register the agents with the state
    for agent in agent_team:
        agent.register(state)

    print(colored(text=f"\n\nDEBUG: State: {State}\n\n", color="red"))
    print(colored(text=f"\nInitial state:\n\n{state}\n\n", color="blue"))

    # Define the graph
    graph = StateGraph(state_schema=State)

    # Dictionary to map agent names to node names
    agent_nodes = {}

    # Add nodes dynamically for each agent
    for agent in agent_team:
        node_name = f"{agent.name}_node"
        agent_nodes[agent.name] = node_name
        if agent.name == "meta_agent":
            # For meta_agent, pass requirements
            graph.add_node(
                node=node_name,
                action=lambda state, agent=agent: agent.invoke(
                    state=state, requirements=requirements
                ),
            )
        else:
            graph.add_node(
                node=node_name,
                action=lambda state, agent=agent: agent.invoke(state=state),
            )

    # Define the routing function
    def routing_function(state: MessagesState) -> Any | Literal["__end__"]:
        """
        Determines the next agent to be invoked based on the current state.

        Args:
            state (MessagesState): The current state of the workflow.

        Returns:
            str: The name of the next agent node to be invoked.
        """
        print(colored(text=f"\n\nDEBUG: State: {state}\n\n", color="red"))
        # If there is no key "meta_agent" the state defaults to an empty string
        if state.get("meta_agent", ""):
            # Extract the last responce from meta_agent
            meta_agent_response = state.get("meta_agent", "")[-1].page_content
            try:
                # Parse meta_agent_response as JSON
                meta_agent_response_json = json.loads(meta_agent_response)
                # Extract the value associated with the "Agent" key
                next_agent = meta_agent_response_json.get("Agent")
                # Map the agent name to its corresponding node name
                # If it fails, it defaults to END
                next_agent_node = agent_nodes.get(next_agent, END)
            except json.JSONDecodeError:
                next_agent_node = END
        else:
            next_agent_node = END
        print(
            colored(text=f"\n\nDEBUG: Next agent: {next_agent_node}\n\n", color="red")  # noqa: E501
        )
        return next_agent_node

    # Edge from START to meta_agent_node
    graph.add_edge(start_key=START, end_key=agent_nodes["meta_agent"])

    # Conditional edge from meta_agent_node to next agent
    graph.add_conditional_edges(
        source=agent_nodes["meta_agent"],
        path=lambda state: routing_function(state),
    )

    # For each agent, add an edge back to 'meta_agent_node'
    # after the agent's node is processed
    for agent in agent_team:
        node_name = agent_nodes[agent.name]
        if agent.name != "reporter_agent" and agent.name != "meta_agent":
            graph.add_edge(node_name, agent_nodes["meta_agent"])
        elif agent.name == "reporter_agent":
            # 'reporter_agent_node' goes to END
            graph.add_edge(node_name, END)

    # Compile the workflow
    checkpointer = MemorySaver()
    workflow = graph.compile(checkpointer)
    return workflow, state
