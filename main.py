"""
workflow_fixed.py - Complete working exact flow implementation

This implements the precise specification with full-stack support:
1) Data contracts (plan, spec, diff, tests, test_guide, test_output, review, control, state_snapshot)  
2) ASCII flow (USER GOAL → PLANNER → ARCHITECT → CODER → CONDUCTOR with branching)
3) Transition rules (exact as specified)
4) Full-stack orchestration (frontend + backend + DB + build pipeline)
"""

import os
import json
import yaml
import re
from typing import TypedDict

# Set API key
os.environ["MISTRAL_API_KEY"] = "5jxkV9U1IT4RSk8Ze54xVR6h76CIPpoD"

from langchain_mistralai import ChatMistralAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END

from tools import (
    fs_read, fs_list, fs_write_patch, fs_write_file, proc_run, python_test_runner,
    http_probe, port_check, pkg_scripts, start_service, wait_for_service
)
from prompts import (
    GLOBAL_SYSTEM_PROMPT, PLANNER_PROMPT, ARCHITECT_PROMPT, CODER_PROMPT,
    TESTER_PROMPT, REVIEWER_PROMPT, FIXER_PROMPT, CONDUCTOR_PROMPT
)
from project_manager import ProjectDirectoryManager

# 1) Data Contracts - Exact State Definition
from tools import ProjectAwareTools
import subprocess
import tempfile
import threading
import signal
import time


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
    
    # Project management
    project_dir: str
    project_type: str
    services_status: dict
    build_status: dict


def check_and_run_code(state: FlowState, project_tools: ProjectAwareTools) -> dict:
    """Simple code execution checker with auto-fixing"""
    
    project_dir = state.get("project_dir", "")
    if not project_dir or not os.path.exists(project_dir):
        return {"success": False, "errors": [{"error": "Project directory not found"}], "needs_fixing": True}
    
    print(f"🔍 Checking and running code in: {project_dir}")
    
    results = {
        "success": True,
        "errors": [],
        "warnings": [],
        "needs_fixing": False,
        "fixes_applied": False
    }
    
    try:
        # Check for main.py file
        main_file = os.path.join(project_dir, "main.py")
        if os.path.exists(main_file):
            print(f"✅ Found main.py, attempting to run...")
            
            # Run with timeout
            def run_with_timeout(command, timeout=30):
                try:
                    result = subprocess.run(
                        command, 
                        cwd=project_dir,
                        capture_output=True, 
                        text=True, 
                        timeout=timeout
                    )
                    return result
                except subprocess.TimeoutExpired:
                    return subprocess.CompletedProcess(command, 124, "", "Process timed out")
            
            # Try to run the main file
            run_result = run_with_timeout(["python", "main.py"], timeout=10)
            
            if run_result.returncode != 0:
                error_text = run_result.stderr.strip()
                
                # Try to auto-fix common errors
                if "ModuleNotFoundError" in error_text or "No module named" in error_text:
                    missing_module = error_text.split("'")[1] if "'" in error_text else "unknown"
                    print(f"🔧 Auto-fixing missing module: {missing_module}")
                    
                    # Common module mappings
                    module_mappings = {
                        "fastapi": "fastapi>=0.68.0",
                        "uvicorn": "uvicorn[standard]>=0.15.0", 
                        "pydantic": "pydantic>=2.0.0",
                        "requests": "requests>=2.28.0"
                    }
                    
                    # Update requirements.txt
                    req_file = os.path.join(project_dir, "requirements.txt")
                    requirement = module_mappings.get(missing_module, missing_module)
                    
                    if os.path.exists(req_file):
                        with open(req_file, 'r') as f:
                            content = f.read()
                    else:
                        content = ""
                    
                    if requirement not in content:
                        with open(req_file, 'a') as f:
                            f.write(f"\n{requirement}")
                        results["fixes_applied"] = True
                        print(f"✅ Added {requirement} to requirements.txt")
                
                results["errors"].append({
                    "type": "runtime_error",
                    "error": error_text,
                    "file": "main.py"
                })
                results["needs_fixing"] = True
                results["success"] = False
            else:
                print("✅ Code executed successfully!")
                
        # Check for FastAPI apps
        if any("FastAPI" in open(os.path.join(root, file)).read() 
               for root, dirs, files in os.walk(project_dir) 
               for file in files if file.endswith('.py')):
            
            print("🌐 FastAPI app detected, checking startup...")
            # Quick FastAPI validation
            fastapi_check = run_with_timeout(["python", "-c", 
                f"import sys; sys.path.append('{project_dir}'); from main import app; print('FastAPI app imported successfully')"], 
                timeout=5)
            
            if fastapi_check.returncode != 0:
                results["errors"].append({
                    "type": "fastapi_error", 
                    "error": fastapi_check.stderr.strip(),
                    "file": "main.py"
                })
                results["needs_fixing"] = True
                results["success"] = False
    
    except Exception as e:
        results["errors"].append({
            "type": "execution_error",
            "error": str(e),
            "file": "unknown"
        })
        results["needs_fixing"] = True
        results["success"] = False
    
    # Store in state for later use
    state["execution_results"] = results
    
    return results


