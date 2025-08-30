"""
Project Directory Manager - Dynamic creation and management of project directories

This module handles:
1. Dynamic creation of unique project directories
2. Optional cleanup of previous projects
3. Project isolation and organization
4. Workspace management
"""

import os
import shutil
import uuid
import re
from datetime import datetime
from typing import Optional, List
from pathlib import Path
import json


class ProjectDirectoryManager:
    """Manages dynamic project directories with cleanup capabilities"""
    
    def __init__(self, base_workspace: str = "/workspaces/makeor_codeagent"):
        self.base_workspace = base_workspace
        self.projects_root = os.path.join(base_workspace, "generated_projects")
        self.metadata_file = os.path.join(self.projects_root, ".project_metadata.json")
        self.current_project_dir = None
        self.current_project_id = None
        
        # Ensure projects root exists
        os.makedirs(self.projects_root, exist_ok=True)
        
    def create_project_directory(self, project_name: str = None, cleanup_previous: bool = False) -> str:
        """
        Create a new project directory with unique identifier
        
        Args:
            project_name: Optional custom project name
            cleanup_previous: Whether to delete previous project directories
            
        Returns:
            Path to the new project directory
        """
        # Generate unique project ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        
        if project_name:
            # Clean project name for filesystem
            clean_name = self._clean_project_name(project_name)
            project_id = f"{timestamp}_{clean_name}_{unique_id}"
        else:
            project_id = f"{timestamp}_project_{unique_id}"
            
        project_dir = os.path.join(self.projects_root, project_id)
        
        # Cleanup previous projects if requested
        if cleanup_previous:
            self.cleanup_previous_projects()
            
        # Create new project directory
        os.makedirs(project_dir, exist_ok=True)
        
        # Create subdirectories
        subdirs = ["backend", "frontend", "database", "docs", "tests", "scripts"]
        for subdir in subdirs:
            os.makedirs(os.path.join(project_dir, subdir), exist_ok=True)
            
        # Save project metadata
        self._save_project_metadata(project_id, project_name or "Unnamed Project", project_dir)
        
        # Update current project
        self.current_project_dir = project_dir
        self.current_project_id = project_id
        
        print(f"📁 Created new project directory: {project_dir}")
        return project_dir
        
    def cleanup_previous_projects(self, keep_last_n: int = 0) -> List[str]:
        """
        Remove previous project directories
        
        Args:
            keep_last_n: Number of recent projects to keep (0 = delete all)
            
        Returns:
            List of deleted project directories
        """
        deleted_projects = []
        
        if not os.path.exists(self.projects_root):
            return deleted_projects
            
        # Get all project directories (exclude metadata file)
        project_dirs = []
        for item in os.listdir(self.projects_root):
            item_path = os.path.join(self.projects_root, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                project_dirs.append((item, item_path))
                
        # Sort by creation time (newest first)
        project_dirs.sort(key=lambda x: os.path.getctime(x[1]), reverse=True)
        
        # Delete old projects (keeping the last N)
        projects_to_delete = project_dirs[keep_last_n:]
        
        for project_name, project_path in projects_to_delete:
            try:
                shutil.rmtree(project_path)
                deleted_projects.append(project_path)
                print(f"🗑️  Deleted previous project: {project_path}")
            except Exception as e:
                print(f"❌ Failed to delete {project_path}: {e}")
                
        # Update metadata
        self._cleanup_metadata(deleted_projects)
        
        return deleted_projects
        
    def list_projects(self) -> List[dict]:
        """List all existing projects with metadata"""
        metadata = self._load_project_metadata()
        projects = []
        
        for project_id, data in metadata.items():
            if os.path.exists(data['path']):
                projects.append({
                    'id': project_id,
                    'name': data['name'],
                    'path': data['path'],
                    'created_at': data['created_at'],
                    'size': self._get_directory_size(data['path'])
                })
                
        return sorted(projects, key=lambda x: x['created_at'], reverse=True)
        
    def get_current_project_dir(self) -> Optional[str]:
        """Get the current active project directory"""
        return self.current_project_dir
        
    def switch_to_project(self, project_id: str) -> bool:
        """Switch to an existing project directory"""
        metadata = self._load_project_metadata()
        
        if project_id in metadata and os.path.exists(metadata[project_id]['path']):
            self.current_project_dir = metadata[project_id]['path']
            self.current_project_id = project_id
            print(f"🔄 Switched to project: {project_id}")
            return True
            
        return False
        
    def _clean_project_name(self, name: str) -> str:
        """Clean project name for filesystem compatibility"""
        # Remove/replace invalid characters
        clean_name = re.sub(r'[^\w\s-]', '', name)
        clean_name = re.sub(r'[-\s]+', '_', clean_name)
        return clean_name.lower()[:50]  # Limit length
        
    def _save_project_metadata(self, project_id: str, project_name: str, project_path: str):
        """Save project metadata to JSON file"""
        metadata = self._load_project_metadata()
        
        metadata[project_id] = {
            'name': project_name,
            'path': project_path,
            'created_at': datetime.now().isoformat(),
            'last_modified': datetime.now().isoformat()
        }
        
        with open(self.metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
            
    def _load_project_metadata(self) -> dict:
        """Load project metadata from JSON file"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
        
    def _cleanup_metadata(self, deleted_projects: List[str]):
        """Remove metadata for deleted projects"""
        metadata = self._load_project_metadata()
        
        # Remove entries for deleted projects
        to_remove = []
        for project_id, data in metadata.items():
            if data['path'] in deleted_projects:
                to_remove.append(project_id)
                
        for project_id in to_remove:
            del metadata[project_id]
            
        with open(self.metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
            
    def _get_directory_size(self, path: str) -> int:
        """Get total size of directory in bytes"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
        except Exception:
            pass
        return total_size


def format_size(size_bytes: int) -> str:
    """Format bytes as human readable string"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


# Enhanced project management CLI commands
def manage_projects_cli():
    """CLI interface for project management"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python project_manager.py <command> [options]")
        print("Commands:")
        print("  list                 - List all projects")
        print("  create <name>        - Create new project")
        print("  cleanup [keep_n]     - Delete old projects (keep last N)")
        print("  switch <project_id>  - Switch to existing project")
        return
        
    manager = ProjectDirectoryManager()
    command = sys.argv[1]
    
    if command == "list":
        projects = manager.list_projects()
        if not projects:
            print("No projects found.")
            return
            
        print(f"{'ID':<25} {'Name':<30} {'Created':<20} {'Size':<10}")
        print("-" * 85)
        for project in projects:
            created = datetime.fromisoformat(project['created_at']).strftime('%Y-%m-%d %H:%M')
            size = format_size(project['size'])
            print(f"{project['id']:<25} {project['name']:<30} {created:<20} {size:<10}")
            
    elif command == "create":
        name = sys.argv[2] if len(sys.argv) > 2 else None
        cleanup = "--cleanup" in sys.argv
        project_dir = manager.create_project_directory(name, cleanup)
        print(f"Created project at: {project_dir}")
        
    elif command == "cleanup":
        keep_n = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        deleted = manager.cleanup_previous_projects(keep_n)
        print(f"Deleted {len(deleted)} projects")
        
    elif command == "switch":
        if len(sys.argv) < 3:
            print("Error: project_id required")
            return
        project_id = sys.argv[2]
        if manager.switch_to_project(project_id):
            print(f"Switched to project: {project_id}")
        else:
            print(f"Project not found: {project_id}")
            
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    manage_projects_cli()
