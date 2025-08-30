# advanced_features.py
# Advanced features for scalable code agent: RAG, Parallelization, Caching, Version Pinning

import asyncio
import hashlib
import json
import os
import pickle
import time
from typing import Dict, List, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

# RAG for Code: Embeddings per file/function
class CodeRAGSystem:
    """RAG system with embeddings per file/function for better context retrieval"""
    
    def __init__(self, cache_dir: str = ".code_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.embeddings_db = os.path.join(cache_dir, "embeddings.db")
        self._init_embeddings_db()
    
    def _init_embeddings_db(self):
        """Initialize embeddings database"""
        conn = sqlite3.connect(self.embeddings_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS code_embeddings (
                id INTEGER PRIMARY KEY,
                file_path TEXT,
                function_name TEXT,
                code_snippet TEXT,
                embedding_hash TEXT,
                embedding_data BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(file_path, function_name, embedding_hash)
            )
        """)
        conn.commit()
        conn.close()
    
    def extract_functions_from_file(self, file_path: str) -> List[Dict[str, str]]:
        """Extract functions and classes from a Python file"""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            functions = []
            lines = content.split('\n')
            current_function = None
            current_lines = []
            indent_level = 0
            
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('def ') or stripped.startswith('class '):
                    # Save previous function
                    if current_function and current_lines:
                        functions.append({
                            'name': current_function,
                            'code': '\n'.join(current_lines),
                            'file_path': file_path
                        })
                    
                    # Start new function
                    current_function = stripped.split('(')[0].replace('def ', '').replace('class ', '')
                    current_lines = [line]
                    indent_level = len(line) - len(line.lstrip())
                
                elif current_function:
                    line_indent = len(line) - len(line.lstrip()) if line.strip() else indent_level
                    if line.strip() == '' or line_indent > indent_level:
                        current_lines.append(line)
                    else:
                        # End of function
                        functions.append({
                            'name': current_function,
                            'code': '\n'.join(current_lines),
                            'file_path': file_path
                        })
                        current_function = None
                        current_lines = []
            
            # Save last function
            if current_function and current_lines:
                functions.append({
                    'name': current_function,
                    'code': '\n'.join(current_lines),
                    'file_path': file_path
                })
            
            return functions
        except Exception as e:
            print(f"Error extracting functions from {file_path}: {e}")
            return []
    
    def generate_embedding_hash(self, code: str) -> str:
        """Generate hash for code snippet"""
        return hashlib.sha256(code.encode()).hexdigest()[:16]
    
    def store_function_embedding(self, file_path: str, function_name: str, code: str):
        """Store function embedding in database"""
        embedding_hash = self.generate_embedding_hash(code)
        
        # Simple embedding simulation (in real implementation, use sentence-transformers)
        embedding_data = pickle.dumps({
            'tokens': code.split(),
            'length': len(code),
            'keywords': [w for w in code.split() if w in ['def', 'class', 'import', 'return', 'if', 'for', 'while']]
        })
        
        conn = sqlite3.connect(self.embeddings_db)
        try:
            conn.execute("""
                INSERT OR REPLACE INTO code_embeddings 
                (file_path, function_name, code_snippet, embedding_hash, embedding_data)
                VALUES (?, ?, ?, ?, ?)
            """, (file_path, function_name, code[:1000], embedding_hash, embedding_data))
            conn.commit()
        except Exception as e:
            print(f"Error storing embedding: {e}")
        finally:
            conn.close()
    
    def find_relevant_functions(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Find relevant functions based on query"""
        query_tokens = set(query.lower().split())
        
        conn = sqlite3.connect(self.embeddings_db)
        cursor = conn.execute("""
            SELECT file_path, function_name, code_snippet, embedding_data 
            FROM code_embeddings 
            ORDER BY created_at DESC
        """)
        
        results = []
        for row in cursor.fetchall():
            file_path, function_name, code_snippet, embedding_data = row
            try:
                embedding = pickle.loads(embedding_data)
                code_tokens = set([t.lower() for t in embedding['tokens']])
                
                # Simple similarity score
                similarity = len(query_tokens.intersection(code_tokens)) / max(len(query_tokens), 1)
                
                if similarity > 0:
                    results.append({
                        'file_path': file_path,
                        'function_name': function_name,
                        'code_snippet': code_snippet,
                        'similarity': similarity
                    })
            except Exception as e:
                continue
        
        conn.close()
        
        # Sort by similarity and return top results
        return sorted(results, key=lambda x: x['similarity'], reverse=True)[:limit]

# Parallelization: Run FE + BE tests separately
class ParallelTestRunner:
    """Run frontend and backend tests in parallel"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
    
    async def run_parallel_tests(self, test_configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run multiple test suites in parallel"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all test tasks
            future_to_config = {
                executor.submit(self._run_single_test, config): config
                for config in test_configs
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    result = future.result()
                    results[config['name']] = result
                except Exception as e:
                    results[config['name']] = {
                        'status': 'error',
                        'error': str(e),
                        'duration': 0
                    }
        
        return results
    
    def _run_single_test(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single test configuration"""
        start_time = time.time()
        
        try:
            # Simulate test execution (replace with actual test runner)
            if config['type'] == 'backend':
                return self._run_backend_tests(config)
            elif config['type'] == 'frontend':
                return self._run_frontend_tests(config)
            else:
                return self._run_generic_tests(config)
        
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'duration': time.time() - start_time
            }
    
    def _run_backend_tests(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run backend-specific tests"""
        start_time = time.time()
        
        # Simulate backend test execution
        import subprocess
        try:
            result = subprocess.run(
                ['python', '-m', 'pytest', 'tests/', '-v'],
                cwd=config.get('working_dir', '.'),
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            return {
                'status': 'passed' if result.returncode == 0 else 'failed',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'duration': time.time() - start_time,
                'exit_code': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'status': 'timeout',
                'error': 'Test execution timed out',
                'duration': time.time() - start_time
            }
    
    def _run_frontend_tests(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run frontend-specific tests"""
        start_time = time.time()
        
        # Simulate frontend test execution
        import subprocess
        try:
            result = subprocess.run(
                ['npm', 'test', '--', '--watchAll=false'],
                cwd=config.get('working_dir', './frontend'),
                capture_output=True,
                text=True,
                timeout=300
            )
            
            return {
                'status': 'passed' if result.returncode == 0 else 'failed',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'duration': time.time() - start_time,
                'exit_code': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'status': 'timeout',
                'error': 'Frontend test execution timed out',
                'duration': time.time() - start_time
            }
        except FileNotFoundError:
            return {
                'status': 'skipped',
                'reason': 'npm not found or no frontend tests',
                'duration': time.time() - start_time
            }
    
    def _run_generic_tests(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run generic test configuration"""
        start_time = time.time()
        
        # Basic test simulation
        import subprocess
        try:
            cmd = config.get('command', ['echo', 'No test command specified'])
            result = subprocess.run(
                cmd,
                cwd=config.get('working_dir', '.'),
                capture_output=True,
                text=True,
                timeout=180
            )
            
            return {
                'status': 'passed' if result.returncode == 0 else 'failed',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'duration': time.time() - start_time,
                'exit_code': result.returncode
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'duration': time.time() - start_time
            }

# Caching: Store error fingerprints, research results, diff history
@dataclass
class ErrorFingerprint:
    error_type: str
    error_message: str
    stack_trace_hash: str
    file_path: str
    timestamp: datetime
    resolution: Optional[str] = None

@dataclass
class ResearchResult:
    query: str
    result_data: Dict[str, Any]
    timestamp: datetime
    confidence_score: float

@dataclass
class DiffHistoryEntry:
    diff_hash: str
    diff_content: str
    files_changed: List[str]
    timestamp: datetime
    success: bool

class AdvancedCachingSystem:
    """Advanced caching for error fingerprints, research results, and diff history"""
    
    def __init__(self, cache_dir: str = ".agent_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_db = os.path.join(cache_dir, "agent_cache.db")
        self._init_cache_db()
    
    def _init_cache_db(self):
        """Initialize caching database"""
        conn = sqlite3.connect(self.cache_db)
        
        # Error fingerprints table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_fingerprints (
                id INTEGER PRIMARY KEY,
                error_type TEXT,
                error_message TEXT,
                stack_trace_hash TEXT,
                file_path TEXT,
                timestamp TIMESTAMP,
                resolution TEXT,
                UNIQUE(stack_trace_hash, file_path)
            )
        """)
        
        # Research results table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS research_results (
                id INTEGER PRIMARY KEY,
                query TEXT,
                result_data TEXT,
                timestamp TIMESTAMP,
                confidence_score REAL,
                expiry_date TIMESTAMP
            )
        """)
        
        # Diff history table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS diff_history (
                id INTEGER PRIMARY KEY,
                diff_hash TEXT UNIQUE,
                diff_content TEXT,
                files_changed TEXT,
                timestamp TIMESTAMP,
                success BOOLEAN
            )
        """)
        
        conn.commit()
        conn.close()
    
    def store_error_fingerprint(self, error: ErrorFingerprint):
        """Store error fingerprint for future reference"""
        conn = sqlite3.connect(self.cache_db)
        try:
            conn.execute("""
                INSERT OR REPLACE INTO error_fingerprints 
                (error_type, error_message, stack_trace_hash, file_path, timestamp, resolution)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                error.error_type,
                error.error_message,
                error.stack_trace_hash,
                error.file_path,
                error.timestamp,
                error.resolution
            ))
            conn.commit()
        finally:
            conn.close()
    
    def find_similar_errors(self, error_hash: str, limit: int = 3) -> List[ErrorFingerprint]:
        """Find similar errors from cache"""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.execute("""
            SELECT error_type, error_message, stack_trace_hash, file_path, timestamp, resolution
            FROM error_fingerprints 
            WHERE stack_trace_hash = ? OR error_type = (
                SELECT error_type FROM error_fingerprints WHERE stack_trace_hash = ? LIMIT 1
            )
            ORDER BY timestamp DESC
            LIMIT ?
        """, (error_hash, error_hash, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append(ErrorFingerprint(
                error_type=row[0],
                error_message=row[1],
                stack_trace_hash=row[2],
                file_path=row[3],
                timestamp=datetime.fromisoformat(row[4]),
                resolution=row[5]
            ))
        
        conn.close()
        return results
    
    def store_research_result(self, result: ResearchResult, ttl_hours: int = 24):
        """Store research result with TTL"""
        expiry_date = datetime.now() + timedelta(hours=ttl_hours)
        
        conn = sqlite3.connect(self.cache_db)
        try:
            conn.execute("""
                INSERT OR REPLACE INTO research_results 
                (query, result_data, timestamp, confidence_score, expiry_date)
                VALUES (?, ?, ?, ?, ?)
            """, (
                result.query,
                json.dumps(result.result_data),
                result.timestamp,
                result.confidence_score,
                expiry_date
            ))
            conn.commit()
        finally:
            conn.close()
    
    def get_cached_research(self, query: str) -> Optional[ResearchResult]:
        """Get cached research result if available and not expired"""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.execute("""
            SELECT query, result_data, timestamp, confidence_score
            FROM research_results 
            WHERE query = ? AND expiry_date > ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (query, datetime.now()))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return ResearchResult(
                query=row[0],
                result_data=json.loads(row[1]),
                timestamp=datetime.fromisoformat(row[2]),
                confidence_score=row[3]
            )
        return None
    
    def store_diff_history(self, diff_entry: DiffHistoryEntry):
        """Store diff history for learning patterns"""
        conn = sqlite3.connect(self.cache_db)
        try:
            conn.execute("""
                INSERT OR REPLACE INTO diff_history 
                (diff_hash, diff_content, files_changed, timestamp, success)
                VALUES (?, ?, ?, ?, ?)
            """, (
                diff_entry.diff_hash,
                diff_entry.diff_content,
                json.dumps(diff_entry.files_changed),
                diff_entry.timestamp,
                diff_entry.success
            ))
            conn.commit()
        finally:
            conn.close()
    
    def get_successful_diff_patterns(self, file_patterns: List[str], limit: int = 5) -> List[DiffHistoryEntry]:
        """Get successful diff patterns for similar file types"""
        conn = sqlite3.connect(self.cache_db)
        
        # Build query for file pattern matching
        pattern_conditions = " OR ".join(["files_changed LIKE ?" for _ in file_patterns])
        pattern_values = [f"%{pattern}%" for pattern in file_patterns]
        
        cursor = conn.execute(f"""
            SELECT diff_hash, diff_content, files_changed, timestamp, success
            FROM diff_history 
            WHERE success = 1 AND ({pattern_conditions})
            ORDER BY timestamp DESC
            LIMIT ?
        """, pattern_values + [limit])
        
        results = []
        for row in cursor.fetchall():
            results.append(DiffHistoryEntry(
                diff_hash=row[0],
                diff_content=row[1],
                files_changed=json.loads(row[2]),
                timestamp=datetime.fromisoformat(row[3]),
                success=bool(row[4])
            ))
        
        conn.close()
        return results
    
    def cleanup_expired_cache(self):
        """Clean up expired cache entries"""
        conn = sqlite3.connect(self.cache_db)
        try:
            # Remove expired research results
            conn.execute("DELETE FROM research_results WHERE expiry_date < ?", (datetime.now(),))
            
            # Remove old error fingerprints (keep last 30 days)
            cutoff_date = datetime.now() - timedelta(days=30)
            conn.execute("DELETE FROM error_fingerprints WHERE timestamp < ?", (cutoff_date,))
            
            # Remove old diff history (keep last 100 entries per file type)
            conn.execute("""
                DELETE FROM diff_history WHERE id NOT IN (
                    SELECT id FROM diff_history ORDER BY timestamp DESC LIMIT 100
                )
            """)
            
            conn.commit()
        finally:
            conn.close()

