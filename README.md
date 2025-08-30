# MakeOR Code Agent - Production Edition

An enterprise-grade multi-agent code generation system with advanced features and dynamic project management.

## Overview

MakeOR Code Agent is a sophisticated AI-powered development platform that generates complete, production-ready applications using advanced multi-agent workflows, RAG systems, parallel processing, and intelligent project management.

## Core Features

### 🤖 **Multi-Agent Architecture**
- **PLANNER**: Strategic application planning with 5-level reasoning
- **ARCHITECT**: Enterprise file manifest and system design
- **CODER**: Full-stack code generation with tool execution
- **TESTER**: Golden test creation and validation
- **REVIEWER**: Intelligent code review and quality assurance
- **CONDUCTOR**: Workflow orchestration with bounded loops

### 🚀 **Advanced Enterprise Features**
- **RAG System**: Code embeddings and intelligent context retrieval
- **Parallel Testing**: Multi-service test execution with asyncio
- **Advanced Caching**: Error patterns and research result caching
- **Version Pinning**: Aggressive dependency version locking
- **Dynamic Project Management**: Isolated project directories

### 📁 **Project Management**
- **Unique Project IDs**: Timestamped project identification
- **Project Isolation**: Complete separation of generated applications
- **Automatic Cleanup**: Optional deletion of previous projects
- **Metadata Tracking**: Comprehensive project information storage

## Installation

```bash
# Clone the repository
git clone https://github.com/kprasad7/makeor_codeagent.git
cd makeor_codeagent

# Install dependencies
pip install -r requirements.txt

# Set up environment
export MISTRAL_API_KEY="your_api_key_here"
```

## Usage

### Basic Usage
```bash
# Generate a simple application
python main.py "Create a FastAPI blog application with user authentication"

# Custom project name with cleanup
python main.py --project my_blog --cleanup "Create a blog API with PostgreSQL"
```

### Project Management
```bash
# List all projects
python project_manager.py list

# Create specific project
python project_manager.py create "my_project_name"

# Cleanup old projects (keep last 3)
python project_manager.py cleanup 3

# Switch to existing project
python project_manager.py switch <project_id>
```

### Advanced Options
```bash
# Help and options
python main.py --help

# Available flags:
--cleanup         # Delete previous projects before creating new one
--project <name>  # Custom project name
```

## Generated Project Structure

Each generated project follows a standardized structure:

```
generated_projects/
├── 20250830_HHMMSS_projectname_uuid/
│   ├── backend/          # Backend application code
│   ├── frontend/         # Frontend application code
│   ├── database/         # Database schemas and migrations
│   ├── docs/            # Documentation and API specs
│   ├── tests/           # Test suites and fixtures
│   ├── scripts/         # Build and deployment scripts
│   ├── main.py          # Application entry point
│   ├── models.py        # Data models
│   ├── requirements.txt # Python dependencies
│   └── ...              # Additional generated files
└── .project_metadata.json  # Project tracking database
```

## Architecture

### Multi-Agent Workflow
```
USER GOAL → PLANNER → ARCHITECT → CODER → CONDUCTOR
                                     ↓
TESTER ← SERVICE_MANAGER ← CONDUCTOR → RUNNER
   ↓                                      ↓
REVIEWER ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ← CONDUCTOR
   ↓                                      ↓
FIXER → CONDUCTOR → PREVIEW (SUCCESS)
```

### Advanced Features Integration
- **RAG Context**: Function-level embeddings for intelligent code suggestions
- **Parallel Execution**: Concurrent testing of frontend and backend services
- **Error Caching**: Fingerprinting and caching of error patterns
- **Research Caching**: Cached web research results for faster development

## Configuration

### Environment Variables
```bash
MISTRAL_API_KEY=your_mistral_api_key
```

### System Requirements
- Python 3.8+
- 4GB+ RAM recommended
- SQLite for caching (included)
- Internet connection for AI API calls

## Production Deployment

### Docker Support
```bash
# Build and run with Docker Compose
docker-compose up --build

# Backend only
docker build -f Dockerfile.backend -t makeor-backend .

# Frontend only  
docker build -f Dockerfile.frontend -t makeor-frontend .
```

### Security Considerations
- API keys should be stored securely
- Generated code should be reviewed before deployment
- File permissions should be properly configured
- Network access should be restricted in production

## API Reference

### Core Functions
- `run_workflow(prompt, project_name=None, cleanup=False)`: Main entry point
- `ProjectDirectoryManager`: Project lifecycle management
- `integrate_advanced_features()`: Advanced feature initialization

### Tool Functions
- `fs_write_file(path, content)`: File writing with safety checks
- `fs_read(path)`: File reading with error handling
- `proc_run(command, cwd)`: Process execution with timeout
- `python_test_runner(test_code)`: Test execution framework

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new features
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- GitHub Issues: [Repository Issues](https://github.com/kprasad7/makeor_codeagent/issues)
- Documentation: See `/docs` in generated projects
- Advanced Features: See `ENHANCED_CAPABILITIES.md`
- Project Management: See `DYNAMIC_PROJECT_MANAGEMENT.md`