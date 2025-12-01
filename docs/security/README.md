# Security Documentation

This document outlines the security features and considerations for My Agent Console.

## Security Architecture

### v0 MVP (Current)

**Local-First Design**:
- All data stored locally in SQLite
- No network exposure by default
- Basic rate limiting per IP
- No authentication (single-user, local-only)

### v1+ (Planned)

- JWT-based authentication
- User management and access control
- Data encryption at rest
- Enhanced rate limiting
- Security monitoring and alerting
- Audit logging

## Current Security Features

### 1. Rate Limiting

Basic rate limiting is implemented to prevent abuse:

- **Per-IP rate limits**: Configurable requests per minute
- **Automatic blocking**: Temporary blocks for excessive requests

### 2. CORS Configuration

CORS is configured to only allow requests from:
- `http://localhost:3000` (development)
- `http://127.0.0.1:3000` (development)

For production, update CORS origins in `backend/app/main.py`.

### 3. Trusted Hosts

The application only accepts requests from:
- `localhost`
- `127.0.0.1`
- `host.docker.internal`

### 4. Input Validation

All API inputs are validated using Pydantic models:
- Type checking
- Required field validation
- Range validation (e.g., progress_percentage 0-100)
- Enum validation

### 5. SQL Injection Prevention

SQLite queries use parameterized statements to prevent SQL injection.

### 6. Error Handling

- Generic error messages to avoid information leakage
- Detailed errors logged server-side only
- No stack traces exposed to clients

## Security Best Practices

### For Users

1. **API Keys**: Keep your LLM API keys secure
   - Never share your `.env` file
   - Use environment variables, not hardcoded keys
   - Rotate keys if compromised

2. **Database Backup**: Regularly backup `data/mindscape.db`
   - This file contains all your personal data
   - Store backups securely

3. **Local Network**: If exposing to network, use firewall rules
   - Default configuration is localhost-only
   - Only expose if necessary

### For Developers

1. **Dependencies**: Keep dependencies updated
   - Regularly run `pip list --outdated`
   - Review security advisories

2. **Secrets Management**: Never commit secrets
   - Use `.env` files (in `.gitignore`)
   - Use environment variables in production

3. **Code Review**: Review all changes for security implications
   - Input validation
   - Authentication/authorization
   - Data exposure

## Known Limitations (v0 MVP)

1. **No Authentication**: Anyone with network access can use the API
   - Mitigation: Run locally only, use firewall rules

2. **No Encryption**: Database is stored in plain SQLite
   - Mitigation: Use filesystem encryption, restrict file permissions

3. **Basic Rate Limiting**: Simple per-IP limits
   - Mitigation: Use reverse proxy with advanced rate limiting

4. **No Audit Logging**: Limited logging of security events
   - Mitigation: Monitor application logs

## Future Security Enhancements (v1+)

1. **JWT Authentication**
   - Token-based authentication
   - Refresh token support
   - Token revocation

2. **Data Encryption**
   - Encrypted database fields
   - Encryption at rest

3. **Advanced Rate Limiting**
   - User-based quotas
   - Sliding window algorithm
   - Distributed rate limiting

4. **Security Monitoring**
   - Anomaly detection
   - Intrusion detection
   - Alert system

5. **Audit Logging**
   - Comprehensive audit trail
   - Security event logging
   - Compliance reporting

## Reporting Security Issues

If you discover a security vulnerability, please:

1. **Do NOT** open a public issue
2. Email security concerns to: [security-email]
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact

We will respond within 48 hours and work with you to resolve the issue.

## Compliance

**v0 MVP**: Not designed for compliance requirements (HIPAA, GDPR, etc.)

**v1+**: Will include compliance features for enterprise deployments.

## Security Checklist

Before deploying to production:

- [ ] Update CORS origins
- [ ] Configure trusted hosts
- [ ] Set strong API keys
- [ ] Enable HTTPS
- [ ] Configure firewall rules
- [ ] Set up database backups
- [ ] Review rate limiting settings
- [ ] Enable security monitoring (v1+)
- [ ] Set up audit logging (v1+)
