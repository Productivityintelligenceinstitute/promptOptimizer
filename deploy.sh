#!/bin/bash

# Manual deployment script (fallback if CI/CD fails)
# Usage: ./deploy.sh [environment]
# Example: ./deploy.sh production

set -e  # Exit on error

ENVIRONMENT=${1:-production}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ECR_REGISTRY="<YOUR_AWS_ACCOUNT_ID>.dkr.ecr.<YOUR_REGION>.amazonaws.com"
ECR_REPOSITORY="jpo-images"
IMAGE_TAG="${ENVIRONMENT}-${TIMESTAMP}"

echo "🚀 Starting deployment to ${ENVIRONMENT}..."

# Step 1: Build Docker image
echo "📦 Building Docker image..."
docker build -t ${ECR_REPOSITORY}:${IMAGE_TAG} \
             -t ${ECR_REPOSITORY}:${ENVIRONMENT}-latest \
             -f Dockerfile .

# Step 2: Login to ECR
echo "🔐 Logging into AWS ECR..."
aws ecr get-login-password --region <YOUR_REGION> | \
    docker login --username AWS --password-stdin ${ECR_REGISTRY}

# Step 3: Tag images
echo "🏷️  Tagging images..."
docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} ${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}
docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} ${ECR_REGISTRY}/${ECR_REPOSITORY}:${ENVIRONMENT}-latest

# Step 4: Push to ECR
echo "⬆️  Pushing to ECR..."
docker push ${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}
docker push ${ECR_REGISTRY}/${ECR_REPOSITORY}:${ENVIRONMENT}-latest

echo "✅ Image pushed successfully!"
echo "📝 Image: ${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"

# Step 5: Deploy to EC2 (optional - comment out if using GitHub Actions)
if [ "$2" == "--deploy" ]; then
    echo "🚢 Deploying to EC2..."
    EC2_HOST="<YOUR_EC2_IP>"
    
    ssh ubuntu@${EC2_HOST} << 'ENDSSH'
        # Login to ECR
        aws ecr get-login-password --region <YOUR_REGION> | \
            docker login --username AWS --password-stdin ${ECR_REGISTRY}
        
        # Pull latest image
        docker pull ${ECR_REGISTRY}/${ECR_REPOSITORY}:${ENVIRONMENT}-latest
        
        # Stop old container
        docker stop promptoptimizer-${ENVIRONMENT} || true
        docker rm promptoptimizer-${ENVIRONMENT} || true
        
        # Start new container
        docker run -d \
            --name promptoptimizer-${ENVIRONMENT} \
            --restart unless-stopped \
            -p 8000:8000 \
            --env-file /home/ubuntu/.env.${ENVIRONMENT} \
            -v /home/ubuntu/uploaded_kb:/app/uploaded_kb \
            ${ECR_REGISTRY}/${ECR_REPOSITORY}:${ENVIRONMENT}-latest
        
        # Cleanup
        docker image prune -af --filter "until=48h"
        
        echo "✅ Deployment complete!"
ENDSSH
fi

echo "🎉 All done!"
