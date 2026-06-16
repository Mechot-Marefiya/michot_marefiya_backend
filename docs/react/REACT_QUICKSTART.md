# React Developer Quickstart
# Platform: Michot Marefiya
# Backend: Django REST Framework
# Last updated: 2026-06-16

## 1. What The React App Covers

This frontend serves three distinct user groups with different permissions and dashboards.

Regular users:
- browse listings
- book services
- manage bookings
- view receipts and payment history

Company roles:
- hotel staff manage hotel listings and bookings for their property
- guesthouse staff manage guesthouse listings and bookings
- property managers manage property rental listings
- car sales agents manage car sale listings
- each staff account only sees its own workspace/domain

Individual owners:
- register and manage their own listings
- view bookings and payouts
- review compliance agreement status
- review tax-related payment data, including property rental tax handling

What React does not handle:
- platform admin workflows in Django admin or Jazzmin
- the Flutter mobile app

## 2. Base URLs

Development:
- `http://localhost:8000`

Staging:
- not configured in this repository

Production:
- not configured in this repository

API prefix:
- `/api/v1/`

Swagger UI:
- `http://localhost:8000/api/docs/`

OpenAPI schema:
- `http://localhost:8000/api/schema/`

Django admin:
- `http://localhost:8000/api/admin/`

## 3. Authentication

Type:
- JWT via SimpleJWT

Token obtain endpoint:
- `POST /api/v1/auth/token/`

Request body:

```json
{
  "phone": "0912345678",
  "password": "your-password"
}
```

Response:
- `access`
- `refresh`
- `role`
- optional `company`, `individual_owner`, or `workspace` details depending on the account

Authenticated requests:
- send `Authorization: Bearer <access_token>`

Refresh endpoint:
- `POST /api/v1/auth/token/refresh/`

JWT lifetime in this repo:
- access token: 1 hour in normal runtime, 30 days in `DEBUG`
- refresh token: 1 day in normal runtime, 30 days in `DEBUG`
- refresh token rotation is enabled

Storage recommendation:
- do not hardcode tokens
- prefer the safest client-side storage your architecture allows
- if you later move to httpOnly cookies, that must be implemented server-side

Role detection:
- read the role value from the login response first
- then confirm the current profile payload after login
- the role code values in this codebase are `user`, `admin`, `company`, `individual_owner`, and `front_desk`

## 4. OTP Authentication

Use OTP for phone verification flows when needed.

Endpoints:
- `POST /api/v1/auth/otp/request/`
- `POST /api/v1/auth/otp/verify/`

React should treat OTP as part of the auth journey, guest flow journey, or phone verification journey depending on the endpoint used.

## 5. API Documentation

Use the backend docs before guessing any request or response shape.

Sources of truth:
- `schema.yaml`
- `http://localhost:8000/api/docs/`
- `http://localhost:8000/api/schema/`

Use the schema for:
- exact field names
- request bodies
- response bodies
- pagination shape
- error shape
- role-specific data

## 6. Maps Integration

React should not call mapping providers directly for backend data such as search, nearby listings, geocoding, or place lookups.

Backend map entrypoints:
- `/api/v1/maps/`
- `/api/v1/listing/` search and discovery endpoints

Important repo detail:
- this backend is configured to use `MAP_PROVIDER=geoapify` by default
- React should consume backend map/search responses rather than coupling itself to a vendor API

If the frontend needs a map rendering library key:
- keep it in React environment variables
- restrict it to your frontend domain
- do not commit it to source control

## 7. Payment Integration

Backend handles all Chapa server-side calls.

React responsibilities:
- start the payment flow
- redirect the user to the checkout URL returned by the backend
- handle the return page
- refresh state after payment completes

React should not:
- call Chapa verification directly
- store Chapa secret keys
- perform server-side callbacks or webhooks

Chapa public key:
- inject it into the React app from frontend environment variables only
- do not hardcode it
- do not store the Chapa secret key in React

Test mode:
- use the test public key prefix documented in `Agents/PAYMENT_SERVICE.md`
- test mode uses test cards and test phone numbers only
- test mode does not move real money

If the app uses inline or HTML checkout:
- keep the public key in React runtime environment variables
- verify the checkout flow against the backend docs and the Chapa payment guide

## 8. Role-Based Rendering

After login, render the dashboard that matches the user role.

Role map:
- `user` -> regular booking dashboard
- `company` -> company/staff dashboard
- `front_desk` -> workspace dashboard for the assigned property
- `individual_owner` -> owner dashboard
- `admin` -> admin-only workflows outside the React app

The login response returns the role code.

The current profile payload exposes the role object from the account serializer, so React should not guess based on email or workspace name.

## 9. Admin Verification Badge

Verified listings show `is_verified: true`.

React should:
- show a verified badge on listing cards and detail pages
- not provide verification actions
- treat verification as a read-only status for the frontend

## 10. Error Response Shape

Validation errors:
- `{ "field_name": ["error message"] }`

General errors:
- `{ "detail": "message" }`

HTTP status behavior:
- `200` for successful reads and some successful actions
- `201` for created resources
- `400` for validation errors
- `401` for unauthenticated requests
- `403` for forbidden requests
- `404` for missing resources
- `500` for server errors

React behavior:
- redirect to login on `401`
- show a permission message on `403`
- show a not-found screen on `404`
- show a generic fallback on `500`

## 11. Pagination

Most list endpoints are paginated.

Common response shape:

```json
{
  "count": 100,
  "current_page": 1,
  "page_size": 10,
  "total_pages": 10,
  "next": "url-or-null",
  "previous": "url-or-null",
  "results": []
}
```

Default page size in settings:
- `10`

React should:
- use the backend pagination links
- not invent page math unless the endpoint explicitly requires it

## 12. Date And Time

Use ISO 8601 everywhere.

Display rules:
- treat backend timestamps as UTC
- convert to local time in the UI only when rendering
- keep the original server value in state when possible

## 13. Running Locally

Backend clone and startup:

```bash
git clone <REPOSITORY_URL> michot_marefiya_backend
cd michot_marefiya_backend
cp .env.example .env
docker compose up --build -d
docker compose exec api python manage.py migrate
docker compose exec api python manage.py seed_data --clear --seed 20260616 --days 45
```

Useful local URLs:
- backend: `http://localhost:8000`
- Swagger: `http://localhost:8000/api/docs/`
- schema: `http://localhost:8000/api/schema/`

If you are building the React app in a separate frontend repo, set its local API base URL to:
- `http://localhost:8000`

Suggested React environment variables:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_NAME=Michot Marefiya
VITE_MAPS_KEY=your-frontend-map-key-if-needed
VITE_CHAPA_PUBLIC_KEY=your-chapa-public-key-if-needed
```

Do not put backend secret keys in React.

## 14. Day-One Checklist

Before writing code:
- confirm the backend is running
- confirm `schema.yaml` opens and matches the app flow you are building
- log in with a seeded account
- fetch the current profile and confirm the `role` value
- inspect at least one list endpoint and one detail endpoint in Swagger
- confirm the payment flow and map flow you plan to use are documented in the backend schema

If anything in the backend looks unclear:
- trust `schema.yaml` first
- trust the backend docs second
- ask before changing request or response shapes
