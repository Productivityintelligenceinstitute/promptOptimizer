# GitHub Secrets Configuration Template

## Copy this checklist when setting up GitHub Secrets

Go to: **Your GitHub Repo → Settings → Secrets and variables → Actions → New repository secret**

---

### AWS Credentials

```
Secret Name: AWS_ACCESS_KEY_ID
Value: AKIAIOSFODNN7EXAMPLE
Description: AWS IAM user access key ID for ECR access
```

```
Secret Name: AWS_SECRET_ACCESS_KEY
Value: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
Description: AWS IAM user secret access key
```

```
Secret Name: AWS_REGION
Value: us-east-1
Description: AWS region where ECR repository is located
```

```
Secret Name: AWS_ACCOUNT_ID
Value: 123456789012
Description: Your AWS account ID (12 digits)
```

---

### ECR Repository

```
Secret Name: ECR_REPOSITORY
Value: jpo-images
Description: ECR repository name for Docker images
```

---

### EC2 Production Instance

```
Secret Name: EC2_HOST
Value: 3.145.123.45
Description: Production EC2 instance public IP or hostname
```

```
Secret Name: EC2_USERNAME
Value: ubuntu
Description: SSH username for EC2 (ubuntu, ec2-user, etc.)
```

```
Secret Name: EC2_SSH_PRIVATE_KEY
Value: -----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
...
-----END RSA PRIVATE KEY-----
Description: Private SSH key for GitHub Actions to access EC2
How to generate: ssh-keygen -t rsa -b 4096 -f ~/.ssh/github-deploy
```

---

### EC2 Staging Instance (Optional)

```
Secret Name: EC2_STAGING_HOST
Value: 3.145.123.46
Description: Staging EC2 instance public IP or hostname
```

---

### Application Secrets (If needed in build)

```
Secret Name: DATABASE_URL
Value: postgresql://user:password@host:5432/dbname
Description: Database connection string
```

```
Secret Name: JWT_SECRET
Value: your-super-secret-jwt-key
Description: JWT token signing secret
```

```
Secret Name: FIREBASE_CREDENTIALS
Value: {"type":"service_account","project_id":"..."}
Description: Firebase service account JSON
```

---

## How to Get These Values

### AWS_ACCESS_KEY_ID & AWS_SECRET_ACCESS_KEY
1. Go to AWS Console → IAM → Users
2. Click "Create user" → Name: `github-actions-deployer`
3. Attach policy: `AmazonEC2ContainerRegistryFullAccess`
4. Create user → Security credentials → Create access key
5. Choose "Third-party service" → Create
6. **Save these values immediately - you can't see the secret again!**

### AWS_REGION
- Check your ECR repository location
- Common values: `us-east-1`, `us-west-2`, `eu-west-1`, `ap-southeast-1`
- Find it: AWS Console → ECR → Your repository → Copy region from URL

### AWS_ACCOUNT_ID
- Top right of AWS Console → Click your username
- 12-digit number shown in dropdown
- Or run: `aws sts get-caller-identity --query Account --output text`

### EC2_HOST
- AWS Console → EC2 → Instances
- Click your instance → Copy "Public IPv4 address" or "Public IPv4 DNS"
- Example: `3.145.123.45` or `ec2-3-145-123-45.us-east-1.compute.amazonaws.com`

### EC2_USERNAME
- Ubuntu AMI: `ubuntu`
- Amazon Linux: `ec2-user`
- Red Hat: `ec2-user`
- Debian: `admin`
- Check your SSH command: `ssh username@host`

### EC2_SSH_PRIVATE_KEY
Generate a new key specifically for GitHub Actions:

