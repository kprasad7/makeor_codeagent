# 🏗️ MakeOR Code Agent - Production Architecture

## Repository Structure

```
makeor_codeagent/
├── 📄 README.md                      # Main documentation
├── 🚀 main.py                        # Core application entry point
├── 🛠️ project_manager.py             # Project management CLI
├── 🤖 prompts.py                     # AI agent prompts and templates
├── 🔧 tools.py                       # Utility functions and tools
├── ⚡ advanced_features.py           # RAG, caching, parallel processing
├── 📦 requirements.txt               # Production dependencies
├── 🔒 requirements.lock              # Locked dependency versions
├── ⚙️ install.sh                     # Installation script
├── 📋 .gitignore                     # Git ignore rules
├── 📁 generated_projects/            # Isolated project directories
│   ├── .project_metadata.json       # Project tracking database
│   ├── 20250830_HHMMSS_project1_xxx/ # Timestamped project folder
│   └── 20250830_HHMMSS_project2_yyy/ # Another project folder
├── 💾 .agent_cache/                  # Agent caching system
├── 🧠 .code_cache/                   # RAG embeddings database
├── 📊 .version_cache.json           # Version tracking
└── 📚 docs/                          # Additional documentation
    ├── DYNAMIC_PROJECT_MANAGEMENT.md
    └── ENHANCED_CAPABILITIES.md
```

## Core Components

### 🚀 **main.py** - Application Core
- Multi-agent workflow orchestration
- Project-aware code generation
- Advanced features integration
- Command-line interface

### 🛠️ **project_manager.py** - Project Management
- Dynamic project directory creation
- Project isolation and cleanup
- Metadata tracking and CLI tools
- Project switching capabilities

### 🤖 **prompts.py** - AI Agent System
- PLANNER: Strategic application planning
- ARCHITECT: System design and file manifests
- CODER: Full-stack code generation
- TESTER: Test creation and validation
- REVIEWER: Code quality assurance
- CONDUCTOR: Workflow orchestration

### ⚡ **advanced_features.py** - Enterprise Features
- **RAG System**: Code embeddings and context retrieval
- **Parallel Testing**: Asyncio-based multi-service testing
- **Advanced Caching**: SQLite-based error pattern caching
- **Version Pinning**: Aggressive dependency locking

### 🔧 **tools.py** - Utility Functions
- File system operations
- Process execution
- HTTP probing and service management
- Enhanced error handling and context management

## Production Features

### 🏢 **Enterprise-Grade Architecture**
- ✅ Complete project isolation
- ✅ Advanced error handling and recovery
- ✅ Intelligent caching and performance optimization
- ✅ Version control and dependency management
- ✅ Scalable multi-agent orchestration

### 🔒 **Security and Reliability**
- ✅ Safe file operations with proper path validation
- ✅ Resource isolation between projects
- ✅ Error containment and graceful degradation
- ✅ Secure API key management
- ✅ Production-ready logging and monitoring

### 📈 **Performance Optimization**
- ✅ RAG-based context retrieval for faster code generation
- ✅ Parallel test execution for multi-service applications
- ✅ Intelligent caching of research results and error patterns
- ✅ Optimized workflow with bounded iterations
- ✅ Efficient file system operations

### 🎯 **Developer Experience**
- ✅ Simple command-line interface
- ✅ Comprehensive project management tools
- ✅ Clear project organization and structure
- ✅ Detailed progress reporting and status updates
- ✅ Easy installation and setup process

## Usage Patterns

### Basic Usage
```bash
# Generate a simple application
python main.py "Create a REST API with FastAPI"

# Custom project with cleanup
python main.py --project my_api --cleanup "Create a REST API"
```

### Project Management
```bash
# List all projects
python project_manager.py list

# Clean up old projects
python project_manager.py cleanup 3

# Create project with custom name
python project_manager.py create "my_project"
```

### Advanced Features
The system automatically includes:
- RAG-based code context retrieval
- Parallel testing for multi-service apps
- Intelligent error pattern caching
- Aggressive dependency version pinning
- Complete project isolation

## Integration Points

### API Integration
- Mistral AI for code generation
- LangChain for agent orchestration
- LangGraph for workflow management

### Storage Systems
- SQLite for caching and embeddings
- JSON for project metadata
- File system for project isolation

### External Tools
- Git for version control
- Python package management
- Process execution for testing and validation

This architecture provides a production-ready, enterprise-grade code generation platform with advanced AI capabilities and professional project management.
