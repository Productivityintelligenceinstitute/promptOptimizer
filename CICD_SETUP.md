# CI/CD Setup Guide - Production Level

## 🚀 Overview
This guide helps you set up a production-ready CI/CD pipeline using GitHub Actions to automate:
- Building Docker images
- Pushing to AWS ECR (jpo-images)
- Deploying to EC2 instances

---

## 📋 Prerequisites Checklist

### 1. **GitHub Repository**
- [ ] Create a GitHub repository for your code
- [ ] Push your code to the repository
- [ ] Set up branch protection rules for `main` branch

### 2. **AWS Resources**
- [ ] ECR Repository: `jpo-images` (already created ✓)
- [ ] EC2 instance(s) running and accessible
- [ ] IAM user with appropriate permissions (see below)
- [ ] Security groups configured

### 3. **Local Setup**
- [ ] Docker installed and working
- [ ] AWS CLI installed and configured
- [ ] Git configured with your GitHub account

---

## 🔐 AWS IAM Permissions

Create an IAM user for GitHub Actions with these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## 🔑 GitHub Secrets Configuration

Go to your GitHub repo → Settings → Secrets and variables → Actions → New repository secret

### Required Secrets:

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `AWS_ACCESS_KEY_ID` | AWS IAM access key | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM secret key | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| `AWS_REGION` | AWS region | `us-east-1` |
| `AWS_ACCOUNT_ID` | Your AWS account ID | `123456789012` |
| `ECR_REPOSITORY` | ECR repository name | `jpo-images` |
| `EC2_HOST` | Production EC2 IP/hostname | `3.145.123.45` or `ec2-xxx.compute.amazonaws.com` |
| `EC2_STAGING_HOST` | Staging EC2 (optional) | `3.145.123.46` |
| `EC2_USERNAME` | EC2 SSH username | `ubuntu` or `ec2-user` |
| `EC2_SSH_PRIVATE_KEY` | Private SSH key for EC2 | `-----BEGIN RSA PRIVATE KEY-----\n...` |

### Application Secrets (if needed):
- `DATABASE_URL`
- `FIREBASE_CREDENTIALS`
- Any other environment variables from your `.env`

---

## 🖥️ EC2 Instance Setup

### 1. **Install Docker on EC2:**
```bash
# For Ubuntu
sudo apt update
sudo apt install -y docker.io
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ubuntu  # or your username

# For Amazon Linux
sudo yum update -y
sudo yum install -y docker
sudo service docker start
sudo usermod -aG docker ec2-user
```

### 2. **Install AWS CLI on EC2:**
```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

### 3. **Configure AWS CLI on EC2:**
```bash
aws configure
# Enter your credentials or use IAM role (recommended)
```

### 4. **Create Environment File on EC2:**
```bash
# Production
sudo nano /home/ubuntu/.env.production

# Add your environment variables:
DATABASE_URL=postgresql://user:pass@host:5432/db
FIREBASE_CREDENTIALS={"type":"service_account",...}
# ... other vars
```

### 5. **Create Upload Directory:**
```bash
mkdir -p /home/ubuntu/uploaded_kb
sudo chown -R ubuntu:ubuntu /home/ubuntu/uploaded_kb
```

### 6. **Security Group Configuration:**
- Inbound Rules:
  - SSH (22) from your IP
  - HTTP (80) from anywhere (or your domain)
  - HTTPS (443) from anywhere
  - Custom (8000) for your app

---

## 📁 Repository Structure

After setup, your repository should have:

```
.github/
  workflows/
    ci.yml                    # Testing and linting
    deploy-production.yml     # Production deployment
    deploy-staging.yml        # Staging deployment (optional)
.gitignore
.dockerignore
Dockerfile
docker-compose.yml
requirements.txt
CICD_SETUP.md              # This file
README.md
```

---

## 🔄 Workflow Explanation

### **Branch Strategy:**
- `main` → Production deployment
- `develop` → Staging deployment (optional)
- Feature branches → Only CI tests

### **Deployment Flow:**

1. **Developer pushes to `main`**
2. **GitHub Actions triggers:**
   - Checks out code
   - Configures AWS credentials
   - Logs into ECR
   - Builds Docker image
   - Tags with commit SHA + latest
   - Pushes to ECR
   - SSHs into EC2
   - Pulls new image on EC2
   - Stops old container
   - Starts new container
   - Cleans up old images

---

## 🚦 Getting Started

### Step 1: Push Code to GitHub
```bash
# Initialize git (if not already)
git init
git add .
git commit -m "Initial commit"