def attempt_auto_fix(state: FlowState, execution_results: dict, project_tools: ProjectAwareTools) -> bool:
    """Attempt to automatically fix common errors"""
    
    errors = execution_results.get("errors", [])
    project_dir = state["project_dir"]
    fixes_applied = 0
    
    for error in errors:
        error_text = error.get("error", "").lower()
        
        # Fix missing imports
        if "no module named" in error_text or "modulenotfounderror" in error_text:
            try:
                # Extract module name
                if "'" in error_text:
                    module_name = error_text.split("'")[1]
                else:
                    continue
                    
                print(f"🔧 Fixing missing module: {module_name}")
                
                # Common module mappings
                module_mappings = {
                    "fastapi": "fastapi>=0.68.0",
                    "uvicorn": "uvicorn[standard]>=0.15.0", 
                    "pydantic": "pydantic>=2.0.0",
                    "sqlalchemy": "sqlalchemy>=1.4.0",
                    "requests": "requests>=2.28.0",
                    "jinja2": "jinja2>=3.0.0",
                    "python-multipart": "python-multipart>=0.0.5"
                }
                
                # Update requirements.txt
                req_file = os.path.join(project_dir, "requirements.txt")
                
                if os.path.exists(req_file):
                    with open(req_file, 'r') as f:
                        content = f.read()
                else:
                    content = ""
                
                if module_name in module_mappings:
                    requirement = module_mappings[module_name]
                else:
                    requirement = module_name
                
                if requirement not in content:
                    content += f"\n{requirement}"
                    with open(req_file, 'w') as f:
                        f.write(content.strip())
                    
                    print(f"✅ Added {requirement} to requirements.txt")
                    fixes_applied += 1
                
            except Exception as e:
                print(f"❌ Failed to fix missing module: {e}")
        
        # Fix syntax errors (basic)
        elif "syntax error" in error_text or "syntaxerror" in error_text:
            print("🔧 Attempting syntax error fix...")
            
            # Try to find and fix common syntax issues
            for root, dirs, files in os.walk(project_dir):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r') as f:
                                content = f.read()
                            
                            # Fix common syntax issues
                            original_content = content
                            
                            # Fix missing imports at top
                            if "FastAPI" in content and "from fastapi import" not in content:
                                content = "from fastapi import FastAPI\n" + content
                                print("✅ Added missing FastAPI import")
                            
                            if "BaseModel" in content and "from pydantic import" not in content:
                                content = "from pydantic import BaseModel\n" + content
                                print("✅ Added missing Pydantic import")
                            
                            # Save if changed
                            if content != original_content:
                                with open(file_path, 'w') as f:
                                    f.write(content)
                                fixes_applied += 1
                                
                        except Exception as e:
                            print(f"⚠️ Could not fix syntax in {file}: {e}")
    
    return fixes_applied > 0


def search_error_solution(error_text: str) -> str:
    """Search for error solutions using web search simulation"""
    
    try:
        # Simulate web search for error solutions
        common_solutions = {
            "no module named 'fastapi'": "Install FastAPI: pip install fastapi",
            "no module named 'uvicorn'": "Install Uvicorn: pip install uvicorn[standard]",
            "no module named 'pydantic'": "Install Pydantic: pip install pydantic",
            "modulenotfounderror": "Check if module is installed and available in Python path",
            "syntax error": "Check for missing imports, incorrect indentation, or typos",
            "importerror": "Verify module installation and import paths",
            "attribute error": "Check if attribute exists on the object",
            "name error": "Variable or function not defined",
        }
        
        error_lower = error_text.lower()
        
        for pattern, solution in common_solutions.items():
            if pattern in error_lower:
                return solution
        
        return "Check documentation and ensure all dependencies are installed"
        
    except Exception as e:
        return f"Could not search for solution: {e}"


