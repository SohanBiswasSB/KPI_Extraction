#!/bin/bash

echo "🚀 Setting up KPI Extraction Platform..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p uploads
mkdir -p frontend/.next
mkdir -p backend/__pycache__

# Create environment files
echo "⚙️ Creating environment files..."

# Frontend environment
cat > frontend/.env.local << EOF
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=KPI Extraction Platform
EOF

# Backend environment
cat > backend/.env << EOF
DATABASE_URL=postgresql://kpi_user:kpi_password@localhost:5432/kpi_platform
OPENAI_API_KEY=your_openai_api_key_here
SECRET_KEY=your-secret-key-change-in-production
JWT_SECRET=your-jwt-secret-change-in-production
EOF

echo "⚠️  IMPORTANT: Please update the following environment variables:"
echo "   - backend/.env: Set your OpenAI API key"
echo "   - backend/.env: Change SECRET_KEY and JWT_SECRET for production"

# Install frontend dependencies
echo "📦 Installing frontend dependencies..."
cd frontend
npm install

# Install backend dependencies
echo "📦 Installing backend dependencies..."
cd ../backend
pip install -r requirements.txt

# Start services
echo "🐳 Starting Docker services..."
cd ..
docker-compose up -d

echo "⏳ Waiting for services to start..."
sleep 10

# Check if services are running
echo "🔍 Checking service status..."
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Backend is running at http://localhost:8000"
else
    echo "❌ Backend is not responding. Check logs with: docker-compose logs backend"
fi

if curl -f http://localhost:3000 > /dev/null 2>&1; then
    echo "✅ Frontend is running at http://localhost:3000"
else
    echo "❌ Frontend is not responding. Check logs with: docker-compose logs frontend"
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Update backend/.env with your OpenAI API key"
echo "2. Access the application at http://localhost:3000"
echo "3. Register a new account and start using the platform"
echo ""
echo "🔧 Useful commands:"
echo "  - View logs: docker-compose logs -f"
echo "  - Stop services: docker-compose down"
echo "  - Restart services: docker-compose restart"
echo "  - Update code: docker-compose up -d --build"
echo ""
echo "📚 Documentation: README.md" 