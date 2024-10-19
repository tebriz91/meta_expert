import asyncio
import json
import os
import re
import time

import chainlit as cl
from termcolor import colored

from agents.agent_base import MetaAgent, ReporterAgent, SimpleAgent
from agents.offline_rag_websearch_agent import OfflineRAGWebsearchAgent
from agents.serper_dev_agent import SerperDevAgent
from agents.serper_dev_shopping_agent import SerperShoppingAgent
from agents.web_scraper_agent import WebScraperAgent
from workflow_builders.meta_agent import build_workflow


@cl.on_chat_start
async def start() -> None:
    """
    Initialize the chat session, set up task list, and register agents.
    """
    task_list = cl.TaskList()
    task_list.status = "Ready"
    await task_list.send()
    cl.user_session.set(key="task_list", value=task_list)

    cl.user_session.set(key="conversation_history", value=[])
    """
    IMPORTANT: Every Agent team must have a MetaAgent called
    "meta_agent" and a ReporterAgent called "reporter_agent".
    IMPORTANT: server names can be "openai" or "anthropic"
    IMPORTANT: for openai models use gpt-4o or gpt-4o-mini
    """
    # Add new agents here:
    meta_agent = MetaAgent(
        name="meta_agent",
        server="openai",
        model="gpt-4o",
        temperature=0.7,
    )
    serper_agent = SerperDevAgent(
        name="serper_agent",
        server="openai",
        model="gpt-4o-mini",
        temperature=0,
    )
    serper_shopping_agent = SerperShoppingAgent(
        name="serper_shopping_agent",
        server="openai",
        model="gpt-4o-mini",
        temperature=0,
    )
    web_scraper_agent = WebScraperAgent(
        name="web_scraper_agent",
        server="openai",
        model="gpt-4o-mini",
        temperature=0,
    )
    offline_rag_websearch_agent = OfflineRAGWebsearchAgent(
        name="offline_rag_websearch_agent",
        server="openai",
        model="gpt-4o-mini",
        temperature=0,
    )
    # Note reporter agent does not call llms.
    reporter_agent = ReporterAgent(
        name="reporter_agent",
        server="openai",
        model="gpt-4o",
        temperature=0,
    )
    llm = SimpleAgent(
        name="chat_model",
        server="openai",
        model="gpt-4o-mini",
        temperature=0,
    )

    chat_model = llm.get_llm()

    prompt_path = os.path.join(
        os.path.dirname(__file__),
        "prompt_engineering",
        "meta_expert_requirements_prompt.md",
    )

    with open(file=prompt_path, mode="r", encoding="utf-8") as file:
        system_prompt = file.read()

    system_prompt = (
        f"{system_prompt}\n\n Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}"  # noqa: E501
    )

    # Add new agents to the session
    cl.user_session.set("system_prompt", system_prompt)
    cl.user_session.set("chat_model", chat_model)
    cl.user_session.set("meta_agent", meta_agent)
    cl.user_session.set("serper_agent", serper_agent)
    cl.user_session.set("serper_shopping_agent", serper_shopping_agent)
    cl.user_session.set("web_scraper_agent", web_scraper_agent)
    cl.user_session.set("offline_rag_websearch_agent", offline_rag_websearch_agent)  # noqa: E501
    cl.user_session.set("reporter_agent", reporter_agent)

    instructions = "/start"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instructions},
    ]

    meta_expert_intro_hi = chat_model.invoke(messages)

    await cl.Message(content=meta_expert_intro_hi, author="Meta Expert👩‍💻").send()  # noqa: E501


def build_chat_workflow(agent_team, requirements, configs=None, state=None):
    """
    Build the chat workflow using the provided agent team and requirements.

    :param agent_team: List of agents to be included in the workflow.
    :param requirements: User requirements for the workflow.
    :param configs: Optional configurations for the workflow.
    :param state: Optional initial state for the workflow.
    :return: Compiled workflow and initial state.
    """
    workflow, state = build_workflow(agent_team, requirements)

    return workflow, state