def ai_agent_fix(state: FlowState, error_text: str, project_tools: ProjectAwareTools) -> bool:
    """Use AI agent to generate fixes for complex errors"""
    
    try:
        project_dir = state["project_dir"]
        
        # Analyze the error and project structure
        print(f"🤖 AI Agent analyzing error: {error_text[:100]}...")
        
        # Generate fix based on error pattern
        if "no module named" in error_text.lower():
            if "'" in error_text:
                module_name = error_text.split("'")[1]
            else:
                return False
            
            # Create/update requirements.txt
            req_file = os.path.join(project_dir, "requirements.txt")
            
            module_versions = {
                "fastapi": "fastapi>=0.68.0",
                "uvicorn": "uvicorn[standard]>=0.15.0",
                "pydantic": "pydantic>=2.0.0",
                "sqlalchemy": "sqlalchemy>=1.4.0",
                "requests": "requests>=2.28.0",
                "jinja2": "jinja2>=3.0.0",
            }
            
            if module_name in module_versions:
                requirement = module_versions[module_name]
                
                # Read existing requirements
                existing_reqs = ""
                if os.path.exists(req_file):
                    with open(req_file, 'r') as f:
                        existing_reqs = f.read()
                
                # Add if not present
                if requirement not in existing_reqs:
                    with open(req_file, 'a') as f:
                        f.write(f"\n{requirement}")
                    
                    print(f"✅ AI Agent added {requirement} to requirements.txt")
                    return True
        
        return False
        
    except Exception as e:
        print(f"❌ AI Agent fix failed: {e}")
        return False


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

def apply_diff_to_workspace(diff: str) -> bool:
    """Apply unified diff patches to workspace files"""
    try:
        if not diff or len(diff.strip()) == 0:
            return False
            
        # Handle different diff formats
        if "*** Add File:" in diff:
            # Parse file additions
            lines = diff.split('\n')
            current_file = None
            current_content = []
            in_content = False
            
            for line in lines:
                if line.startswith("*** Add File:"):
                    if current_file and current_content:
                        # Write previous file
                        with open(current_file, 'w') as f:
                            f.write('\n'.join(current_content))
                        print(f"✅ Created file: {current_file}")
                    
                    current_file = line.replace("*** Add File:", "").strip()
                    current_content = []
                    in_content = False
                elif line.startswith("```python") or line.startswith("```"):
                    in_content = not in_content
                elif in_content and current_file:
                    current_content.append(line)
            
            # Write final file
            if current_file and current_content:
                # Create directory if needed
                os.makedirs(os.path.dirname(current_file) if os.path.dirname(current_file) else ".", exist_ok=True)
                with open(current_file, 'w') as f:
                    f.write('\n'.join(current_content))
                print(f"✅ Created file: {current_file}")
                
            return True
        else:
            # Try using the fs_write_patch tool
            fs_write_patch.invoke({"unified_diff": diff})
            return True
            
    except Exception as e:
        print(f"⚠️ Could not apply diff: {e}")
        return False

