# Quick Start: CI/CD Pipeline Setup

## 🎯 **BEST APPROACH - STEP BY STEP**

### Step 1: Push Your Code to GitHub
```bash
# 1. Create a new repository on GitHub (e.g., "promptOptimizer")

# 2. In your local project directory:
git init
git add .
git commit -m "Initial commit - FastAPI Prompt Optimizer"

# 3. Add remote and push
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

---

### Step 2: Create IAM User for GitHub Actions

1. Go to AWS Console → IAM → Users → Add User
2. Name: `github-actions-deployer`
3. Attach policies:
   - `AmazonEC2ContainerRegistryFullAccess`
4. Create user and save credentials

---

### Step 3: Configure GitHub Secrets

Go to your GitHub repo → Settings → Secrets and variables → Actions

Add these secrets:

| Secret | How to Get It | Example Value |
|--------|---------------|---------------|
| `AWS_ACCESS_KEY_ID` | From IAM user created above | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | From IAM user | `wJalrXUt...` |
| `AWS_REGION` | Your ECR region | `us-east-1` |
| `AWS_ACCOUNT_ID` | AWS Console → Account | `123456789012` |
| `ECR_REPOSITORY` | Your ECR repo name | `jpo-images` |
| `EC2_HOST` | EC2 instance public IP | `3.145.123.45` |
| `EC2_USERNAME` | SSH user | `ubuntu` or `ec2-user` |
| `EC2_SSH_PRIVATE_KEY` | See Step 4 | `-----BEGIN RSA...` |

---

### Step 4: Set Up SSH Key for EC2 Access

```bash
# On your local machine:
ssh-keygen -t rsa -b 4096 -f ~/.ssh/github-actions-deploy -N ""

# Copy public key to EC2:
ssh-copy-id -i ~/.ssh/github-actions-deploy.pub ubuntu@YOUR_EC2_IP

# Test SSH connection:
ssh -i ~/.ssh/github-actions-deploy ubuntu@YOUR_EC2_IP

# Copy the PRIVATE key content to GitHub Secret 'EC2_SSH_PRIVATE_KEY':
cat ~/.ssh/github-actions-deploy
# Copy everything including -----BEGIN and -----END lines
```

---

### Step 5: Prepare EC2 Instance

SSH into your EC2 and run:

```bash
# Install Docker
sudo apt update && sudo apt install -y docker.io
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
# Logout and login again for group changes

# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Configure AWS CLI (use IAM role or credentials)
aws configure

# Create environment file
nano ~/.env.production
# Add all your environment variables:
# DATABASE_URL=...
# FIREBASE_CREDENTIALS=...
# etc.

# Create upload directory
mkdir -p ~/uploaded_kb
```

---

### Step 6: Test Your First Deployment

```bash
# Make a small change in your code
echo "# CI/CD Enabled" >> README.md

# Commit and push
git add .
git commit -m "Enable CI/CD pipeline"
git push origin main

# Watch deployment in GitHub:
# Go to your repo → Actions tab → Click on the running workflow
```

---

## 🎉 **What Happens After Push:**

1. ✅ GitHub Actions triggers automatically
2. ✅ Builds Docker image
3. ✅ Pushes to ECR (jpo-images)
4. ✅ SSHs into EC2
5. ✅ Pulls latest image
6. ✅ Restarts container
7. ✅ Your app is live!

---

## 🔄 **Workflow Branches:**

- **Push to `main`** → Deploys to Production EC2
- **Push to `develop`** → Deploys to Staging EC2 (if configured)
- **Pull Request** → Runs tests only (no deployment)

---

## 📝 **What You Need Before Going Live:**

### Mandatory:
- ✅ GitHub repository created
- ✅ AWS credentials (IAM user)
- ✅ ECR repository (jpo-images) - Already have ✓
- ✅ EC2 instance with Docker installed
- ✅ SSH access to EC2
- ✅ GitHub Secrets configured
- ✅ Environment variables file on EC2

### Recommended for Production:
- 🔒 **SSL/TLS Certificate** (Let's Encrypt + Nginx)
- 🌐 **Domain Name** (Route 53)
- 📊 **Monitoring** (CloudWatch, Datadog, New Relic)
- 🔔 **Alerts** (SNS, Slack webhooks)
- 💾 **Database Backups** (Automated daily)
- 🔐 **Secrets Manager** (AWS Secrets Manager)
- 🚦 **Health Checks** (Load balancer)
- 📈 **Logging** (CloudWatch Logs, ELK stack)
- 🔄 **Rollback Strategy**
- 🧪 **Staging Environment**
- 🛡️ **WAF** (Web Application Firewall)
- 📦 **CDN** (CloudFront for static assets)

---

## 🔒 **Production-Level Enhancements Needed:**

### 1. **Nginx Reverse Proxy with SSL**
```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 2. **Database Migration in Pipeline**
Add to workflow before deployment:
```yaml
- name: Run Database Migrations
  run: |
    docker exec promptoptimizer alembic upgrade head
```

### 3. **Auto-scaling with ECS/EKS** (Advanced)
- Instead of EC2, use ECS Fargate or EKS
- Auto-scales based on load
- Better for production

### 4. **Multi-Region Deployment**
- Deploy to multiple AWS regions
- Use Route 53 for failover

### 5. **Blue-Green Deployment**
```yaml
# Run new container on different port
# Test health
# Switch traffic
# Kill old container
```

---

## 🐛 **Common Issues & Solutions:**

| Issue | Solution |
|-------|----------|
| Pipeline fails at ECR login | Check AWS credentials in GitHub Secrets |
| SSH timeout | Verify security group allows SSH from GitHub IPs |
| Container won't start | Check `.env.production` file exists on EC2 |
| Old container still running | Container name conflict - check `docker ps` |
| Port already in use | Stop existing container: `docker stop promptoptimizer` |

---

## 📞 **Support Checklist:**

Before asking for help, verify:
1. All GitHub Secrets are added correctly
2. EC2 security group allows inbound SSH (port 22)
3. Docker is running on EC2: `sudo systemctl status docker`
4. AWS CLI configured on EC2: `aws sts get-caller-identity`
5. Environment file exists: `ls -la ~/.env.production`
6. GitHub Actions logs for error details

---

## 🚀 **Next Steps After Setup:**

1. Add unit tests to CI workflow
2. Set up staging environment
3. Configure monitoring and alerts
4. Implement automated backups
5. Add Slack notifications for deployments
6. Set up log aggregation
7. Add performance monitoring
8. Implement feature flags

---

**For detailed step-by-step guide, see [CICD_SETUP.md](./CICD_SETUP.md)**