def _run_workflow_sync(workflow, state, configs, progress_queue) -> None:
    """
    Run the workflow synchronously and update the progress queue.

    :param workflow: The compiled workflow to be executed.
    :param state: The initial state of the workflow.
    :param configs: Configuration settings for the workflow.
    :param progress_queue: Queue to track progress messages.
    """
    seen_progress_messages = set()
    try:
        for event in workflow.stream(state, configs):
            response = state.get("meta_agent", "No response from ReporterAgent")[  # noqa: E501
                -1
            ].page_content
            response_json = json.loads(response)
            message = response_json.get("step_4").get("final_draft")
            agent = response_json.get("Agent")

            node_output = next(iter(event.values()))
            reporter_agent_node = node_output.get("reporter_agent", "")
            print(
                colored(
                    text=f"\n\nDEBUG REPORTER AGENT NODE: {reporter_agent_node}\n\n",  # noqa: E501
                    color="cyan",
                )
            )

            if reporter_agent_node:
                message = reporter_agent_node[-1].page_content

            truncated_msg = message[:50]

            task_tracking_message = f"Meta Agent asked {agent} to: {truncated_msg}"  # noqa: E501

            print(
                colored(
                    text=f"\n\nMeta Agent asked {agent} to: {message}\n\n",
                    color="green",
                )
            )

            if task_tracking_message not in seen_progress_messages:
                progress_queue.put_nowait(task_tracking_message)
                seen_progress_messages.add(task_tracking_message)
    except Exception as e:
        print(f"Exception in workflow execution: {e}")
    finally:
        progress_queue.put_nowait(None)  # Signal that the workflow is complete


async def run_workflow(workflow, state, configs):
    """
    Run the workflow asynchronously and update the task list.

    :param workflow: The compiled workflow to be executed.
    :param state: The initial state of the workflow.
    :param configs: Configuration settings for the workflow.
    :return: Final message and updated state.
    """
    task_list = cl.user_session.get(key="task_list")
    task_list.status = "Running..."
    await task_list.send()

    progress_queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None,
        _run_workflow_sync,
        workflow,
        state,
        configs,
        progress_queue,
    )

    # Process progress messages and update the TaskList
    while True:
        progress_message = await progress_queue.get()
        if progress_message is None:
            # Workflow is complete
            break

        # Create a new task with status RUNNING
        task = cl.Task(title=progress_message, status=cl.TaskStatus.RUNNING)
        await task_list.add_task(task)
        await task_list.send()

        # Simulate task completion
        task.status = cl.TaskStatus.DONE
        await task_list.send()

    # Update TaskList status to Done and send the final update
    task_list.status = "Done"
    await task_list.send()

    # Retrieve the final state
    meta_agent_response = state.get("meta_agent", [])
    if not meta_agent_response:
        final_message = "No response from ReporterAgent"
    else:
        final_message = meta_agent_response[-1].page_content

    # Ensure final_message is a valid JSON string
    try:
        response_json = json.loads(final_message)
    except json.JSONDecodeError:
        response_json = {}

    message = response_json.get("step_4", {}).get(
        "final_draft", "No final draft available."
    )
    return message, state