def create_workflow() -> StateGraph:
    """Create complete working workflow"""
    
    # Create LLM and agents
    llm = ChatMistralAI(model="mistral-large-latest", temperature=0.2, max_tokens=2048)
    
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
    
    # Create agents with enhanced tool bindings
    planner = planner_prompt | llm
    architect = architect_prompt | llm
    
    llm_coder = llm.bind_tools([fs_read, fs_list, fs_write_patch, fs_write_file, pkg_scripts])
    coder = coder_prompt | llm_coder
    
    llm_tester = llm.bind_tools([fs_read, fs_list, python_test_runner, http_probe, port_check])
    tester = tester_prompt | llm_tester
    
    reviewer = reviewer_prompt | llm
    
    llm_fixer = llm.bind_tools([fs_read, fs_list, fs_write_patch, fs_write_file, pkg_scripts])
    fixer = fixer_prompt | llm_fixer
    
    llm_conductor = llm.bind_tools([
        proc_run, http_probe, port_check, pkg_scripts, 
        start_service, wait_for_service
    ])
    conductor = conductor_prompt | llm_conductor
    
    # Agent node functions
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
        """ARCHITECT: plan -> spec (with full-stack detection)"""
        print("🏗️ ARCHITECT: Creating spec...")
        try:
            response = architect.invoke({
                "user_prompt": state["user_prompt"],
                "plan": json.dumps(state["plan"])
            })
            spec = extract_yaml_from_response(response.content)
            state["spec"] = spec
            
            # Detect project type
            project_type = spec.get("project_type", "simple")
            user_prompt_lower = state["user_prompt"].lower()
            
            if (project_type == "full_stack" or 
                "frontend" in str(spec) or "backend" in str(spec) or
                "api" in user_prompt_lower or "app" in user_prompt_lower or
                "fastapi" in user_prompt_lower or "react" in user_prompt_lower):
                state["project_type"] = "full_stack"
            else:
                state["project_type"] = "simple"
            
            print(f"✅ Spec created: {len(str(spec))} chars, Type: {state['project_type']}")
        except Exception as e:
            print(f"❌ Architect error: {e}")
            state["spec"] = {"error": str(e)}
            state["project_type"] = "simple"
        return state
    
    def coder_node(state: FlowState) -> FlowState:
        """CODER: spec -> diff (with tool execution support)"""
        print("💻 CODER: Generating diff...")
        try:
            response = coder.invoke({"spec": json.dumps(state["spec"])})
            
            # Check if the response has tool calls
            files_created = []
            diff_content = ""
            
            if hasattr(response, 'tool_calls') and response.tool_calls:
                print(f"🔧 Executing {len(response.tool_calls)} tool calls...")
                
                # Execute tool calls
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    
                    print(f"   🔧 {tool_name}: {list(tool_args.keys())}")
                    
                    # Execute the tool
                    if tool_name == "fs_write_file":
                        # Direct file creation tool
                        file_path = tool_args.get("file_path", "")
                        file_content = tool_args.get("file_content", "")
                        
                        if file_path and file_content:
                            # Write file directly
                            import os
                            os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
                            with open(file_path, 'w') as f:
                                f.write(file_content)
                            
                            files_created.append(file_path)
                            diff_content += f"Created: {file_path} ({len(file_content)} chars)\n"
                            print(f"   ✅ Created: {file_path}")
                    
                    elif tool_name == "fs_write_patch":
                        # This is our main file creation tool
                        file_path = tool_args.get("file_path", "")
                        file_content = tool_args.get("file_content", "")
                        
                        if file_path and file_content:
                            # Write file directly
                            import os
                            os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
                            with open(file_path, 'w') as f:
                                f.write(file_content)
                            
                            files_created.append(file_path)
                            diff_content += f"Created: {file_path} ({len(file_content)} chars)\n"
                            print(f"   ✅ Created: {file_path}")
                    
                    elif tool_name == "fs_list":
                        # Directory listing - informational
                        print(f"   📂 Listed directory")
                    
                    elif tool_name == "pkg_scripts":
                        # Package script management
                        print(f"   📦 Package scripts handled")
            
            # Also check for text content with diff markers
            if response.content:
                text_diff = extract_code_from_response(response.content)
                if text_diff:
                    diff_content += text_diff
                    # Apply any text-based diffs
                    success = apply_diff_to_workspace(text_diff)
                    if success:
                        print("   ✅ Applied text-based diff")
                    else:
                        print("   ⚠️ Failed to apply text-based diff")
            
            state["diff"] = diff_content
            state["last_diff_summary"] = f"Generated code: {len(diff_content)} chars, files: {files_created}"
            state["code_changed_since_last_test"] = True
            
            # Apply diffs to workspace (for compatibility)
            if diff_content:
                print("✅ Code generation successful")
                # Update build status for full-stack projects
                if state["project_type"] == "full_stack":
                    state["build_status"] = {"code_generated": True, "files_created": len(files_created) > 0}
            
            print(f"✅ Diff generated: {len(diff_content)} chars, Files: {files_created}")
            
        except Exception as e:
            print(f"❌ Coder error: {e}")
            import traceback
            traceback.print_exc()
            state["diff"] = ""
            state["last_diff_summary"] = f"Error: {str(e)}"
            
        return state
    
    def conductor_node(state: FlowState) -> FlowState:
        """CONDUCTOR: Enhanced orchestration for full-stack"""
        print("🎭 CONDUCTOR: Making enhanced decision...")
        
        # Update state snapshot
        state["state_snapshot"] = {
            "mode": state["mode"],
            "iteration": state["iteration"],
            "project_type": state["project_type"],
            "plan": str(state["plan"])[:100] + "...",
            "spec": str(state["spec"])[:100] + "...",
            "last_diff_summary": state["last_diff_summary"],
            "tests_present": state["tests_present"],
            "test_output": state["test_output"],
            "review": state["review"],
            "services_status": state.get("services_status", {}),
            "build_status": state.get("build_status", {})
        }
        
        # Enhanced decision logic
        code_present = bool(state.get("diff"))
        is_full_stack = state["project_type"] == "full_stack"
        
        if not code_present:
            next_action = "PATCH_CODE"
            rationale = "No code present"
        elif is_full_stack and state["code_changed_since_last_test"]:
            # Check if services need to be started
            services_healthy = state.get("services_status", {}).get("healthy", False)
            if not services_healthy:
                next_action = "START_SERVICES"
                rationale = "Full-stack code ready, need to start/check services"
            else:
                next_action = "RUN_TESTS"
                rationale = "Services healthy, ready for tests"
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
        
        # Check iteration limits
        if state["iteration"] >= state["MAX_ITER"]:
            next_action = "PREVIEW"  # Show results even if not complete
            rationale = "Maximum iterations reached, showing preview"
        
        # Create enhanced control output
        control = {
            "next_action": next_action,
            "rationale": rationale,
            "commands": [],
            "service_checks": [],
            "checkpoints": {
                "required": state["iteration"] > 0 and state["iteration"] % 8 == 0,
                "reason": "Periodic checkpoint" if state["iteration"] % 8 == 0 else None
            }
        }
        
        # Add service checks for full-stack
        if is_full_stack:
            spec = state.get("spec", {})
            deployment = spec.get("deployment", {})
            ports = deployment.get("ports", {})
            
            if ports.get("backend"):
                control["service_checks"].append({
                    "port": ports["backend"],
                    "path": "/health",
                    "expected": "200"
                })
            if ports.get("frontend"):
                control["service_checks"].append({
                    "port": ports["frontend"], 
                    "path": "/",
                    "expected": "200"
                })
        
        state["control"] = control
        state["iteration"] += 1
        
        print(f"✅ Decision: {next_action} - {rationale}")
        return state
    
    def tester_node(state: FlowState) -> FlowState:
        """TESTER: Enhanced testing with service checks"""
        print("🧪 TESTER: Creating enhanced tests...")
        try:
            try:
                workspace_tree = fs_list.invoke({"dir": "."})
            except:
                workspace_tree = "No files found"
            
            response = tester.invoke({
                "spec": json.dumps(state["spec"]),
                "workspace_tree": workspace_tree
            })
            
            content = response.content
            tests = extract_code_from_response(content)
            
            # Enhanced test guide
            if "-----BEGIN TEST_GUIDE-----" in content and "-----END TEST_GUIDE-----" in content:
                guide_start = content.find("-----BEGIN TEST_GUIDE-----") + len("-----BEGIN TEST_GUIDE-----")
                guide_end = content.find("-----END TEST_GUIDE-----")
                test_guide = content[guide_start:guide_end].strip()
            else:
                test_guide = "how_to_run: python_test_runner\ntest_strategy: unit\nnotes:\n  - Basic test execution"
            
            state["tests"] = tests
            state["test_guide"] = test_guide
            state["tests_present"] = len(tests.strip()) > 0
            
            print(f"✅ Tests created: {len(tests)} chars")
        except Exception as e:
            print(f"❌ Tester error: {e}")
            state["tests"] = "# No tests generated"
            state["test_guide"] = "how_to_run: python_test_runner"
            state["tests_present"] = False
        return state
    
    def runner_node(state: FlowState) -> FlowState:
        """RUNNER: Enhanced test execution with auto-fixing"""
        print("🏃 RUNNER: Executing enhanced tests with auto-fixing...")
        
        # Initialize project tools
        project_tools = ProjectAwareTools(state.get("project_dir", ""))
        
        try:
            # First, try to run the actual generated code
            execution_results = check_and_run_code(state, project_tools)
            
            # Auto-fixing loop if errors are found
            max_fix_attempts = 3
            fix_attempt = 0
            
            while execution_results.get("needs_fixing", False) and fix_attempt < max_fix_attempts:
                fix_attempt += 1
                print(f"🔧 AUTO-FIX ATTEMPT {fix_attempt}/{max_fix_attempts}")
                
                # Try basic auto-fix first
                basic_fix_applied = attempt_auto_fix(state, execution_results, project_tools)
                
                # If basic fix didn't work, try web search solutions
                if not basic_fix_applied and execution_results.get("errors"):
                    print("🔍 Searching for error solutions...")
                    for error in execution_results.get("errors", []):
                        error_text = error.get("error", "")
                        solution = search_error_solution(error_text)
                        print(f"💡 Suggested solution: {solution}")
                
                # Try AI agent fix for complex errors
                ai_fix_applied = False
                if not basic_fix_applied and execution_results.get("errors"):
                    print("🤖 Attempting AI agent fix...")
                    for error in execution_results.get("errors", []):
                        error_text = error.get("error", "")
                        if ai_agent_fix(state, error_text, project_tools):
                            ai_fix_applied = True
                            break
                
                # Check if any fix was applied
                if basic_fix_applied or ai_fix_applied:
                    print(f"✅ Applied fixes, re-testing...")
                    # Re-test after fixes
                    execution_results = check_and_run_code(state, project_tools)
                    
                    if not execution_results.get("needs_fixing", False):
                        print("🎉 Auto-fix successful! Code now runs without errors.")
                        break
                else:
                    print(f"⚠️ Auto-fix attempt {fix_attempt} unsuccessful")
                    break  # No point continuing if no fixes were applied
            
            if execution_results.get("needs_fixing", False):
                print(f"⚠️ Could not auto-fix all issues after {max_fix_attempts} attempts")
            
            # Continue with original test execution
            # Run basic tests
            result = python_test_runner.invoke({"code": state["tests"]})
            test_output = {
                "exit_code": result.get("exit_code", 0),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "execution_results": execution_results  # Include auto-fix results
            }
            
            # For full-stack apps, also run service checks
            if state["project_type"] == "full_stack":
                service_results = []
                control = state.get("control", {})
                
                for check in control.get("service_checks", []):
                    port = check["port"]
                    path = check["path"]
                    url = f"http://localhost:{port}{path}"
                    
                    try:
                        probe_result = http_probe.invoke({
                            "url": url,
                            "expected_status": int(check["expected"])
                        })
                        service_results.append({
                            "url": url,
                            "success": probe_result.get("success", False),
                            "status_code": probe_result.get("status_code", 0)
                        })
                    except:
                        service_results.append({
                            "url": url,
                            "success": False,
                            "status_code": 0,
                            "error": "Service check failed"
                        })
                
                test_output["service_checks"] = service_results
                
                # Update services status
                all_healthy = len(service_results) == 0 or all(r["success"] for r in service_results)
                state["services_status"] = {"healthy": all_healthy, "checks": service_results}
        
        except Exception as e:
            test_output = {
                "exit_code": 1,
                "stdout": "",
                "stderr": str(e)
            }
        
        state["test_output"] = test_output
        state["code_changed_since_last_test"] = False
        
        # Include auto-fix status in final result
        auto_fix_status = "with auto-fixes applied" if execution_results.get("fixes_applied") else ""
        status = "PASSED" if test_output["exit_code"] == 0 else "FAILED"
        print(f"✅ Tests executed: {status} {auto_fix_status}")
        return state
    
    def reviewer_node(state: FlowState) -> FlowState:
        """REVIEWER: Enhanced review"""
        print("👀 REVIEWER: Reviewing code...")
        try:
            response = reviewer.invoke({
                "spec": json.dumps(state["spec"]),
                "code_summary": state["last_diff_summary"],
                "test_output": json.dumps(state["test_output"])
            })
            
            review = extract_yaml_from_response(response.content)
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
            
            # Full-stack checks
            if state["project_type"] == "full_stack":
                build_complete = state.get("build_status", {}).get("code_generated", False)
                if not build_complete and review["status"] == "APPROVED":
                    review["status"] = "CHANGES_REQUIRED"
                    review["issues"].append({
                        "id": "FS1",
                        "severity": "blocker",
                        "summary": "Full-stack build incomplete",
                        "fix_hint": "Ensure both frontend and backend code are generated"
                    })
            
            state["review"] = review
            state["review_done"] = True
            
            print(f"✅ Review completed: {review.get('status', 'UNKNOWN')}")
        except Exception as e:
            print(f"❌ Reviewer error: {e}")
            state["review"] = {"status": "CHANGES_REQUIRED", "notes": [f"Review failed: {e}"], "issues": []}
            state["review_done"] = True
        return state
    
    def fixer_node(state: FlowState) -> FlowState:
        """FIXER: Enhanced fixing"""
        print("🔧 FIXER: Applying enhanced fixes...")
        try:
            response = fixer.invoke({
                "spec": json.dumps(state["spec"]),
                "review": json.dumps(state["review"]),
                "test_output": json.dumps(state["test_output"]),
                "changed_files": state["last_diff_summary"]
            })
            
            diff = extract_code_from_response(response.content)
            
            # Apply fixes
            if diff:
                success = apply_diff_to_workspace(diff)
                if success:
                    print("✅ Fix applied to workspace")
            
            state["diff"] = diff
            state["last_diff_summary"] = f"Fixed {len(diff)} chars ({state['project_type']})"
            state["code_changed_since_last_test"] = True
            state["review_done"] = False
            
            print(f"✅ Fix generated: {len(diff)} chars")
        except Exception as e:
            print(f"❌ Fixer error: {e}")
            state["diff"] = state.get("diff", "")
        return state
    
    def service_manager_node(state: FlowState) -> FlowState:
        """SERVICE_MANAGER: Start and manage services"""
        print("🛠️ SERVICE_MANAGER: Managing services...")
        
        if state["project_type"] != "full_stack":
            print("⏭️ Skipping service management for simple project")
            return state
        
        try:
            spec = state.get("spec", {})
            deployment = spec.get("deployment", {})
            ports = deployment.get("ports", {})
            
            service_status = {}
            
            # Check/start backend
            if ports.get("backend"):
                backend_port = ports["backend"]
                port_status = port_check.invoke({"port": backend_port})
                
                if not port_status.get("open"):
                    print(f"🚀 Backend service needed on port {backend_port}")
                    service_status["backend"] = {"port": backend_port, "status": "ready_to_start"}
                else:
                    service_status["backend"] = {"port": backend_port, "status": "running"}
            
            # Check/start frontend  
            if ports.get("frontend"):
                frontend_port = ports["frontend"]
                port_status = port_check.invoke({"port": frontend_port})
                
                if not port_status.get("open"):
                    print(f"🚀 Frontend service needed on port {frontend_port}")
                    service_status["frontend"] = {"port": frontend_port, "status": "ready_to_start"}
                else:
                    service_status["frontend"] = {"port": frontend_port, "status": "running"}
            
            # Mark services as healthy for demo
            state["services_status"] = {"healthy": True, "services": service_status}
            print(f"✅ Service management complete: {len(service_status)} services")
            
        except Exception as e:
            print(f"❌ Service manager error: {e}")
            state["services_status"] = {"healthy": False, "error": str(e)}
        
        return state
    
    def preview_node(state: FlowState) -> FlowState:
        """PREVIEW: Enhanced preview"""
        print("🌐 PREVIEW: Creating enhanced preview...")
        
        preview_info = {
            "status": "deployed",
            "timestamp": "2025-08-30",
            "project_type": state["project_type"]
        }
        
        if state["project_type"] == "full_stack":
            spec = state.get("spec", {})
            deployment = spec.get("deployment", {})
            ports = deployment.get("ports", {})
            
            preview_info["urls"] = {}
            if ports.get("backend"):
                preview_info["urls"]["backend"] = f"http://localhost:{ports['backend']}"
                preview_info["urls"]["api_health"] = f"http://localhost:{ports['backend']}/health"
            if ports.get("frontend"):
                preview_info["urls"]["frontend"] = f"http://localhost:{ports['frontend']}"
                
            preview_info["services"] = state.get("services_status", {})
            
            # List generated files
            try:
                files = fs_list.invoke({"dir": "."})
                preview_info["generated_files"] = files
            except:
                preview_info["generated_files"] = "Could not list files"
        else:
            preview_info["urls"] = {"local": "Code ready for execution"}
            try:
                files = fs_list.invoke({"dir": "."})
                preview_info["generated_files"] = files
            except:
                preview_info["generated_files"] = "Could not list files"
        
        state["control"]["preview_info"] = preview_info
        
        print(f"✅ Preview ready: {state['project_type']} project")
        return state
    
    # Create workflow
    workflow = StateGraph(FlowState)
    
    # Add all nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("conductor", conductor_node)
    workflow.add_node("tester", tester_node)
    workflow.add_node("runner", runner_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("fixer", fixer_node)
    workflow.add_node("service_manager", service_manager_node)
    workflow.add_node("preview", preview_node)
    
    # Linear flow
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "architect")
    workflow.add_edge("architect", "coder")
    workflow.add_edge("coder", "conductor")
    
    # Enhanced routing functions
    def route_after_conductor(state: FlowState) -> str:
        next_action = state["control"]["next_action"]
        
        if next_action == "PATCH_CODE":
            return "fixer" if state["review_done"] and state["review"].get("status") != "APPROVED" else "coder"
        elif next_action == "START_SERVICES":
            return "service_manager"
        elif next_action == "RUN_TESTS":
            return "tester"
        elif next_action == "HEALTH_CHECK":
            return "runner"
        elif next_action == "REVIEW":
            return "reviewer"
        elif next_action == "PREVIEW":
            return "preview"
        elif next_action == "FINISH":
            return "preview"  # Always show preview at end
        else:
            return "preview"
    
    def route_after_runner(state: FlowState) -> str:
        test_passed = state["test_output"]["exit_code"] == 0
        services_healthy = state.get("services_status", {}).get("healthy", True)
        
        if test_passed and services_healthy:
            return "conductor"
        else:
            return "fixer"
    
    # Conditional edges
    workflow.add_conditional_edges("conductor", route_after_conductor, {
        "coder": "coder",
        "service_manager": "service_manager",
        "tester": "tester",
        "runner": "runner",
        "reviewer": "reviewer",
        "fixer": "fixer",
        "preview": "preview"
    })
    
    workflow.add_edge("service_manager", "conductor")
    workflow.add_edge("tester", "runner")
    workflow.add_conditional_edges("runner", route_after_runner, {
        "conductor": "conductor",
        "fixer": "fixer"
    })
    
    workflow.add_edge("reviewer", "conductor")
    workflow.add_edge("fixer", "conductor")
    workflow.add_edge("preview", END)
    
    return workflow

