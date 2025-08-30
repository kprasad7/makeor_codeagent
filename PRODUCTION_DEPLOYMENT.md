# MakeOR Code Agent - Production Deployment Guide

## Production Setup

### 1. Environment Configuration

Copy the production environment template:
```bash
cp .env.production .env
# Edit .env with your production values
```

### 2. Security Hardening

#### API Key Management
```bash
# Use environment variables for API keys
export MISTRAL_API_KEY="your_secure_api_key"
# Or use a secrets management system
```

#### File System Security
```bash
# Set proper permissions
chmod 755 main.py project_manager.py
chmod 644 *.md *.txt *.json
chmod 700 .env

# Create restricted user for running the service
useradd -r -s /bin/false makeor
chown -R makeor:makeor /app
```

### 3. System Requirements

#### Minimum Requirements
- CPU: 2 cores
- RAM: 4GB
- Storage: 20GB SSD
- Network: Stable internet connection

#### Recommended Requirements
- CPU: 4+ cores
- RAM: 8GB+
- Storage: 100GB+ SSD
- Network: High-speed internet

### 4. Docker Production Deployment

#### Build Production Images
```bash
# Build optimized images
docker build -f Dockerfile.backend -t makeor-agent:latest .
docker build -f Dockerfile.frontend -t makeor-frontend:latest .
```

#### Production Docker Compose
```yaml
version: '3.8'
services:
  makeor-agent:
    image: makeor-agent:latest
    restart: unless-stopped
    environment:
      - NODE_ENV=production
      - MISTRAL_API_KEY=${MISTRAL_API_KEY}
    volumes:
      - ./data:/app/data:rw
      - ./logs:/app/logs:rw
      - ./generated_projects:/app/generated_projects:rw
    ports:
      - "8080:8080"
    deploy:
      resources:
        limits:
          memory: 4g
          cpus: '2'
        reservations:
          memory: 2g
          cpus: '1'
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 5. Monitoring and Logging

#### Log Configuration
```bash
# Create log directories
mkdir -p /app/logs
touch /app/logs/makeor.log
chown makeor:makeor /app/logs/makeor.log

# Configure log rotation
cat > /etc/logrotate.d/makeor << EOF
/app/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    notifempty
    create 644 makeor makeor
}
EOF
```

#### Health Monitoring
```bash
# Add health check endpoint monitoring
curl -f http://localhost:8080/health || exit 1
```

### 6. Database and Storage

#### Backup Configuration
```bash
# Create backup script
cat > /app/scripts/backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/app/backups"
mkdir -p $BACKUP_DIR

# Backup databases
cp /app/data/*.db $BACKUP_DIR/db_backup_$DATE.db

# Backup projects metadata
tar -czf $BACKUP_DIR/projects_backup_$DATE.tar.gz /app/generated_projects/.project_metadata.json

# Cleanup old backups (keep last 30 days)
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
EOF

chmod +x /app/scripts/backup.sh

# Add to crontab
echo "0 2 * * * /app/scripts/backup.sh" | crontab -u makeor -
```

### 7. Performance Optimization

#### System Tuning
```bash
# Increase file descriptor limits
echo "makeor soft nofile 65536" >> /etc/security/limits.conf
echo "makeor hard nofile 65536" >> /etc/security/limits.conf

# Optimize Python performance
export PYTHONOPTIMIZE=1
export PYTHONUNBUFFERED=1
```

#### Cache Optimization
```bash
# Configure cache directories
mkdir -p /app/cache/{rag,research,embeddings}
chown -R makeor:makeor /app/cache
```

### 8. Security Best Practices

#### Network Security
```bash
# Configure firewall
ufw allow 8080/tcp
ufw enable

# Use reverse proxy (nginx)
cat > /etc/nginx/sites-available/makeor << 'EOF'
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Security headers
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";
    }
}
EOF
```

#### SSL/TLS Configuration
```bash
# Install Let's Encrypt certificate
certbot --nginx -d your-domain.com
```

### 9. Deployment Commands

#### Start Production Services
```bash
# Using Docker Compose
docker-compose -f docker-compose.prod.yml up -d

# Using systemd
sudo systemctl enable makeor-agent
sudo systemctl start makeor-agent
```

#### Update Deployment
```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up --build -d
```

### 10. Maintenance Tasks

#### Regular Maintenance
```bash
# Daily tasks
- Check log files for errors
- Monitor disk usage
- Verify backup completion
- Check system resources

# Weekly tasks  
- Update dependencies
- Review generated projects
- Clean up old cache files
- Performance monitoring

# Monthly tasks
- Security updates
- Capacity planning
- Backup testing
- Documentation updates
```

#### Troubleshooting
```bash
# Check service status
docker-compose logs makeor-agent

# Monitor resource usage
docker stats

# Check database integrity
sqlite3 /app/data/cache.db "PRAGMA integrity_check;"

# Test API connectivity
curl -X POST http://localhost:8080/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test connection"}'
```

## Production Checklist

- [ ] Environment variables configured
- [ ] SSL/TLS certificates installed
- [ ] Firewall rules configured
- [ ] Backup system tested
- [ ] Monitoring systems active
- [ ] Log rotation configured
- [ ] Performance tuning applied
- [ ] Security hardening complete
- [ ] Health checks working
- [ ] Documentation updated