@cl.on_message
async def main(message: cl.Message) -> None:
    """
    Main function to handle incoming messages and manage the workflow.

    :param message: The incoming message from the user.
    """
    # Retrieve session variables
    # Add new agents to the session
    meta_agent = cl.user_session.get("meta_agent")
    serper_agent = cl.user_session.get("serper_agent")
    web_scraper_agent = cl.user_session.get("web_scraper_agent")
    offline_rag_websearch_agent = cl.user_session.get("offline_rag_websearch_agent")  # noqa: E501
    reporter_agent = cl.user_session.get("reporter_agent")
    serper_shopping_agent = cl.user_session.get("serper_shopping_agent")
    chat_model = cl.user_session.get("chat_model")
    system_prompt = cl.user_session.get("system_prompt")
    conversation_history = cl.user_session.get(
        "conversation_history", default=[]
    )  # Default to empty list if not set
    state = cl.user_session.get("state")

    if state:
        previous_work = state.get("reporter_agent", "No response from ReporterAgent")[  # noqa: E501
            -1
        ].page_content
        print(
            colored(
                text=(
                    f"\n\nDEBUG REPORTER AGENT WORK FEEDBACK: {previous_work}\n\n"  # noqa: E501
                    f"Type: {type(previous_work)}\n\n"
                ),
                color="red",
            )
        )
        system_prompt = f"{system_prompt}\n\nLast message from the agent:\n<prev_work>{previous_work}</prev_work>"  # noqa: E501

    # Add new agents to the agent_team
    agent_team = [
        meta_agent,
        serper_agent,
        serper_shopping_agent,
        web_scraper_agent,
        offline_rag_websearch_agent,
        reporter_agent,
    ]
    # agent_team = [meta_agent, serper_agent, offline_rag_websearch_agent, reporter_agent] # noqa: E501
    configs = {"recursion_limit": 50, "configurable": {"thread_id": 42}}

    # Append the new user message to the conversation history
    conversation_history.append({"role": "user", "content": message.content})

    # Prepare messages for the chat model,
    # including the full conversation history
    messages = [
        {"role": "system", "content": system_prompt},
    ] + conversation_history  # Include the full conversation history

    chat_model_response = chat_model.invoke(messages)
    await cl.Message(content=chat_model_response, author="Meta Expert👩‍💻").send()  # noqa: E501

    # Append the assistant's response to the conversation history
    conversation_history.append({"role": "assistant", "content": chat_model_response})  # noqa: E501

    # Update the conversation history in the session
    cl.user_session.set(key="conversation_history", value=conversation_history)

    if message.content == "/end":
        loop = asyncio.get_running_loop()

        formatted_requirements = "\n\n".join(
            re.findall(
                pattern=r"```python\s*([\s\S]*?)\s*```",
                string=chat_model_response,
                flags=re.MULTILINE,
            )
        )

        print(
            colored(
                text=f"\n\n User Requirements: {formatted_requirements}\n\n",
                color="green",
            )
        )

        workflow, state = await loop.run_in_executor(
            None,
            build_chat_workflow,
            agent_team,
            formatted_requirements,
            configs,
        )

        # Save state & workflow to session before running
        cl.user_session.set("state", state)
        cl.user_session.set("workflow", workflow)

        await cl.Message(
            content="This will take some time, probably a good time for a coffee break ☕...",  # noqa: E501
            author="System",
        ).send()

        message, state = await run_workflow(
            workflow=workflow, state=state, configs=configs
        )

        # Update state in session after running
        cl.user_session.set("state", state)
        cl.user_session

        print(colored(text=f"\n\nDEBUG AFTER RUN STATE: {state}\n\n", color="red"))  # noqa: E501

        await cl.Message(content=message, author="MetaExpert").send()
    else:
        # Update the state in user session
        cl.user_session.set("state", state)


# if __name__ == "__main__":
#     # Create an instance of SerperDevAgent for testing
#     # agent = SerperDevAgent("TestSerperAgent")

#     serper_agent = SerperDevAgent(
#         name="serper_agent",
#         server="openai",
#         model="gpt-4o-mini",
#         temperature=0,
#     )

#     # Create a sample tool response
#     test_tool_response = {
#         "queries": ["Python programming", "Machine learning basics"],
#         "location": "us",
#     }

#     # Create a sample state (can be None or an empty dict for this test)
#     test_state = {}

#     # Execute the tool and print the results
#     try:
#         results = serper_agent.execute_tool(
#             tool_response=test_tool_response,
#             state=test_state,
#         )
#         print("Search Results:")
#         print(results)
#     except Exception as e:
#         print(f"An error occurred: {e}")
