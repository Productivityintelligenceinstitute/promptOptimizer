# Rollback Guide

## 🔄 Quick Rollback to Previous Version

If a deployment causes issues, follow these steps to rollback:

### **Method 1: Using GitHub Actions (Recommended)**

1. **Find the previous working commit:**
   ```bash
   git log --oneline -10
   ```

2. **Revert to that commit:**
   ```bash
   git revert HEAD --no-edit
   git push origin main
   ```
   
   This will trigger a new deployment with the previous working code.

---

### **Method 2: Manual Rollback on EC2**

1. **SSH into EC2:**
   ```bash
   ssh ubuntu@YOUR_EC2_IP
   ```

2. **Find previous image:**
   ```bash
   # List all images
   docker images | grep jpo-images
   
   # You'll see something like:
   # jpo-images  abc123def  (current broken)
   # jpo-images  xyz789ghi  (previous working)
   ```

3. **Stop current container:**
   ```bash
   docker stop promptoptimizer
   docker rm promptoptimizer
   ```

4. **Start previous version:**
   ```bash
   ECR_REGISTRY="<YOUR_ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com"
   PREVIOUS_TAG="xyz789ghi"  # Replace with actual tag
   
   docker run -d \
     --name promptoptimizer \
     --restart unless-stopped \
     -p 8000:8000 \
     --env-file /home/ubuntu/.env.production \
     -v /home/ubuntu/uploaded_kb:/app/uploaded_kb \
     ${ECR_REGISTRY}/jpo-images:${PREVIOUS_TAG}
   ```

5. **Verify it's working:**
   ```bash
   curl http://localhost:8000/health
   docker logs -f promptoptimizer
   ```

---

### **Method 3: Pull Specific Version from ECR**

1. **Find the working commit SHA from GitHub:**
   - Go to GitHub → Actions → Find last successful deployment
   - Note the commit SHA

2. **SSH to EC2 and pull that version:**
   ```bash
   ssh ubuntu@YOUR_EC2_IP
   
   ECR_REGISTRY="<YOUR_ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com"
   WORKING_SHA="abc123"  # Replace with actual SHA
   
   # Login to ECR
   aws ecr get-login-password --region <REGION> | \
     docker login --username AWS --password-stdin ${ECR_REGISTRY}
   
   # Pull specific version
   docker pull ${ECR_REGISTRY}/jpo-images:${WORKING_SHA}
   
   # Stop current
   docker stop promptoptimizer && docker rm promptoptimizer
   
   # Run previous version
   docker run -d \
     --name promptoptimizer \
     --restart unless-stopped \
     -p 8000:8000 \
     --env-file /home/ubuntu/.env.production \
     -v /home/ubuntu/uploaded_kb:/app/uploaded_kb \
     ${ECR_REGISTRY}/jpo-images:${WORKING_SHA}
   ```

---

### **Method 4: Database Rollback (if schema changed)**

If you ran migrations that need to be reverted:

1. **SSH to EC2:**
   ```bash
   ssh ubuntu@YOUR_EC2_IP
   ```

2. **Downgrade database:**
   ```bash
   docker exec -it promptoptimizer alembic downgrade -1
   # Or to specific revision:
   # docker exec -it promptoptimizer alembic downgrade <revision_id>
   ```

3. **Restart container with old code:**
   ```bash
   # Follow Method 2 or 3 above
   ```

---

## 🛡️ Prevention: Always Keep Last 5 Versions

Add this to your EC2 deployment script (in GitHub Actions workflow):

```yaml
- name: Keep last 5 images
  run: |
    # Don't prune images less than 120 hours old (5 days)
    docker image prune -af --filter "until=120h"
```

---

## 📊 Verify Rollback Success

```bash
# Check container is running
docker ps | grep promptoptimizer

# Check logs for errors
docker logs promptoptimizer --tail 100

# Test health endpoint
curl http://localhost:8000/health

# Check API response
curl http://localhost:8000/docs
```

---

## 🚨 Emergency Contacts Checklist

When rollback is needed:
- [ ] Identify what broke (check logs)
- [ ] Note the broken commit SHA
- [ ] Note the last working commit SHA
- [ ] Execute rollback
- [ ] Verify application is working
- [ ] Notify team
- [ ] Create incident report
- [ ] Fix issue in development branch
- [ ] Test thoroughly before re-deploying

---

## 📝 Post-Rollback Actions

1. **Create GitHub Issue** documenting:
   - What broke
   - When it happened
   - How you fixed it
   - What to prevent it in the future

2. **Improve Tests** to catch the issue earlier

3. **Add Monitoring** if issue wasn't detected quickly

4. **Update Runbook** with lessons learned

---

## 🔍 Debugging Commands

```bash
# View all container logs
docker logs promptoptimizer

# Follow logs in real-time
docker logs -f promptoptimizer

# Check container resource usage
docker stats promptoptimizer

# Inspect container configuration
docker inspect promptoptimizer

# Check network connectivity
docker exec promptoptimizer curl http://localhost:8000/health

# Access container shell
docker exec -it promptoptimizer /bin/bash
```

---

## ⏱️ Rollback Time Estimates

- **Method 1 (GitHub Actions)**: 3-5 minutes
- **Method 2 (Manual EC2)**: 1-2 minutes
- **Method 3 (ECR Pull)**: 2-3 minutes
- **Method 4 (With DB)**: 5-10 minutes

**Target: < 5 minutes for critical rollback**