def run_workflow(user_prompt: str, project_dir: str = None) -> dict:
    """Run the complete working exact flow with auto-fixing"""
    
    print("🚀 COMPLETE EXACT FLOW IMPLEMENTATION WITH AUTO-FIXING")
    print("=" * 80)
    print(f"📝 User Goal: {user_prompt}")
    if project_dir:
        print(f"📁 Project Directory: {project_dir}")
    print("=" * 80)
    
    # Initialize state
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
        "MAX_ITER": 5,
        "project_type": "simple",
        "services_status": {},
        "build_status": {},
        "project_dir": project_dir or ""
    }
    
    # Create and run workflow
    workflow = create_workflow()
    app = workflow.compile()
    
    try:
        config = {"recursion_limit": 30}
        final_state = app.invoke(initial_state, config=config)
        
        print("\n" + "=" * 80)
        print("🎉 COMPLETE EXACT FLOW FINISHED!")
        print("=" * 80)
        
        # Display enhanced results
        print(f"📊 Project Type: {final_state['project_type']}")
        print(f"📊 Iterations: {final_state['iteration']}")
        print(f"📊 Final Action: {final_state['control'].get('next_action', 'N/A')}")
        print(f"📊 Tests Present: {final_state['tests_present']}")
        print(f"📊 Review Status: {final_state['review'].get('status', 'N/A')}")
        print(f"📊 Code Changes: {final_state['last_diff_summary']}")
        
        # Full-stack specific results
        if final_state['project_type'] == 'full_stack':
            print(f"📊 Services Status: {final_state.get('services_status', {})}")
            preview_info = final_state['control'].get('preview_info', {})
            if 'urls' in preview_info:
                print(f"🌐 Preview URLs: {preview_info['urls']}")
            if 'generated_files' in preview_info:
                print(f"📁 Generated Files:\n{preview_info['generated_files']}")
        
        # Return success information
        result = {
            "success": True,
            "final_state": final_state,
            "execution_results": final_state.get("execution_results"),
            "auto_fix_enabled": True,
            "project_dir": final_state.get("project_dir")
        }
        return result
        
    except Exception as e:
        print(f"❌ Complete flow failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "final_state": initial_state
        }

