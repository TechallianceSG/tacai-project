# TACAI User Management Security Policy Draft

## Password Rules

- Never store plaintext passwords.
- Store password hashes only.
- Minimum password length: 8 characters.
- Password must include:
  - Uppercase.
  - Lowercase.
  - Number.
- Password expiration: 180 days.

## Login Security

- Implement failed login count.
- Implement account lock after repeated login failures.
- Track last login.
- Track locked date.

## Session Security

Session records must track:

- Session ID.
- User ID.
- Login time.
- Logout time.
- IP address.
- Browser.
- Device.
- Expiration time.

Session timeout must be implemented.

## Audit Security

All actions must be logged.

Audit examples:

- User login.
- User logout.
- Password change.
- Role assignment.
- User creation.
- User deactivation.

Audit records must never be deleted.

## Future Security Requirements

- HTTPS deployment support.
- MFA.
- Microsoft Authenticator.
- Google Authenticator.
- SSO.
- Azure AD.
- Google Workspace.
- Production password hashing policy review.
