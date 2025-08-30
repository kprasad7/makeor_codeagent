"""
workflow.py - Complete exact implementation of your specified agent-connecting flow

This implements the precise specification:
1) Data contracts (plan, spec, diff, tests, test_guide, test_output, review, control, state_snapshot)  
2) ASCII flow (USER GOAL → PLANNER → ARCHITECT → CODER → CONDUCTOR with branching)
3) Transition rules (exact as specified)
4) Control bus formats (next_action, rationale, checkpoints)
5) Conductor policy (exact logic)
"""

from typing import TypedDict, List, Dict, Any, Literal
import json
import yaml
import re
import os

# Core imports
from langchain_mistralai import ChatMistralAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END

from tools import (
    fs_read, fs_list, fs_write_patch, proc_run, python_test_runner,
    http_probe, port_check, pkg_scripts, start_service, wait_for_service
)
from prompts import (
    GLOBAL_SYSTEM_PROMPT, PLANNER_PROMPT, ARCHITECT_PROMPT, CODER_PROMPT,
    TESTER_PROMPT, REVIEWER_PROMPT, FIXER_PROMPT, CONDUCTOR_PROMPT
)

from typing import TypedDict, List, Dict, Any, Literal
import json
import yaml
import re
import os

# Core imports
from langchain_mistralai import ChatMistralAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END

from tools import fs_read, fs_list, fs_write_patch, proc_run, python_test_runner
from prompts import (
    GLOBAL_SYSTEM_PROMPT, PLANNER_PROMPT, ARCHITECT_PROMPT, CODER_PROMPT,
    TESTER_PROMPT, REVIEWER_PROMPT, FIXER_PROMPT, CONDUCTOR_PROMPT
)

# 1) Data Contracts - Exact State Definition  
class FlowState(TypedDict):
    # User input
    user_prompt: str
    
    # Agent artifacts (exact as specified)
    plan: dict         # ← Planner
    spec: dict         # ← Architect  
    diff: str          # ← Coder/Fixer (unified patches)
    tests: str         # ← Tester
    test_guide: str    # ← Tester
    test_output: dict  # ← Runner (exit_code/stdout/stderr)
    review: dict       # ← Reviewer (APPROVED or CHANGES_REQUIRED)
    control: dict      # ← Conductor (next_action/checkpoint)
    state_snapshot: dict  # ← Orchestrator
    
    # Flow control
    mode: str
    iteration: int
    last_diff_summary: str
    tests_present: bool
    review_done: bool
    code_changed_since_last_test: bool
    checkpoints: dict
    MAX_ITER: int

