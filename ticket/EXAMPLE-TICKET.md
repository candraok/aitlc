# DEMO-001 - Update Customer Profile

## Feature Description

A logged-in customer can update their display name from the profile page.

The API endpoint is:

`PATCH /api/customers/me/profile`

The display name is mandatory and must contain 3 to 50 characters.

## Acceptance Criteria

1. A customer can update a valid display name.
2. The API rejects a display name shorter than 3 characters.
3. The API rejects a display name longer than 50 characters.
4. The API rejects an empty display name.
5. An unauthenticated request is rejected.
6. After a successful update, the new display name is persisted and returned by the profile endpoint.

## Additional Technical Information

- Authentication: Bearer token
- UI route: Profile > Edit Profile
- HTTP status for success: 200
- Validation errors: 400
- Authentication error: 401
