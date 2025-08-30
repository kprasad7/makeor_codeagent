# tools.py
# Tool implementations for fs/proc/http/etc. for the multi-agent workflow.

import os
import subprocess
import json
import urllib.request
import time
from langchain.tools import tool

@tool("fs_read")
def fs_read(path: str) -> str:
    """Read file contents."""
    try:
        with open(path, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

@tool("fs_list")
def fs_list(dir: str = ".") -> str:
    """List files/dirs recursively."""
    try:
        result = []
        for root, dirs, files in os.walk(dir):
            for d in dirs:
                result.append(os.path.join(root, d) + "/")
            for f in files:
                result.append(os.path.join(root, f))
        return "\n".join(result)
    except Exception as e:
        return f"Error listing directory: {str(e)}"

@tool("fs_write_file")
def fs_write_file(file_path: str, file_content: str) -> str:
    """Create or write a file with the given content."""
    try:
        import os
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
        
        # Write the file
        with open(file_path, 'w') as f:
            f.write(file_content)
        
        return f"Successfully created: {file_path} ({len(file_content)} chars)"
    except Exception as e:
        return f"Error creating file {file_path}: {str(e)}"

@tool("fs_write_patch")
def fs_write_patch(unified_diff: str) -> str:
    """Apply unified diff patch."""
    try:
        lines = unified_diff.strip().split('\n')
        i = 0
        files_created = []
        
        while i < len(lines):
            line = lines[i]
            
            if line.startswith('*** Add File:'):
                path = line.split(':', 1)[1].strip()
                i += 1
                
                # Collect content until next file marker or end
                content = []
                while i < len(lines):
                    if lines[i].startswith('*** Add File:') or lines[i].startswith('*** Update File:') or lines[i].startswith('*** End Patch'):
                        break
                    # Skip --- separators and @@
                    if not (lines[i].strip() == '---' or lines[i].startswith('@@')):
                        content.append(lines[i])
                    i += 1
                
                # Clean up content
                content_str = '\n'.join(content)
                
                # Remove markdown code blocks more aggressively
                content_str = content_str.strip()
                
                # Remove various markdown patterns
                if content_str.startswith('```python'):
                    content_str = content_str[9:].strip()
                elif content_str.startswith('```'):
                    content_str = content_str[3:].strip()
                    
                if content_str.endswith('```'):
                    content_str = content_str[:-3].strip()
                
                # Remove any remaining ``` patterns
                lines_clean = []
                for line in content_str.split('\n'):
                    if line.strip() != '```' and not line.strip().startswith('```') and not line.strip().endswith('```'):
                        lines_clean.append(line)
                
                content_str = '\n'.join(lines_clean)
                
                # Create directory if needed
                if '/' in path:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                
                # Write file
                with open(path, 'w') as f:
                    f.write(content_str.strip())
                files_created.append(path)
                
            elif line.startswith('*** Update File:'):
                path = line.split(':', 1)[1].strip()
                i += 1
                
                # Skip to new content (after ---)
                while i < len(lines) and not lines[i].strip().startswith('---'):
                    i += 1
                if i < len(lines):
                    i += 1  # Skip the --- line
                
                # Collect new content
                content = []
                while i < len(lines):
                    if lines[i].startswith('*** Add File:') or lines[i].startswith('*** Update File:') or lines[i].startswith('*** End Patch'):
                        break
                    content.append(lines[i])
                    i += 1
                
                # Clean up content
                content_str = '\n'.join(content)
                if content_str.startswith('```python\n'):
                    content_str = content_str[10:]
                if content_str.endswith('\n```'):
                    content_str = content_str[:-4]
                
                # Write file
                with open(path, 'w') as f:
                    f.write(content_str.strip())
                files_created.append(path)
                
            else:
                i += 1
        
        if files_created:
            return f"Created/updated files: {', '.join(files_created)}"
        else:
            return "No files found in patch"
            
    except Exception as e:
        return f"Error applying patch: {str(e)}"

@tool("proc_run")
def proc_run(cmd: str, timeout_s: int = 60) -> dict:
    """Run shell command."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_s)
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except Exception as e:
        return {"error": str(e)}

@tool("http_probe")
def http_probe(url: str) -> dict:
    """Probe HTTP URL."""
    try:
        with urllib.request.urlopen(url) as response:
            return {
                "status_code": response.getcode(),
                "content": response.read(1024).decode('utf-8', errors='ignore')
            }
    except Exception as e:
        return {"error": str(e)}

@tool("pkg_scripts")
def pkg_scripts() -> dict:
    """Parse package/project files for scripts."""
    scripts = {}
    if os.path.exists("package.json"):
        try:
            with open("package.json") as f:
                data = json.load(f)
            scripts.update(data.get("scripts", {}))
        except:
            pass
    # Add more parsers if needed (e.g., pyproject.toml, setup.py)
    return scripts

@tool("python_test_runner")
def python_test_runner(code: str) -> dict:
    """Execute Python code bundle and return structured result."""
    try:
        # Capture stdout/stderr
        import sys
        from io import StringIO
        
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture
        
        try:
            exec(code)
            exit_code = 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            exit_code = 1
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        
        return {
            "exit_code": exit_code,
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue()
        }
    except Exception as e:
        return {
            "exit_code": 1,
            "stdout": "",
            "stderr": f"Test execution failed: {str(e)}"
        }

# Full-stack development tools

@tool("http_probe")
def http_probe(url: str, expected_status: int = 200, timeout: int = 5) -> dict:
    """Probe HTTP endpoint for health check."""
    try:
        import requests
        response = requests.get(url, timeout=timeout)
        return {
            "status_code": response.status_code,
            "success": response.status_code == expected_status,
            "response_time": response.elapsed.total_seconds(),
            "content": response.text[:200] + "..." if len(response.text) > 200 else response.text
        }
    except requests.exceptions.RequestException as e:
        return {
            "status_code": 0,
            "success": False,
            "error": str(e),
            "response_time": timeout
        }

@tool("port_check")
def port_check(port: int, host: str = "localhost") -> dict:
    """Check if a port is open and listening."""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        
        return {
            "port": port,
            "host": host,
            "open": result == 0,
            "status": "open" if result == 0 else "closed"
        }
    except Exception as e:
        return {
            "port": port,
            "host": host,
            "open": False,
            "error": str(e)
        }

@tool("pkg_scripts")
def pkg_scripts(directory: str = ".") -> dict:
    """Detect package scripts and build commands for different project types."""
    scripts = {}
    
    # Check for package.json (Node.js)
    package_json_path = os.path.join(directory, "package.json")
    if os.path.exists(package_json_path):
        try:
            with open(package_json_path) as f:
                package_data = json.load(f)
                scripts["npm"] = package_data.get("scripts", {})
        except:
            pass
    
    # Check for Python project files
    if os.path.exists(os.path.join(directory, "requirements.txt")):
        scripts["python"] = {
            "install": "pip install -r requirements.txt",
            "test": "python -m pytest" if os.path.exists(os.path.join(directory, "test_*.py")) else "python_test_runner"
        }
    
    if os.path.exists(os.path.join(directory, "pyproject.toml")):
        scripts["python"] = scripts.get("python", {})
        scripts["python"]["install"] = "pip install -e ."
    
    # Check for Docker
    if os.path.exists(os.path.join(directory, "Dockerfile")):
        scripts["docker"] = {
            "build": "docker build -t app .",
            "run": "docker run -p 8000:8000 app"
        }
    
    return scripts

@tool("start_service")
def start_service(command: str, background: bool = True, cwd: str = ".") -> dict:
    """Start a service in the background."""
    try:
        if background:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            
            # Give it a moment to start
            time.sleep(2)
            
            # Check if it's still running
            if process.poll() is None:
                return {
                    "pid": process.pid,
                    "status": "started",
                    "command": command,
                    "background": True
                }
            else:
                stdout, stderr = process.communicate()
                return {
                    "pid": process.pid,
                    "status": "failed",
                    "command": command,
                    "stdout": stdout.decode(),
                    "stderr": stderr.decode()
                }
        else:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": command,
                "background": False
            }
    except Exception as e:
        return {
            "status": "error",
            "command": command,
            "error": str(e)
        }

@tool("wait_for_service")
def wait_for_service(url: str, max_wait: int = 30, check_interval: int = 2) -> dict:
    """Wait for a service to become available."""
    import time
    import requests
    
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return {
                    "success": True,
                    "url": url,
                    "wait_time": time.time() - start_time,
                    "status_code": response.status_code
                }
        except:
            pass
        
        time.sleep(check_interval)
    
    return {
        "success": False,
        "url": url,
        "wait_time": max_wait,
        "timeout": True
    }

@tool("log_condenser")
def log_condenser(raw_output: str, max_lines: int = 50) -> str:
    """Condense long logs to key error info for triage."""
    try:
        lines = raw_output.split('\n')
        if len(lines) <= max_lines:
            return raw_output
        
        # Keep first and last portions, highlight errors
        error_lines = [line for line in lines if any(keyword in line.lower() 
                      for keyword in ['error', 'fail', 'exception', 'traceback'])]
        
        condensed = []
        condensed.extend(lines[:10])  # First 10 lines
        
        if error_lines:
            condensed.append("\n--- KEY ERRORS ---")
            condensed.extend(error_lines[:20])  # Up to 20 error lines
        
        condensed.append("\n--- LAST OUTPUT ---")
        condensed.extend(lines[-10:])  # Last 10 lines
        
        return '\n'.join(condensed)
    except Exception as e:
        return f"Error condensing logs: {str(e)}"

@tool("error_triage")
def error_triage(test_output: str, spec: str) -> dict:
    """Analyze errors and suggest reproduction steps and suspect files."""
    try:
        errors = []
        suggestions = []
        suspect_files = []
        
        # Parse common error patterns
        lines = test_output.split('\n')
        for line in lines:
            line_lower = line.lower()
            if 'traceback' in line_lower or 'error:' in line_lower:
                errors.append(line.strip())
            if 'file "' in line_lower:
                # Extract file names from error traces
                import re
                file_match = re.search(r'file "([^"]+)"', line, re.IGNORECASE)
                if file_match:
                    suspect_files.append(file_match.group(1))
        
        # Generate suggestions based on error patterns
        error_text = test_output.lower()
        if 'modulenotfounderror' in error_text:
            suggestions.append("Install missing dependencies")
        if 'syntaxerror' in error_text:
            suggestions.append("Fix syntax errors in code")
        if 'importerror' in error_text:
            suggestions.append("Check import paths and module structure")
        if 'connectionerror' in error_text or 'connection refused' in error_text:
            suggestions.append("Start required services or check ports")
        
        return {
            "errors": errors[:5],  # Top 5 errors
            "suggestions": suggestions,
            "suspect_files": list(set(suspect_files[:10])),  # Unique files
            "repro_steps": [
                "Run the failing test in isolation",
                "Check file dependencies",
                "Verify service prerequisites"
            ]
        }
    except Exception as e:
        return {"errors": [f"Triage failed: {str(e)}"], "suggestions": [], "suspect_files": []}

@tool("context_manager")
def context_manager(spec: str, suspect_files: list, query: str) -> dict:
    """Retrieve only relevant code snippets to keep prompts small (RAG-style)."""
    try:
        snippets = {}
        
        # Read suspect files and extract relevant sections
        for file_path in suspect_files[:5]:  # Limit to 5 files
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        content = f.read()
                        # Keep only first 500 chars of each file for context
                        snippets[file_path] = content[:500] + "..." if len(content) > 500 else content
            except:
                continue
        
        # Extract key sections from spec
        spec_summary = spec[:300] + "..." if len(spec) > 300 else spec
        
        return {
            "spec_summary": spec_summary,
            "file_snippets": snippets,
            "query_context": f"Focused on: {query}"
        }
    except Exception as e:
        return {"error": f"Context retrieval failed: {str(e)}"}

@tool("web_search")
def web_search(error_query: str) -> dict:
    """Search for external solutions to errors (mock implementation for demo)."""
    try:
        # This is a mock implementation - in production you'd use real search APIs
        common_solutions = {
            "modulenotfounderror": "Install package with pip install <package_name>",
            "syntaxerror": "Check for missing colons, parentheses, or indentation",
            "importerror": "Verify module exists and is in PYTHONPATH",
            "connectionerror": "Ensure service is running on correct port",
            "permission denied": "Check file permissions or run with appropriate access"
        }
        
        # Find matching solution
        error_lower = error_query.lower()
        for error_type, solution in common_solutions.items():
            if error_type in error_lower:
                return {
                    "query": error_query,
                    "solution": solution,
                    "confidence": "high",
                    "source": "common_patterns"
                }
        
        return {
            "query": error_query,
            "solution": "No specific solution found. Consider checking documentation.",
            "confidence": "low",
            "source": "fallback"
        }
    except Exception as e:
        return {"error": f"Web search failed: {str(e)}"}

@tool("url_fetch")
def url_fetch(url: str) -> str:
    """Fetch content from URL for research (limited implementation)."""
    try:
        # Simple HTTP GET with timeout
        import urllib.request
        import urllib.error
        
        req = urllib.request.Request(url, headers={'User-Agent': 'CodeAgent/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            # Return first 2KB to avoid context bloat
            return content[:2048] + "..." if len(content) > 2048 else content
    except Exception as e:
        return f"Failed to fetch {url}: {str(e)}"


class ProjectAwareTools:
    """Project-aware utility functions for dynamic project management"""
    
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
    
    def get_project_dir(self) -> str:
        """Get the current project directory"""
        return self.project_dir
    
    def file_exists(self, filename: str) -> bool:
        """Check if a file exists in the project directory"""
        return os.path.exists(os.path.join(self.project_dir, filename))
    
    def read_file(self, filename: str) -> str:
        """Read a file from the project directory"""
        try:
            with open(os.path.join(self.project_dir, filename), 'r') as f:
                return f.read()
        except Exception as e:
            return f"Error reading {filename}: {str(e)}"
    
    def write_file(self, filename: str, content: str) -> bool:
        """Write a file to the project directory"""
        try:
            # Create directory if it doesn't exist
            file_path = os.path.join(self.project_dir, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"Error writing {filename}: {str(e)}")
            return False
    
    def list_files(self, pattern: str = "*") -> list:
        """List files in the project directory"""
        try:
            import glob
            return glob.glob(os.path.join(self.project_dir, pattern))
        except Exception as e:
            print(f"Error listing files: {str(e)}")
            return []
