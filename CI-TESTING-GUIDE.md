# CI Testing Quick Reference

## 🚀 What happens when you create a PR?

1. **Automatic Build**: GitHub Actions automatically builds your Docker Compose stack
2. **Service Health Checks**: Waits for PostgreSQL, Redis, and app server to be ready
3. **Endpoint Testing**: Tests all major visualization pages to ensure they load
4. **Error Detection**: Scans logs for critical errors and reports them
5. **Status Report**: Shows green ✅ or red ❌ status on your PR

## 🔍 What gets tested?

### Source connection regression checks

Run the focused checks with `pytest` through `uv`, which installs the application
and development dependencies. Set `QUERY_TEST_DSN` to a disposable PostgreSQL 14+
database running on Linux (for disconnect polling support):

```bash
QUERY_TEST_DSN="host=localhost port=5432 dbname=postgres user=postgres password=test" \
  uv run pytest tests/test_query_cancellation.py -v
```

Without `QUERY_TEST_DSN`, `uv run pytest` collects and skips these database-backed
tests. They can also be collected without a database using
`uv run pytest tests/test_query_cancellation.py --collect-only`.

The tests create and remove isolated schemas. They check server-side streaming,
timeout rollback without Celery retries, connection settings and reuse, prefork
pool isolation, and cleanup of a running query after its client is killed.

### Pages tested on every PR:
- `/` - Welcome page
- `/contributions` - Contribution metrics
- `/contributors/contribution_types` - Contributor type analysis
- `/contributors/behavior` - Contributor behavior patterns
- `/chaoss` - CHAOSS metrics
- `/codebase` - Codebase analysis
- `/affiliation` - Organization affiliation data
- `/info` - Information and definitions
- `/repo_overview` - Repository overview

### Health checks:
- Database connectivity
- Redis cache availability
- Application server responsiveness
- Service startup order

## 🛠️ For Developers

### Testing locally before PR:

**Option 1: Using Docker (same as CI)**
```bash
# Use the same commands as CI
docker compose up --build -d

# Wait for services
docker compose ps

# Test endpoints manually
curl http://localhost:8080/
curl http://localhost:8080/contributions
curl http://localhost:8080/health

# Check logs
docker compose logs app-server
```

**Option 2: Using Podman (recommended for local development)**
```bash
# Use Podman instead of Docker
podman compose up --build -d

# Wait for services
podman compose ps

# Test endpoints manually (same as Docker)
curl http://localhost:8080/
curl http://localhost:8080/contributions
curl http://localhost:8080/health

# Check logs
podman compose logs app-server
```

> **Note**: CI always uses Docker, but you can use either Docker or Podman locally. Both should produce same results.

### If CI fails:
1. **Check the logs** in the GitHub Actions tab
2. **Look for error patterns** in the "Check application logs" step
3. **Test locally** with the same environment
4. **Fix the issue** and push again

### Adding new pages:
Update `.github/workflows/pr-build-test.yml` to test your new endpoint:
```bash
# Add to "Test application endpoints" step
curl -f -s http://localhost:8080/your-new-page > /dev/null
```

## 🚨 Error Detection Features

### Enhanced logging in debug mode:
- More verbose error messages
- Service status checks
- Database connectivity validation
- Redis connection testing

### Health check endpoint:
```bash
curl http://localhost:8080/health
```
Returns:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2024-01-15 10:30:00"
}
```

## 📊 Understanding CI Results

### ✅ Green (Success):
- All services started correctly
- All endpoints returned HTTP 200
- No critical errors in logs
- Application is ready for review

### ❌ Red (Failure):
- Service startup failed
- Endpoint returned error (4xx/5xx)
- Critical errors found in logs
- Build or dependency issues

### 🟡 Yellow (In Progress):
- Tests are currently running
- Wait for completion before reviewing

## 🔧 Troubleshooting Common Issues

### "Service startup timeout"
- Services took too long to start
- Usually indicates resource constraints or configuration issues
- Check Docker resource limits

### "Database connection failed"
- PostgreSQL service didn't start properly
- Environment variables might be incorrect
- Check database initialization logs

### "Endpoint test failed"
- Application returned error status
- Check application logs for Python exceptions
- Verify all dependencies are properly installed

### "Redis connection failed"
- Redis service startup issue
- Password configuration problem
- Check Redis service logs

## 📈 Best Practices

### Before creating a PR:
1. Test locally with `docker compose up --build` or `podman compose up --build`
2. Check all pages load without errors
3. Review application logs for warnings
4. Ensure new dependencies are reflected in `pyproject.toml` (new dependencies can be added with `uv add`)

### When CI fails:
1. Don't ignore failures - they catch real issues
2. Check logs thoroughly before asking for help
3. Test the fix locally before pushing again
4. Consider if new tests are needed for your changes

### For dependency changes:
1. Pin specific versions in `pyproject.toml` (if needed because a later version causes issues )
2. Monitor nightly test results for compatibility
3. Update documentation if new env vars are needed
4. Test security implications

## 🎯 Goals of CI Testing

- **Catch build issues early** before they reach production
- **Ensure all pages load** without critical errors
- **Validate dependencies** work together correctly
- **Provide fast feedback** to developers
- **Maintain application stability** across changes

The CI system is designed to give you confidence that your changes work correctly and don't break existing functionality. Use it as a safety net and debugging tool!