# Version Pinning: Lock dependencies more aggressively
class AggressiveVersionPinner:
    """Aggressive version pinning and dependency management"""
    
    def __init__(self, project_root: str = "."):
        self.project_root = project_root
        self.version_db = os.path.join(project_root, ".version_cache.json")
        self.lockfile_path = os.path.join(project_root, "requirements.lock")
    
    def pin_python_dependencies(self, requirements_file: str = "requirements.txt") -> Dict[str, str]:
        """Pin Python dependencies with exact versions"""
        import subprocess
        
        pinned_versions = {}
        
        try:
            # Get currently installed versions
            result = subprocess.run(['pip', 'freeze'], capture_output=True, text=True)
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if '==' in line:
                        package, version = line.split('==', 1)
                        pinned_versions[package.lower()] = version
            
            # Read requirements.txt and pin versions
            requirements_path = os.path.join(self.project_root, requirements_file)
            if os.path.exists(requirements_path):
                with open(requirements_path, 'r') as f:
                    requirements = f.readlines()
                
                pinned_requirements = []
                for req in requirements:
                    req = req.strip()
                    if req and not req.startswith('#'):
                        package_name = req.split('>=')[0].split('==')[0].split('[')[0].strip()
                        if package_name.lower() in pinned_versions:
                            pinned_req = f"{package_name}=={pinned_versions[package_name.lower()]}"
                            pinned_requirements.append(pinned_req)
                        else:
                            pinned_requirements.append(req)
                
                # Write lockfile
                with open(self.lockfile_path, 'w') as f:
                    f.write('\n'.join(pinned_requirements))
                
                print(f"✅ Created {self.lockfile_path} with {len(pinned_requirements)} pinned dependencies")
        
        except Exception as e:
            print(f"❌ Error pinning dependencies: {e}")
        
        return pinned_versions
    
    def pin_node_dependencies(self, package_json_path: str = "frontend/package.json"):
        """Pin Node.js dependencies"""
        import subprocess
        
        full_path = os.path.join(self.project_root, package_json_path)
        
        if os.path.exists(full_path):
            try:
                # Run npm install to generate package-lock.json
                frontend_dir = os.path.dirname(full_path)
                result = subprocess.run(
                    ['npm', 'install', '--package-lock-only'],
                    cwd=frontend_dir,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print(f"✅ Generated package-lock.json for dependency pinning")
                else:
                    print(f"⚠️ Warning: Could not generate package-lock.json: {result.stderr}")
            
            except FileNotFoundError:
                print("⚠️ npm not found - skipping Node.js dependency pinning")
            except Exception as e:
                print(f"❌ Error pinning Node.js dependencies: {e}")
    
    def save_version_snapshot(self, label: str = None):
        """Save current version snapshot"""
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'label': label or f"snapshot_{int(time.time())}",
            'python_versions': self.pin_python_dependencies(),
            'system_info': self._get_system_info()
        }
        
        # Load existing snapshots
        snapshots = {}
        if os.path.exists(self.version_db):
            try:
                with open(self.version_db, 'r') as f:
                    snapshots = json.load(f)
            except Exception:
                pass
        
        # Add new snapshot
        snapshots[snapshot['label']] = snapshot
        
        # Save updated snapshots
        try:
            with open(self.version_db, 'w') as f:
                json.dump(snapshots, f, indent=2)
            print(f"✅ Saved version snapshot: {snapshot['label']}")
        except Exception as e:
            print(f"❌ Error saving version snapshot: {e}")
    
    def _get_system_info(self) -> Dict[str, str]:
        """Get system information for version tracking"""
        import platform
        import sys
        
        return {
            'python_version': sys.version,
            'platform': platform.platform(),
            'architecture': platform.architecture()[0],
            'processor': platform.processor()
        }

# Integration with main workflow
def integrate_advanced_features():
    """Factory function to create advanced feature instances"""
    return {
        'rag_system': CodeRAGSystem(),
        'parallel_runner': ParallelTestRunner(),
        'cache_system': AdvancedCachingSystem(),
        'version_pinner': AggressiveVersionPinner()
    }
