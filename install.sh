#!/bin/bash

# MakeOR Code Agent - Production Installation Script

set -e

echo "🚀 Installing MakeOR Code Agent - Production Edition"
echo "=================================================="

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Error: Python 3.8+ is required. Found: $python_version"
    exit 1
fi

echo "✅ Python version check passed: $python_version"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Set up API key (optional)
if [ ! -f ".env" ]; then
    echo "🔑 Setting up environment variables..."
    cat > .env << EOF
# MakeOR Code Agent Configuration
MISTRAL_API_KEY=your_mistral_api_key_here

# Optional: Customize cache directories
AGENT_CACHE_DIR=.agent_cache
CODE_CACHE_DIR=.code_cache
PROJECTS_DIR=generated_projects
EOF
    echo "✅ Created .env file. Please add your Mistral API key."
else
    echo "✅ .env file already exists."
fi

# Create necessary directories
echo "📁 Creating cache directories..."
mkdir -p .agent_cache
mkdir -p .code_cache
mkdir -p generated_projects

# Set proper permissions
chmod +x main.py
chmod +x project_manager.py

echo ""
echo "🎉 Installation completed successfully!"
echo ""
echo "📋 Next steps:"
echo "   1. Add your Mistral API key to .env file"
echo "   2. Activate the virtual environment: source venv/bin/activate"
echo "   3. Run your first project: python main.py 'Create a simple API'"
echo ""
echo "📖 For more information, see README.md"
echo "🔧 For project management, use: python project_manager.py --help"
