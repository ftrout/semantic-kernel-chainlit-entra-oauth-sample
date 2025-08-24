import asyncio
import jwt
from dotenv import load_dotenv
from typing import Dict, Optional
import chainlit as cl
import os

from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion, OpenAIChatPromptExecutionSettings
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.utils.logging import setup_logging

load_dotenv()

request_settings = OpenAIChatPromptExecutionSettings(
    function_choice_behavior=FunctionChoiceBehavior.Auto(filters={"excluded_plugins": ["ChatBot"]})
)

@cl.oauth_callback
def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: Dict[str, str],
    default_user: cl.User,
    id_token: Optional[str] = None
) -> Optional[cl.User]:
    
    if provider_id != "azure-ad":
        return None
    
    if not raw_user_data:
        return None
    
    # Use Microsoft Graph field names
    identifier = (
        raw_user_data.get("userPrincipalName") or
        raw_user_data.get("mail") or  
        raw_user_data.get("id")
    )
    
    if not identifier:
        return None
    
    return cl.User(
        identifier=identifier,
        metadata={
            "name": raw_user_data.get("displayName", identifier),
            "email": raw_user_data.get("mail"),
            "provider": "azure-ad",
            "azure_id": raw_user_data.get("id"),
        }
    )

@cl.on_chat_start
async def on_chat_start():
    try:
        # Initialize kernel and chat history regardless of user authentication
        kernel = Kernel()
        service = OpenAIChatCompletion()
        kernel.add_service(service)
        chat_history = ChatHistory()
        
        # Store in session
        cl.user_session.set("kernel", kernel)
        cl.user_session.set("service", service)
        cl.user_session.set("chat_history", chat_history)
        
        app_user = cl.user_session.get("user")
        if not app_user:
            await cl.Message(
                content="Unlock Cloodio’s Cybersecurity AI! Sign in with your Microsoft account.",
                elements=[
                    cl.Text(
                        name="unauthenticated_message",
                        content="Unlock Cloodio’s Cybersecurity AI! Sign in with your Microsoft account.",
                        display="inline",
                        styles={"text-align": "center", "color": "#0078d4", "font-size": "16px", "font-weight": "300"}
                    )
                ]
            ).send()
            return
        
        await cl.Message(
            content=f"Hello, {app_user.metadata['name']}! Cloodio’s Cybersecurity AI is ready to assist you.",
            elements=[
                cl.Text(
                    name="welcome_message",
                    content=f"Hello, {app_user.metadata['name']}! Cloodio’s Cybersecurity AI is ready to assist you.",
                    display="inline",
                    styles={"text-align": "center", "color": "#0078d4", "font-size": "16px", "font-weight": "300"}
                )
            ]
        ).send()
        
    except Exception as e:
        print(f"Error in on_chat_start: {str(e)}")
        await cl.Message(f"Failed to initialize chat: {str(e)}. Please try again.").send()

@cl.on_message
async def on_message(message: cl.Message):
    kernel = cl.user_session.get("kernel")
    service = cl.user_session.get("service")
    chat_history = cl.user_session.get("chat_history")

    # Safeguard against None values
    if not all([kernel, service, chat_history]):
        await cl.Message("Session not properly initialized. Please restart the chat.").send()
        return

    # Add user message to history
    chat_history.add_user_message(message.content)

    # Create a Chainlit message for the response stream
    answer = cl.Message(content="")

    async for msg in service.get_streaming_chat_message_content(
        chat_history=chat_history,
        user_input=message.content,
        settings=request_settings,
        kernel=kernel,
    ):
        if msg.content:
            await answer.stream_token(msg.content)

    # Add the full assistant response to history
    chat_history.add_assistant_message(answer.content)

    # Send the final message
    await answer.send()