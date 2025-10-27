"""
writer.py

This module defines the multi-agent "Writer Team" responsible for all content
generation and revision tasks. It constructs and configures the agents and the
group chat manager that form this team.

The Writer Team's purpose is to synthesise information from the source documents
and follow detailed guidance to produce a structured markdown document for a
specific section. It operates in two modes: initial creation and correction,
where it refines a previous draft based on feedback.

The team consists of:
- Planner: A fast orchestrator agent that directs the workflow and ensures tasks are completed in order.
- Document_Writer: The specialist content generation agent that synthesises information and writes the draft.
- Writer_User_Proxy: The tool-executing agent for saving the final document to blob storage.
"""


import autogen
from autogen import ConversableAgent, UserProxyAgent, GroupChat, GroupChatManager
from typing import Dict
from ..utils.utils import (
    is_terminate_message,
    upload_blob_async
)

# This team is responsible for drafting the document
def create_writer_team(llm_config: Dict, llm_config_fast: Dict) -> GroupChatManager:
    """
    Creates and configures the writer multi-agent team.
    """
    writer_user_proxy = UserProxyAgent(
        name="Writer_User_Proxy",
        is_termination_msg=is_terminate_message,
        human_input_mode="NEVER",
        max_consecutive_auto_reply=30,
        code_execution_config={"work_dir": "outputs", "use_docker": False},
        llm_config=llm_config_fast,
        system_message="""You are the user proxy and tool executor for the writer team.
                        Your job is to execute tool calls as directed by the Planner (e.g., reading and saving files).
                        You must wait for the Planner to confirm the task is complete.
                        The Planner will signal the end of the task by replying with the single word 'TERMINATE'. Your termination condition is set to detect this word."""
    )

    document_writer = ConversableAgent(
        name="Document_Writer",
        llm_config=llm_config,
        system_message= """You are a professional document writer. Your job is to synthesise information from provided source documents into a final draft.

        Your primary directive is to **strictly and precisely follow all rules and instructions** provided to you in the user's prompt under the heading "writer's guidance". 
        This guidance is your absolute source of truth for formatting, structure, and content generation rules.
        
        **CRITICAL INSTRUCTION: CITE AS YOU WRITE**
        For every single piece of information, statement, or fact you write, you **MUST** append a citation tag that indicates the exact source document it came from.

        - The format is: `[SOURCE: <filename.txt>]`
        - The citation must be placed directly at the end of the sentence or phrase it applies to.
        - Do not add any conversational text, comments, or parentheses. Your entire response must be ONLY the document content with the required citation tags.

        **Execution Rules:**
        - If you receive a [REVISION_REQUEST], refine the document based ONLY on the revision instructions provided, while continuing to adhere to the original writer's guidance.
        - If you receive a [REVISION_REQUEST], apply the changes while preserving this citation format.

        ---
        **EXAMPLE:**

        **INSTEAD OF THIS:**
        **Name:** Gemma Saunders
        **Interests:** Gemma enjoys looking at books.

        **YOU MUST WRITE THIS:**
        **Name:** Gemma Saunders [SOURCE: Gemma Saunders app A (2).pdf.txt]
        **Interests:** Gemma enjoys looking at books. [SOURCE: Gemma Saunders SEND Support Review (2).pdf.txt]
        ---  
        """
    )

    planner = ConversableAgent(
        name="Planner",
        llm_config=llm_config_fast,
        system_message=
        
        """You are a meticulous planner. Your role is to create a step-by-step plan and ensure it is followed precisely.

        The initial prompt already contains all the necessary guidance and the relavent source documents. Your first step is to direct the drafting of the content.

        **Your plan is ALWAYS:**
        1.  **Draft Content:** Direct the `Document_Writer` to synthesise all the provided information to write the document. **You must explicitly remind the `Document_Writer` to strictly follow the writer's guidance.**
        3.  **Save Output:** After the `Document_Writer` has provided the complete draft, direct the `Writer_User_Proxy` to save the result using the `upload_blob_async` tool, specifying the exact container and blob name as instructed in the initial user prompt.
        4.  **Terminate:** After the save is confirmed, you MUST respond with the single word: "TERMINATE".

        You will output one step of the plan at a time and wait for it to be completed before announcing the next step. Do not combine steps."""
    )
 
    
    agent_tools = [
        upload_blob_async
    ]

    for func in agent_tools:
        description = f"{func.__doc__} The `container_name` argument is required."
        
        autogen.agentchat.register_function(
            func,
            caller=writer_user_proxy, 
            executor=writer_user_proxy, 
            name=func.__name__,
            description=description
        )
    
    # Create the group chat and manager
    groupchat = GroupChat(
        agents=[writer_user_proxy, document_writer, planner],
        messages=[],
        max_round=30
    )
    
    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=llm_config_fast,
        system_message="""You are the manager of a writing team. Your goal is to follow the Planner's simple plan to produce and save a single document.
                        """
    )
    
    return manager