```bash
# Generate key pair
ssh-keygen -t rsa -b 4096 -f ~/.ssh/github-deploy -N ""

# This creates:
# ~/.ssh/github-deploy (private key) ← This goes to GitHub Secret
# ~/.ssh/github-deploy.pub (public key) ← This goes to EC2

# Copy public key to EC2
ssh-copy-id -i ~/.ssh/github-deploy.pub ubuntu@YOUR_EC2_IP

# Or manually:
cat ~/.ssh/github-deploy.pub
# SSH to EC2 and paste into ~/.ssh/authorized_keys

# Get private key content for GitHub Secret
cat ~/.ssh/github-deploy
# Copy EVERYTHING including the BEGIN and END lines
```

---

## Verification Commands

After adding secrets, verify they work:

### Test AWS Credentials
```bash
# On your local machine with the IAM credentials:
export AWS_ACCESS_KEY_ID="your-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="your-region"

aws ecr describe-repositories --repository-names jpo-images
# Should show repository details without error
```

### Test SSH Key
```bash
# On your local machine:
ssh -i ~/.ssh/github-deploy ubuntu@YOUR_EC2_IP

# Should log in without password
# If it works, GitHub Actions will also work
```

### Test ECR Login from EC2
```bash
# SSH to EC2:
ssh ubuntu@YOUR_EC2_IP

# Try to login to ECR:
aws ecr get-login-password --region YOUR_REGION | \
  docker login --username AWS --password-stdin \
  YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com

# Should say "Login Succeeded"
```

---

## Security Best Practices

✅ **DO:**
- Use separate IAM users for different environments
- Rotate credentials every 90 days
- Use least-privilege IAM policies
- Enable MFA on AWS root account
- Regularly audit secret usage in GitHub Actions logs

❌ **DON'T:**
- Commit secrets to Git
- Share secrets in chat/email
- Use production secrets in development
- Give IAM users more permissions than needed
- Reuse SSH keys across multiple purposes

---

## Troubleshooting

### "Error: Secrets not found"
- Double-check secret names match exactly (case-sensitive)
- Verify you're in the correct repository
- Secrets are only available to workflows, not visible in repo settings after creation

### "AWS authentication failed"
- Verify IAM user has correct permissions
- Check if credentials are expired
- Ensure region matches ECR location

### "SSH connection failed"
- Verify EC2 security group allows SSH (port 22)
- Check if SSH key is correctly formatted (include BEGIN/END lines)
- Ensure public key is in EC2's `~/.ssh/authorized_keys`
- Try the key locally first: `ssh -i ~/.ssh/github-deploy ubuntu@EC2_IP`

---

## Secret Update Procedure

When you need to update a secret:

1. GitHub → Repo → Settings → Secrets and variables → Actions
2. Click the secret name
3. Click "Update secret"
4. Enter new value
5. Click "Update secret"
6. **No need to restart workflows - they use new value immediately**

---

## Backup Your Secrets

**Important:** GitHub doesn't show secret values after creation!

Create a secure backup:
```bash
# Create encrypted backup file
cat > github-secrets.txt << EOF
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUt...
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012
ECR_REPOSITORY=jpo-images
EC2_HOST=3.145.123.45
EC2_USERNAME=ubuntu
# EC2_SSH_PRIVATE_KEY is in ~/.ssh/github-deploy
EOF

# Encrypt it
gpg -c github-secrets.txt

# Delete plaintext
shred -u github-secrets.txt

# Store github-secrets.txt.gpg in a secure location (password manager)
```

---

## Quick Copy Template

For quick setup, fill this out and copy to a secure note:

```
# GitHub Secrets for promptOptimizer CI/CD
# Created: [DATE]
# AWS Account: [ACCOUNT_ID]

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=
AWS_ACCOUNT_ID=
ECR_REPOSITORY=jpo-images
EC2_HOST=
EC2_USERNAME=ubuntu
EC2_STAGING_HOST=
EC2_SSH_PRIVATE_KEY=
  [Paste multi-line private key here]

# Optional Application Secrets
DATABASE_URL=
JWT_SECRET=
FIREBASE_CREDENTIALS=
```

---

**Ready to add secrets?** Copy this template and start filling in your values! 🔐
