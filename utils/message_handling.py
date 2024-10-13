from langchain_core.messages import AIMessage

def get_ai_message_contents(conversation_history):
    """
    Extracts the content of AI messages from the conversation history.

    Args:
        conversation_history (list): A list of messages in the conversation history.

    Returns:
        list: A list of contents from AI messages.
    """
    return [message.content for message in conversation_history if isinstance(message, AIMessage)]