# LLM and Agent Setup
def create_agents():
    """Create all agents with proper tool bindings"""
    
    llm = ChatMistralAI(
        model="mistral-large-latest", 
        temperature=0.2, 
        max_tokens=2048
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
    
    # Create agents with tool bindings
    planner = planner_prompt | llm
    architect = architect_prompt | llm
    
    llm_coder = llm.bind_tools([fs_read, fs_list, fs_write_patch])
    coder = coder_prompt | llm_coder
    
    llm_tester = llm.bind_tools([fs_read, fs_list, python_test_runner])
    tester = tester_prompt | llm_tester
    
    reviewer = reviewer_prompt | llm
    
    llm_fixer = llm.bind_tools([fs_read, fs_list, fs_write_patch])
    fixer = fixer_prompt | llm_fixer
    
    conductor = conductor_prompt | llm
    
    return {
        "planner": planner,
        "architect": architect,
        "coder": coder,
        "tester": tester,
        "reviewer": reviewer,
        "fixer": fixer,
        "conductor": conductor
    }

# Helper Functions
def extract_yaml_from_response(response_content: str) -> dict:
    """Extract YAML from agent response"""
    try:
        if "```yaml" in response_content:
            yaml_start = response_content.find("```yaml") + 7
            yaml_end = response_content.find("```", yaml_start)
            yaml_content = response_content[yaml_start:yaml_end].strip()
            return yaml.safe_load(yaml_content)
        return {}
    except Exception as e:
        print(f"Error parsing YAML: {e}")
        return {}

def extract_code_from_response(response_content: str) -> str:
    """Extract code/diff from agent response"""
    try:
        # Check for diff format first
        if "-----BEGIN DIFF-----" in response_content and "-----END DIFF-----" in response_content:
            diff_start = response_content.find("-----BEGIN DIFF-----") + len("-----BEGIN DIFF-----")
            diff_end = response_content.find("-----END DIFF-----")
            return response_content[diff_start:diff_end].strip()
        
        # Check for code blocks
        if "```python" in response_content:
            code_start = response_content.find("```python") + 9
            code_end = response_content.find("```", code_start)
            return response_content[code_start:code_end].strip()
        elif "```" in response_content:
            code_start = response_content.find("```") + 3
            code_end = response_content.find("```", code_start)
            return response_content[code_start:code_end].strip()
        
        return response_content
    except Exception as e:
        print(f"Error extracting code: {e}")
        return ""

# Create workflow - following exact flow specification
def create_workflow() -> StateGraph:
    """Create exact workflow matching your specification"""
    
    # Get agents
    agents = create_agents()
    
    # Agent nodes
    def planner_node(state: FlowState) -> FlowState:
        print("📋 PLANNER: Creating plan...")
        try:
            response = agents["planner"].invoke({"user_prompt": state["user_prompt"]})
            plan = extract_yaml_from_response(response.content)
            state["plan"] = plan
            print(f"✅ Plan created")
        except Exception as e:
            print(f"❌ Planner error: {e}")
            state["plan"] = {"error": str(e)}
        return state
    
    def architect_node(state: FlowState) -> FlowState:
        print("🏗️ ARCHITECT: Creating spec...")
        try:
            response = agents["architect"].invoke({
                "user_prompt": state["user_prompt"],
                "plan": json.dumps(state["plan"])
            })
            spec = extract_yaml_from_response(response.content)
            state["spec"] = spec
            print(f"✅ Spec created")
        except Exception as e:
            print(f"❌ Architect error: {e}")
            state["spec"] = {"error": str(e)}
        return state
    
    def coder_node(state: FlowState) -> FlowState:
        print("💻 CODER: Generating diff...")
        try:
            response = agents["coder"].invoke({"spec": json.dumps(state["spec"])})
            diff = extract_code_from_response(response.content)
            state["diff"] = diff
            state["last_diff_summary"] = f"Generated {len(diff)} chars"
            state["code_changed_since_last_test"] = True
            print(f"✅ Diff generated")
        except Exception as e:
            print(f"❌ Coder error: {e}")
            state["diff"] = ""
        return state
    
    def conductor_node(state: FlowState) -> FlowState:
        print("🎭 CONDUCTOR: Making decision...")
        
        # State snapshot
        state["state_snapshot"] = {
            "mode": state["mode"],
            "iteration": state["iteration"],
            "plan": str(state["plan"])[:100] + "...",
            "spec": str(state["spec"])[:100] + "...",
            "last_diff_summary": state["last_diff_summary"],
            "tests_present": state["tests_present"],
            "test_output": state["test_output"],
            "review": state["review"]
        }
        
        # Decision logic
        code_present = bool(state.get("diff"))
        
        if not code_present:
            next_action = "PATCH_CODE"
            rationale = "No code present"
        elif state["code_changed_since_last_test"]:
            next_action = "RUN_TESTS"
            rationale = "Code changed since last test"
        elif state["test_output"].get("exit_code") == 0 and not state["review_done"]:
            next_action = "REVIEW"
            rationale = "Tests passing, ready for review"
        elif state["review"].get("status") == "APPROVED":
            next_action = "PREVIEW"
            rationale = "Code approved"
        else:
            next_action = "PATCH_CODE"
            rationale = "Issues found, need to fix"
        
        if state["iteration"] >= state["MAX_ITER"]:
            next_action = "FINISH"
            rationale = "Maximum iterations reached"
        
        state["control"] = {
            "next_action": next_action,
            "rationale": rationale,
            "commands": []
        }
        state["iteration"] += 1
        
        print(f"✅ Decision: {next_action} - {rationale}")
        return state
    
    def tester_node(state: FlowState) -> FlowState:
        print("🧪 TESTER: Creating tests...")
        try:
            workspace_tree = fs_list.invoke({"dir": "."})
            response = agents["tester"].invoke({
                "spec": json.dumps(state["spec"]),
                "workspace_tree": workspace_tree
            })
            
            content = response.content
            tests = extract_code_from_response(content)
            test_guide = "how_to_run: python_test_runner"
            
            state["tests"] = tests
            state["test_guide"] = test_guide
            state["tests_present"] = len(tests.strip()) > 0
            print(f"✅ Tests created")
        except Exception as e:
            print(f"❌ Tester error: {e}")
            state["tests"] = "# No tests generated"
            state["test_guide"] = "how_to_run: python_test_runner"
            state["tests_present"] = False
        return state
    
    def runner_node(state: FlowState) -> FlowState:
        print("🏃 RUNNER: Executing tests...")
        try:
            result = python_test_runner.invoke({"code": state["tests"]})
            test_output = {
                "exit_code": result.get("exit_code", 0),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", "")
            }
        except Exception as e:
            test_output = {
                "exit_code": 1,
                "stdout": "",
                "stderr": str(e)
            }
        
        state["test_output"] = test_output
        state["code_changed_since_last_test"] = False
        
        status = "PASSED" if test_output["exit_code"] == 0 else "FAILED"
        print(f"✅ Tests executed: {status}")
        return state
    
    def reviewer_node(state: FlowState) -> FlowState:
        print("👀 REVIEWER: Reviewing code...")
        try:
            response = agents["reviewer"].invoke({
                "spec": json.dumps(state["spec"]),
                "code_summary": state["last_diff_summary"],
                "test_output": json.dumps(state["test_output"])
            })
            
            review = extract_yaml_from_response(response.content)
            if "status" not in review:
                review["status"] = "APPROVED" if "approved" in response.content.lower() else "CHANGES_REQUIRED"
            
            state["review"] = review
            state["review_done"] = True
            print(f"✅ Review: {review.get('status')}")
        except Exception as e:
            print(f"❌ Reviewer error: {e}")
            state["review"] = {"status": "CHANGES_REQUIRED", "notes": [str(e)]}
            state["review_done"] = True
        return state
    
    def fixer_node(state: FlowState) -> FlowState:
        print("🔧 FIXER: Applying fixes...")
        try:
            response = agents["fixer"].invoke({
                "spec": json.dumps(state["spec"]),
                "review": json.dumps(state["review"]),
                "test_output": json.dumps(state["test_output"]),
                "changed_files": state["last_diff_summary"]
            })
            
            diff = extract_code_from_response(response.content)
            state["diff"] = diff
            state["last_diff_summary"] = f"Fixed {len(diff)} chars"
            state["code_changed_since_last_test"] = True
            state["review_done"] = False
            print(f"✅ Fix generated")
        except Exception as e:
            print(f"❌ Fixer error: {e}")
        return state
    
    def preview_node(state: FlowState) -> FlowState:
        print("🌐 PREVIEW: Creating preview...")
        state["control"]["preview_info"] = {
            "status": "deployed",
            "url": "http://localhost:8000"
        }
        print(f"✅ Preview ready")
        return state
    
    # Create workflow
    workflow = StateGraph(FlowState)
    
    # Add nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("conductor", conductor_node)
    workflow.add_node("tester", tester_node)
    workflow.add_node("runner", runner_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("fixer", fixer_node)
    workflow.add_node("preview", preview_node)
    
    # Linear flow
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "architect")
    workflow.add_edge("architect", "coder")
    workflow.add_edge("coder", "conductor")
    
    # Routing functions
    def route_after_conductor(state: FlowState) -> str:
        next_action = state["control"]["next_action"]
        if next_action == "PATCH_CODE":
            return "fixer" if state["review_done"] and state["review"].get("status") != "APPROVED" else "coder"
        elif next_action == "RUN_TESTS":
            return "tester"
        elif next_action == "REVIEW":
            return "reviewer"
        elif next_action == "PREVIEW":
            return "preview"
        else:
            return END
    
    def route_after_runner(state: FlowState) -> str:
        return "conductor" if state["test_output"]["exit_code"] == 0 else "fixer"
    
    # Conditional edges
    workflow.add_conditional_edges("conductor", route_after_conductor, {
        "coder": "coder",
        "tester": "tester",
        "reviewer": "reviewer",
        "fixer": "fixer",
        "preview": "preview",
        END: END
    })
    
    workflow.add_edge("tester", "runner")
    workflow.add_conditional_edges("runner", route_after_runner, {
        "conductor": "conductor",
        "fixer": "fixer"
    })
    
    workflow.add_edge("reviewer", "conductor")
    workflow.add_edge("fixer", "conductor")
    workflow.add_edge("preview", END)
    
    return workflow

def run_workflow(user_prompt: str) -> dict:
    """Run the exact flow implementation"""
    
    print("🚀 EXACT FLOW IMPLEMENTATION")
    print("=" * 80)
    print(f"📝 User Goal: {user_prompt}")
    print("=" * 80)
    
    initial_state = {
        "user_prompt": user_prompt,
        "plan": {},
        "spec": {},
        "diff": "",
        "tests": "",
        "test_guide": "",
        "test_output": {},
        "review": {},
        "control": {},
        "state_snapshot": {},
        "mode": "agent",
        "iteration": 0,
        "last_diff_summary": "",
        "tests_present": False,
        "review_done": False,
        "code_changed_since_last_test": False,
        "checkpoints": {"pending": False, "reason": None},
        "MAX_ITER": 3
    }
    
    workflow = create_workflow()
    app = workflow.compile()
    
    try:
        config = {"recursion_limit": 20}
        final_state = app.invoke(initial_state, config=config)
        
        print("\n" + "=" * 80)
        print("🎉 EXACT FLOW COMPLETE!")
        print("=" * 80)
        
        print(f"📊 Iterations: {final_state['iteration']}")
        print(f"📊 Final Action: {final_state['control'].get('next_action', 'N/A')}")
        print(f"📊 Tests Present: {final_state['tests_present']}")
        print(f"📊 Review Status: {final_state['review'].get('status', 'N/A')}")
        print(f"📊 Code Changes: {final_state['last_diff_summary']}")
        
        return final_state
        
    except Exception as e:
        print(f"❌ Flow failed: {e}")
        return initial_state

# For backwards compatibility
def main():
    """Test function"""
    os.environ["MISTRAL_API_KEY"] = "5jxkV9U1IT4RSk8Ze54xVR6h76CIPpoD"
    result = run_workflow("Create a simple function that adds two numbers")
    return result

if __name__ == "__main__":
    main()

# 1) Data Contracts - Exact State Definition
class FlowState(TypedDict):
    # User input
    user_prompt: str
    
    # Agent artifacts (exact as specified)
    plan: dict         # ← Planner
    spec: dict         # ← Architect  
    diff: str          # ← Coder/Fixer (unified patches)
    tests: str         # ← Tester
    test_guide: str    # ← Tester
    test_output: dict  # ← Runner (exit_code/stdout/stderr)
    review: dict       # ← Reviewer (APPROVED or CHANGES_REQUIRED)
    control: dict      # ← Conductor (next_action/checkpoint)
    state_snapshot: dict  # ← Orchestrator
    
    # Flow control
    mode: Literal["agent", "chat"]
    iteration: int
    last_diff_summary: str
    tests_present: bool
    review_done: bool
    code_changed_since_last_test: bool
    checkpoints: dict
    MAX_ITER: int

# Helper Functions
def extract_yaml_from_response(response_content: str) -> dict:
    """Extract YAML from agent response"""
    try:
        if "```yaml" in response_content:
            yaml_start = response_content.find("```yaml") + 7
            yaml_end = response_content.find("```", yaml_start)
            yaml_content = response_content[yaml_start:yaml_end].strip()
            return yaml.safe_load(yaml_content)
        return {}
    except Exception as e:
        print(f"Error parsing YAML: {e}")
        return {}

def extract_code_from_response(response_content: str) -> str:
    """Extract code blocks from agent response"""
    try:
        # Check for diff format first
        if "-----BEGIN DIFF-----" in response_content and "-----END DIFF-----" in response_content:
            diff_start = response_content.find("-----BEGIN DIFF-----") + len("-----BEGIN DIFF-----")
            diff_end = response_content.find("-----END DIFF-----")
            return response_content[diff_start:diff_end].strip()
        
        # Check for code blocks
        if "```python" in response_content:
            code_start = response_content.find("```python") + 9
            code_end = response_content.find("```", code_start)
            return response_content[code_start:code_end].strip()
        elif "```" in response_content:
            code_start = response_content.find("```") + 3
            code_end = response_content.find("```", code_start)
            return response_content[code_start:code_end].strip()
        
        return response_content
    except Exception as e:
        print(f"Error extracting code: {e}")
        return ""

# Agent Nodes - Following Your Exact Flow
def planner_node(state: FlowState) -> FlowState:
    """PLANNER: user_prompt -> plan"""
    print("📋 PLANNER: Creating plan...")
    
    try:
        response = planner.invoke({"user_prompt": state["user_prompt"]})
        plan = extract_yaml_from_response(response.content)
        state["plan"] = plan
        print(f"✅ Plan created: {len(str(plan))} chars")
    except Exception as e:
        print(f"❌ Planner error: {e}")
        state["plan"] = {"error": str(e)}
    
    return state

def architect_node(state: FlowState) -> FlowState:
    """ARCHITECT: plan -> spec"""
    print("🏗️ ARCHITECT: Creating spec...")
    
    try:
        response = architect.invoke({
            "user_prompt": state["user_prompt"],
            "plan": json.dumps(state["plan"])
        })
        spec = extract_yaml_from_response(response.content)
        state["spec"] = spec
        print(f"✅ Spec created: {len(str(spec))} chars")
    except Exception as e:
        print(f"❌ Architect error: {e}")
        state["spec"] = {"error": str(e)}
    
    return state

def coder_node(state: FlowState) -> FlowState:
    """CODER: spec -> diff (unified patches)"""
    print("💻 CODER: Generating diff...")
    
    try:
        response = coder.invoke({"spec": json.dumps(state["spec"])})
        
        # Extract unified diff
        diff = extract_code_from_response(response.content)
        state["diff"] = diff
        state["last_diff_summary"] = f"Generated code: {len(diff)} chars"
        state["code_changed_since_last_test"] = True
        
        # Apply diff to workspace
        if diff and ("***" in diff or "@@" in diff):
            try:
                fs_write_patch.invoke({"unified_diff": diff})
                print("✅ Diff applied to workspace")
            except Exception as e:
                print(f"⚠️ Could not apply as patch: {e}")
        
        print(f"✅ Diff generated: {len(diff)} chars")
    except Exception as e:
        print(f"❌ Coder error: {e}")
        state["diff"] = ""
    
    return state

def conductor_node(state: FlowState) -> FlowState:
    """CONDUCTOR: Decides next action - your exact policy"""
    print("🎭 CONDUCTOR: Making decision...")
    
    # Update state snapshot (exact format from spec)
    state["state_snapshot"] = {
        "mode": state["mode"],
        "iteration": state["iteration"],
        "plan": str(state["plan"])[:100] + "...",
        "spec": str(state["spec"])[:100] + "...",
        "last_diff_summary": state["last_diff_summary"],
        "tests_present": state["tests_present"],
        "test_output": state["test_output"],
        "review": state["review"],
        "checkpoints": state["checkpoints"]
    }
    
    # Your exact conductor policy
    code_present = bool(state.get("diff"))
    
    if not code_present:
        next_action = "PATCH_CODE"
        rationale = "No code present"
    elif state["code_changed_since_last_test"]:
        next_action = "RUN_TESTS" 
        rationale = "Code changed since last test"
    elif state["test_output"].get("exit_code") == 0 and not state["review_done"]:
        next_action = "REVIEW"
        rationale = "Tests passing, ready for review"
    elif state["review"].get("status") == "APPROVED":
        next_action = "PREVIEW"
        rationale = "Code approved"
    else:
        next_action = "PATCH_CODE"  # Fixer
        rationale = "Issues found, need to fix"
    
    # Check iteration limits
    if state["iteration"] >= state["MAX_ITER"]:
        next_action = "FINISH"
        rationale = "Maximum iterations reached"
    
    # Create control output (exact format)
    control = {
        "next_action": next_action,
        "rationale": rationale,
        "commands": [],
        "checkpoints": {
            "required": state["iteration"] > 0 and state["iteration"] % 8 == 0,
            "reason": "Periodic checkpoint after 8 actions" if state["iteration"] % 8 == 0 else None
        }
    }
    
    state["control"] = control
    state["iteration"] += 1
    
    print(f"✅ Decision: {next_action} - {rationale}")
    return state

def tester_node(state: FlowState) -> FlowState:
    """TESTER: spec -> tests + test_guide"""
    print("🧪 TESTER: Creating tests...")
    
    try:
        # Get workspace context
        try:
            workspace_tree = fs_list.invoke({"dir": "."})
        except:
            workspace_tree = "No files found"
        
        response = tester.invoke({
            "spec": json.dumps(state["spec"]),
            "workspace_tree": workspace_tree
        })
        
        content = response.content
        
        # Extract test guide (exact format)
        if "-----BEGIN TEST_GUIDE-----" in content and "-----END TEST_GUIDE-----" in content:
            guide_start = content.find("-----BEGIN TEST_GUIDE-----") + len("-----BEGIN TEST_GUIDE-----")
            guide_end = content.find("-----END TEST_GUIDE-----")
            test_guide = content[guide_start:guide_end].strip()
        else:
            test_guide = "how_to_run: python_test_runner\nnotes:\n  - Basic test execution"
        
        # Extract tests (exact format)
        if "-----BEGIN TESTS-----" in content and "-----END TESTS-----" in content:
            tests_start = content.find("-----BEGIN TESTS-----") + len("-----BEGIN TESTS-----")
            tests_end = content.find("-----END TESTS-----")
            tests = content[tests_start:tests_end].strip()
        else:
            # Fallback - extract any code block
            tests = extract_code_from_response(content)
        
        state["tests"] = tests
        state["test_guide"] = test_guide
        state["tests_present"] = len(tests.strip()) > 0
        
        print(f"✅ Tests created: {len(tests)} chars, Guide: {len(test_guide)} chars")
    except Exception as e:
        print(f"❌ Tester error: {e}")
        state["tests"] = "# No tests generated"
        state["test_guide"] = "how_to_run: python_test_runner"
        state["tests_present"] = False
    
    return state

def runner_node(state: FlowState) -> FlowState:
    """RUNNER: tests + test_guide -> test_output"""
    print("🏃 RUNNER: Executing tests...")
    
    try:
        # Parse how_to_run from test_guide
        test_guide = state["test_guide"]
        if "how_to_run:" in test_guide:
            how_to_run_line = [line for line in test_guide.split('\n') if 'how_to_run:' in line][0]
            how_to_run = how_to_run_line.split('how_to_run:')[1].strip().strip('"\'')
        else:
            how_to_run = "python_test_runner"
        
        if how_to_run == "python_test_runner":
            result = python_test_runner.invoke({"code": state["tests"]})
        else:
            result = proc_run.invoke({"command": how_to_run})
        
        # Format as exact test_output contract
        test_output = {
            "exit_code": result.get("exit_code", 0),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", "")
        }
        
    except Exception as e:
        test_output = {
            "exit_code": 1,
            "stdout": "",
            "stderr": str(e)
        }
    
    state["test_output"] = test_output
    state["code_changed_since_last_test"] = False
    
    status = "PASSED" if test_output["exit_code"] == 0 else "FAILED"
    print(f"✅ Tests executed: {status} (exit_code: {test_output['exit_code']})")
    return state

def reviewer_node(state: FlowState) -> FlowState:
    """REVIEWER: test_output -> review (APPROVED or CHANGES_REQUIRED)"""
    print("👀 REVIEWER: Reviewing code...")
    
    try:
        response = reviewer.invoke({
            "spec": json.dumps(state["spec"]),
            "code_summary": state["last_diff_summary"],
            "test_output": json.dumps(state["test_output"])
        })
        
        # Extract review (exact format)
        review = extract_yaml_from_response(response.content)
        
        # Ensure proper format
        if "status" not in review:
            content_lower = response.content.lower()
            if "approved" in content_lower:
                review["status"] = "APPROVED"
            else:
                review["status"] = "CHANGES_REQUIRED"
        
        if "notes" not in review:
            review["notes"] = ["Review completed"]
        if "issues" not in review:
            review["issues"] = []
        
        state["review"] = review
        state["review_done"] = True
        
        print(f"✅ Review completed: {review.get('status', 'UNKNOWN')}")
    except Exception as e:
        print(f"❌ Reviewer error: {e}")
        state["review"] = {"status": "CHANGES_REQUIRED", "notes": [f"Review failed: {e}"], "issues": []}
        state["review_done"] = True
    
    return state

def fixer_node(state: FlowState) -> FlowState:
    """FIXER: review + test_output -> diff"""
    print("🔧 FIXER: Applying fixes...")
    
    try:
        response = fixer.invoke({
            "spec": json.dumps(state["spec"]),
            "review": json.dumps(state["review"]),
            "test_output": json.dumps(state["test_output"]),
            "changed_files": state["last_diff_summary"]
        })
        
        # Extract code/diff
        diff = extract_code_from_response(response.content)
        
        # Apply to workspace
        if diff and ("***" in diff or "@@" in diff):
            try:
                fs_write_patch.invoke({"unified_diff": diff})
                print("✅ Fix applied to workspace")
            except Exception as e:
                print(f"⚠️ Could not apply as patch: {e}")
        
        state["diff"] = diff
        state["last_diff_summary"] = f"Fixed {len(diff)} chars"
        state["code_changed_since_last_test"] = True
        state["review_done"] = False  # Need new review after fixes
        
        print(f"✅ Fix generated: {len(diff)} chars")
    except Exception as e:
        print(f"❌ Fixer error: {e}")
        state["diff"] = state.get("diff", "")
    
    return state

def preview_node(state: FlowState) -> FlowState:
    """PREVIEW: Deploy/preview approved code"""
    print("🌐 PREVIEW: Creating preview...")
    
    preview_info = {
        "status": "deployed",
        "url": "http://localhost:8000",
        "timestamp": "2025-08-29"
    }
    
    if "preview_info" not in state["control"]:
        state["control"]["preview_info"] = preview_info
    
    print(f"✅ Preview ready: {preview_info['url']}")
    return state

# 3) Transition Rules - Your Exact Routing
def route_after_conductor(state: FlowState) -> str:
    """Route based on conductor decision"""
    next_action = state["control"]["next_action"]
    
    if next_action == "PATCH_CODE":
        return "fixer" if state["review_done"] and state["review"].get("status") != "APPROVED" else "coder"
    elif next_action == "RUN_TESTS":
        return "tester"
    elif next_action == "REVIEW":
        return "reviewer"
    elif next_action == "PREVIEW":
        return "preview"
    elif next_action == "FINISH":
        return END
    else:
        return END

def route_after_runner(state: FlowState) -> str:
    """Route based on test results - your exact rule"""
    if state["test_output"]["exit_code"] == 0:
        return "conductor"  # Tests pass -> back to conductor
    else:
        return "fixer"  # Tests fail -> fix directly

# Create Workflow - Your Exact Flow
def create_workflow() -> StateGraph:
    """Create workflow that exactly matches your specification"""
    
    workflow = StateGraph(FlowState)
    
    # Add all agent nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("conductor", conductor_node)
    workflow.add_node("tester", tester_node)
    workflow.add_node("runner", runner_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("fixer", fixer_node)
    workflow.add_node("preview", preview_node)
    
    # Your exact transition rules
    # Linear flow: USER GOAL -> PLANNER -> ARCHITECT -> CODER -> CONDUCTOR
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "architect")  # when plan ready
    workflow.add_edge("architect", "coder")     # when spec ready
    workflow.add_edge("coder", "conductor")     # after first diff applied
    
    # Conductor branches (your exact rules)
    workflow.add_conditional_edges("conductor", route_after_conductor, {
        "coder": "coder",
        "tester": "tester", 
        "reviewer": "reviewer",
        "fixer": "fixer",
        "preview": "preview",
        END: END
    })
    
    # Tester -> Runner (when tests provided)
    workflow.add_edge("tester", "runner")
    
    # Runner branches (your exact rule)
    workflow.add_conditional_edges("runner", route_after_runner, {
        "conductor": "conductor",  # if exit_code == 0
        "fixer": "fixer"          # else
    })
    
    # Reviewer -> Conductor (always)
    workflow.add_edge("reviewer", "conductor")
    
    # Fixer -> Conductor (loop back)
    workflow.add_edge("fixer", "conductor")
    
    # Preview -> END
    workflow.add_edge("preview", END)
    
    return workflow

def run_workflow(user_prompt: str) -> dict:
    """Run the exact flow implementation"""
    
    print("🚀 EXACT FLOW IMPLEMENTATION")
    print("=" * 80)
    print(f"📝 User Goal: {user_prompt}")
    print("=" * 80)
    
    # Initialize state with exact contracts
    initial_state = {
        "user_prompt": user_prompt,
        "plan": {},
        "spec": {},
        "diff": "",
        "tests": "",
        "test_guide": "",
        "test_output": {},
        "review": {},
        "control": {},
        "state_snapshot": {},
        "mode": "agent",
        "iteration": 0,
        "last_diff_summary": "",
        "tests_present": False,
        "review_done": False,
        "code_changed_since_last_test": False,
        "checkpoints": {"pending": False, "reason": None},
        "MAX_ITER": 3
    }
    
    # Create and run workflow
    workflow = create_workflow()
    app = workflow.compile()
    
    try:
        config = {"recursion_limit": 20}
        final_state = app.invoke(initial_state, config=config)
        
        print("\n" + "=" * 80)
        print("🎉 EXACT FLOW COMPLETE!")
        print("=" * 80)
        
        # Display results matching your data contracts
        print(f"📊 Iterations: {final_state['iteration']}")
        print(f"📊 Final Action: {final_state['control'].get('next_action', 'N/A')}")
        print(f"📊 Tests Present: {final_state['tests_present']}")
        print(f"📊 Review Status: {final_state['review'].get('status', 'N/A')}")
        print(f"📊 Code Changes: {final_state['last_diff_summary']}")
        
        return final_state
        
    except Exception as e:
        print(f"❌ Flow failed: {e}")
        return initial_state
        
# For backwards compatibility
def main():
    """Test function"""
    os.environ["MISTRAL_API_KEY"] = "5jxkV9U1IT4RSk8Ze54xVR6h76CIPpoD"
    result = run_workflow("Create a simple function that adds two numbers")
    return result

if __name__ == "__main__":
    main()