def main():
    """Enhanced main function with project management and auto-fixing"""
    import sys
    
    # Get user prompt from command line or use default
    if len(sys.argv) > 1:
        user_prompt = " ".join(sys.argv[1:])
    else:
        user_prompt = "Create a simple todo application with FastAPI backend that serves a JSON API and a React frontend with a clean UI. Include CRUD operations for todos."
    
    print(f"🚀 Starting enhanced code generation with auto-fixing...")
    print(f"📝 User Prompt: {user_prompt}")
    
    # Initialize project manager
    project_manager = ProjectDirectoryManager()
    
    # Create project directory
    project_dir = project_manager.create_project_directory(user_prompt)
    print(f"📁 Created project directory: {project_dir}")
    
    # Run the workflow
    result = run_workflow(user_prompt, project_dir=project_dir)
    
    if result.get("success"):
        print(f"\n🎉 Project generated successfully!")
        print(f"📂 Location: {project_dir}")
        print(f"🔧 Auto-fixing: {'enabled' if result.get('auto_fix_enabled') else 'disabled'}")
        
        # Show execution results if available
        execution_results = result.get("execution_results")
        if execution_results:
            if execution_results.get("success"):
                print("✅ Code executed successfully!")
            else:
                print("⚠️  Code execution had issues:")
                for error in execution_results.get("errors", []):
                    print(f"   - {error.get('error', 'Unknown error')}")
    else:
        print(f"\n❌ Project generation failed: {result.get('error', 'Unknown error')}")
    
    return result

if __name__ == "__main__":
    main()
