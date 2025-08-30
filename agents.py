"""
agents.py - Agent definitions for the exact flow specification
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_mistralai import ChatMistralAI
from tools import (
    fs_read, fs_list, fs_write_patch, proc_run, http_probe, pkg_scripts, python_test_runner
)

# Import prompts
from prompts import (
    GLOBAL_SYSTEM_PROMPT,
    PLANNER_PROMPT,
    ARCHITECT_PROMPT,
    CODER_PROMPT,
    TESTER_PROMPT,
    REVIEWER_PROMPT,
    FIXER_PROMPT,
    CONDUCTOR_PROMPT
)

# LLM setup
llm = ChatMistralAI(
    model="mistral-large-latest",
    temperature=0.2,
    max_tokens=2048,
)

# Agent prompt templates
planner_prompt = ChatPromptTemplate.from_messages([
    ("system", GLOBAL_SYSTEM_PROMPT),
    ("system", PLANNER_PROMPT),
    ("human", "user_prompt:\n{user_prompt}")
])

architect_prompt = ChatPromptTemplate.from_messages([
    ("system", GLOBAL_SYSTEM_PROMPT),
    ("system", ARCHITECT_PROMPT),
    ("human", "plan:\n{plan}\n\nuser_prompt:\n{user_prompt}")
])

coder_prompt = ChatPromptTemplate.from_messages([
    ("system", GLOBAL_SYSTEM_PROMPT),
    ("system", CODER_PROMPT),
    ("human", "spec:\n{spec}")
])

tester_prompt = ChatPromptTemplate.from_messages([
    ("system", GLOBAL_SYSTEM_PROMPT),
    ("system", TESTER_PROMPT),
    ("human", "spec:\n{spec}\n\nworkspace:\n{workspace_tree}")
])

reviewer_prompt = ChatPromptTemplate.from_messages([
    ("system", GLOBAL_SYSTEM_PROMPT),
    ("system", REVIEWER_PROMPT),
    ("human", "spec:\n{spec}\n\ntest_output:\n{test_output}\n\ncode_summary:\n{code_summary}")
])

fixer_prompt = ChatPromptTemplate.from_messages([
    ("system", GLOBAL_SYSTEM_PROMPT),
    ("system", FIXER_PROMPT),
    ("human", "spec:\n{spec}\n\nreview:\n{review}\n\ntest_output:\n{test_output}\n\nchanged_files:\n{changed_files}")
])

conductor_prompt = ChatPromptTemplate.from_messages([
    ("system", GLOBAL_SYSTEM_PROMPT),
    ("system", CONDUCTOR_PROMPT),
    ("human", "state:\n{state_snapshot}")
])

# Create agents
planner = planner_prompt | llm
architect = architect_prompt | llm

# Bind tools to LLMs for agents that need them
llm_coder = llm.bind_tools([fs_read, fs_list, fs_write_patch])
coder = coder_prompt | llm_coder

llm_tester = llm.bind_tools([fs_read, fs_list, python_test_runner, pkg_scripts, proc_run])
tester = tester_prompt | llm_tester

reviewer = reviewer_prompt | llm

llm_fixer = llm.bind_tools([fs_read, fs_list, fs_write_patch])
fixer = fixer_prompt | llm_fixer

llm_conductor = llm.bind_tools([fs_read, fs_list, fs_write_patch, proc_run, http_probe, pkg_scripts])
conductor = conductor_prompt | llm_conductor
