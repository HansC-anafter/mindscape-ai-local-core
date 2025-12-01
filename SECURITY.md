# Security Policy

## Supported Versions

We currently support the following versions with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public issue. Instead, please report it privately:

1. **Email**: [security@mindscape.ai] (or create a private security advisory on GitHub)
2. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within **48 hours** and work with you to resolve the issue responsibly.

## Security Features

### Current (v0.1)

- **Local-First Design**: All data stored locally in SQLite
- **No Network Exposure**: Default configuration is localhost-only
- **Input Validation**: All API inputs validated using Pydantic models
- **SQL Injection Prevention**: Parameterized queries
- **Rate Limiting**: Basic per-IP rate limiting
- **CORS Protection**: Restricted to localhost by default

### Known Limitations

1. **No Authentication**: Anyone with network access can use the API
   - **Mitigation**: Run locally only, use firewall rules
   - **Future**: JWT-based authentication (v1+)

2. **No Encryption**: Database stored in plain SQLite
   - **Mitigation**: Use filesystem encryption, restrict file permissions
   - **Future**: Encryption at rest (v1+)

3. **Basic Rate Limiting**: Simple per-IP limits
   - **Mitigation**: Use reverse proxy with advanced rate limiting
   - **Future**: Advanced rate limiting (v1+)

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

4. **File Permissions**: Restrict database file permissions
   ```bash
   chmod 600 data/mindscape.db
   ```

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

## Security Checklist

Before deploying to production:

- [ ] Update CORS origins in `backend/app/main.py`
- [ ] Configure trusted hosts
- [ ] Set strong API keys
- [ ] Enable HTTPS (if exposing to network)
- [ ] Configure firewall rules
- [ ] Set up database backups
- [ ] Review rate limiting settings
- [ ] Restrict database file permissions

## Future Security Enhancements

1. **JWT Authentication** (v1+)
   - Token-based authentication
   - Refresh token support
   - Token revocation

2. **Data Encryption** (v1+)
   - Encrypted database fields
   - Encryption at rest

3. **Advanced Rate Limiting** (v1+)
   - User-based quotas
   - Sliding window algorithm

4. **Security Monitoring** (v1+)
   - Anomaly detection
   - Intrusion detection
   - Alert system

5. **Audit Logging** (v1+)
   - Comprehensive audit trail
   - Security event logging

## Compliance

**v0.1**: Not designed for compliance requirements (HIPAA, GDPR, etc.)

**v1+**: Will include compliance features for enterprise deployments.

---

**Last updated**: 2025-12-02