# Add remote and push
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

### Step 2: Add GitHub Secrets
- Go through each secret in the table above
- Add them to GitHub repository settings

### Step 3: Generate SSH Key for EC2
```bash
# On your local machine
ssh-keygen -t rsa -b 4096 -C "github-actions" -f ~/.ssh/github-actions-key

# Copy public key to EC2
ssh-copy-id -i ~/.ssh/github-actions-key.pub ubuntu@YOUR_EC2_IP

# Copy private key content to GitHub Secret EC2_SSH_PRIVATE_KEY
cat ~/.ssh/github-actions-key
```

### Step 4: Test Deployment
```bash
# Make a small change and push
git add .
git commit -m "Test CI/CD pipeline"
git push origin main

# Check GitHub Actions tab for workflow progress
```

---

## 🛡️ Production Best Practices

### 1. **Environment Separation**
- Separate EC2 instances for staging/production
- Different ECR tags (latest vs staging)
- Separate environment files

### 2. **Secrets Management**
- Use AWS Secrets Manager or Parameter Store
- Rotate credentials regularly
- Never commit secrets to git

### 3. **Monitoring & Logging**
- Set up CloudWatch logs
- Add health check endpoints
- Monitor container status
- Set up alerts for failures

### 4. **Rollback Strategy**
```bash
# Keep previous image tag
# If deployment fails, manually rollback:
docker pull <ecr-registry>/jpo-images:<previous-sha>
docker stop promptoptimizer
docker run -d --name promptoptimizer <ecr-registry>/jpo-images:<previous-sha>
```

### 5. **Database Migrations**
- Run Alembic migrations before deployment
- Add migration step to workflow if needed

### 6. **Zero-Downtime Deployment**
- Use blue-green deployment
- Or run multiple containers with load balancer

### 7. **Backup Strategy**
- Regular database backups
- Backup uploaded_kb volume
- Backup environment configurations

---

## 🔍 Health Check Endpoint

Add a health check to your FastAPI app:

```python
# In main.py
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }
```

---

## 🐛 Troubleshooting

### Pipeline fails at ECR login:
- Check AWS credentials in GitHub Secrets
- Verify IAM permissions

### SSH connection fails:
- Check EC2 security group
- Verify SSH key is correct
- Ensure EC2_HOST is accessible

### Container fails to start:
- Check environment variables
- Verify volume mounts exist
- Check Docker logs: `docker logs promptoptimizer`

### Image pull fails on EC2:
- Ensure AWS CLI is configured on EC2
- Check ECR permissions
- Verify internet connectivity

---

## 📊 Monitoring Commands

```bash
# On EC2 - Check running containers
docker ps

# View logs
docker logs -f promptoptimizer

# Check resource usage
docker stats promptoptimizer

# List images
docker images | grep jpo-images
```

---

## 🎯 Next Steps

1. **Add comprehensive tests** to CI workflow
2. **Set up database migration automation**
3. **Implement monitoring** (CloudWatch, Datadog, etc.)
4. **Add Slack/Email notifications** for deployments
5. **Set up staging environment**
6. **Configure CDN** for static assets
7. **Add automated backups**
8. **Implement blue-green deployment**

---

## 📝 Additional Workflows to Consider

- **Scheduled Security Scans**: Weekly dependency checks
- **Automated Backups**: Daily database backups
- **Performance Tests**: Load testing before production
- **Documentation Generation**: Auto-generate API docs

---

## 🔗 Useful Links

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [AWS ECR Documentation](https://docs.aws.amazon.com/ecr/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)

---

## ✅ Pre-Deployment Checklist

Before your first production deployment:

- [ ] All GitHub Secrets configured
- [ ] EC2 instance prepared with Docker & AWS CLI
- [ ] Environment file created on EC2
- [ ] SSH keys configured
- [ ] Security groups configured
- [ ] Health check endpoint added
- [ ] Database backed up
- [ ] Rollback plan documented
- [ ] Team notified of deployment
- [ ] Monitoring set up

---

**Need Help?** Check GitHub Actions logs for detailed error messages.
