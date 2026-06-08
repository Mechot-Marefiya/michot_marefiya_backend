# AGENTS.md

## Purpose

This file is for Codex agents working in `michot_marefiya_backend`.

Use it as the first navigation and decision guide when:

- reviewing the backend
- adding or debugging Django REST APIs
- tracing booking/payment flows
- running targeted tests
- extending features without breaking the mobile-app-facing API contract

This project already serves an app client. Existing request/response shapes, URL paths, auth expectations, and field names should be treated as stable contracts.

If a task would change an existing API contract in a way that could break the app, stop and ask the user before doing it.

## High-Level Architecture

This is a Django 5 + Django REST Framework modular monolith.

- `config/` holds project settings, URL mounting, ASGI/WSGI, and Celery bootstrap.
- `apps/` holds domain apps.
- Business logic is service-heavy.
- DRF views and viewsets usually handle auth, permissions, queryset shaping, and serializer selection.
- Serializers do validation and often create/update related objects.
- Services handle multi-model workflows, transactions, availability changes, pricing, payment confirmation, and side effects.

The most coupled domain is `apps/listing`.

## Core Apps

- `apps/account`: users, roles, companies, hotels, staff, onboarding, auth-adjacent flows
- `apps/core`: shared models, utilities, pagination, currency, facilities, email helpers
- `apps/listing`: listings, inventory, pricing, bookings, terms, seasons, search, workspace features
- `apps/payment`: Chapa initialization, verification, transaction ledger, payout metadata
- `apps/notifications`: notification records, preferences, templates, async email hooks
- `apps/analytics`: overview/revenue/activity/front-desk reporting
- `apps/favorites`: generic favorites and snapshot helpers

## Files To Read First

Read these before making non-trivial backend changes:

- `config/settings/base.py`
- `config/urls.py`
- `apps/core/models.py`
- `apps/core/views.py`
- `apps/account/models.py`
- `apps/account/views.py`
- `apps/listing/models.py`
- `apps/listing/serializers.py`
- `apps/listing/views.py`
- `apps/listing/services.py`
- `apps/payment/models.py`
- `apps/payment/services.py`

## Runtime And Entrypoints

- `manage.py` defaults to `config.settings.dev`
- `config/wsgi.py` defaults to `config.settings.dev`
- `config/asgi.py` defaults to `config.settings.dev`
- tests use `config.settings.test` through `pytest.ini`
- local development is Docker-first via `compose.yaml`
- production compose is `compose.prod.yaml`
- Celery app entrypoint is `config/celery.py`

Important note:

- production entrypoints still default to development settings unless environment overrides `DJANGO_SETTINGS_MODULE`

## API Surface

Root mounting is in `config/urls.py`.

Current top-level namespaces:

- `api/v1/account/`
- `api/v1/core/`
- `api/v1/listing/`
- `api/v1/favorites/`
- `api/v1/payment/`
- `api/v1/analytics/`
- `api/v1/notifications/`
- auth endpoints under `api/v1/auth/`
- schema/docs under `api/schema/` and `api/docs/`

Most REST resources use `DefaultRouter`.
Most viewsets inherit `AbstractModelViewSet` from `apps/core/views.py`, which restricts methods to:

- `get`
- `post`
- `patch`
- `delete`

Do not widen method support casually.

## API Stability Rules

Because the backend is consumed by an app:

- do not rename existing endpoints
- do not remove fields from existing responses
- do not change status-code behavior without explicit approval
- do not change serializer output shape for live endpoints unless the user approves it
- do not change auth requirements, throttling behavior, or pagination shape on existing endpoints without asking first
- prefer additive changes such as new endpoints, new optional fields, or new actions
- do not change database coloumns, unless the user approves it
Ask the user before:

- changing path names
- changing payload field names
- changing response nesting
- altering booking, payment, or notification semantics visible to clients
- changing defaults that could affect the app UX

## Shared Patterns

### Models

- most domain models inherit `AbstractBaseModel`
- UUID primary keys are standard across the project
- shared address data lives in `core.Address`
- hotel-level shared facilities live in `core.Facility`
- room/event-level shared amenities live in `listing.Amenity`

### Generic Relations

Generic relations are part of the design, not an exception.

Existing uses include:

- `account.ListingImage`
- `favorites.Favorite`
- `payment.PaymentTransaction.booking_object`
- `listing.TermsAndConditions`
- `account.User.workspace`

When extending these areas, prefer preserving the `ContentType` / `GenericForeignKey` pattern instead of adding per-model special cases.

### Views And Serializers

- views commonly switch serializer classes by action
- serializers often normalize nested payloads and call service-layer methods
- nearby endpoints usually show the expected permission and throttle style
- drf-spectacular decorators are used for schema documentation

### Services

Service classes are the real source of truth for business behavior.

Examples:

- `ListingService`
- `StayAvailabilityService`
- `GuestHouseBookingService`
- `BookingService`
- `CarRentalService`
- `EventSpaceBookingService`
- `TermsService`
- `ChapaPaymentService`
- analytics and notification service modules

Before changing a serializer or view, inspect the relevant service file first.

## Domain Map

### Account

- custom user model uses `email` as `USERNAME_FIELD`
- role codes live in `apps/account/enums.py`
- users can belong to a `CompanyProfile` or an `IndividualOwnerProfile`
- `HotelProfile` belongs to a company
- staff can carry a generic `workspace`

Main navigation files:

- `apps/account/models.py`
- `apps/account/serializers.py`
- `apps/account/views.py`
- `apps/account/permissions.py`

### Listing

This is the largest app and highest-risk area.

Main families:

- Hotels: `HotelProfile` -> `RoomListing` -> `StayAvailability` -> `Booking` and `BookingItem`
- Guest houses: `GuestHouseProfile` -> `GuestHouseRoom` -> `GuestHouseInventory` -> `GuestHouseBooking`
- Event spaces: `EventSpaceListing` -> `EventSpaceAvailability` -> `EventSpaceBooking`
- Cars: `CarListing` -> `CarAvailability` -> `CarRental`
- Properties: `PropertyListing`

Supporting concepts:

- terms and conditions
- addon offerings
- booking addons
- seasons and seasonal rates
- booking snapshots
- price preview and currency conversion helpers

Main navigation files:

- `apps/listing/models.py`
- `apps/listing/serializers.py`
- `apps/listing/views.py`
- `apps/listing/services.py`
- `apps/listing/tests/`

### Payment

- Chapa integration lives in `apps/payment/services.py`
- transaction model is `PaymentTransaction`
- payment supports multiple booking types via generic relation
- ledger endpoints are owner-facing and read-only

Main navigation files:

- `apps/payment/models.py`
- `apps/payment/serializers.py`
- `apps/payment/views.py`
- `apps/payment/services.py`

### SMS

- all SMS delivery must go through `services/sms.py`
- do not import or call AfroMessage directly from views, serializers, models, or tasks
- the working AfroMessage send contract uses the hardcoded send URL, `AFRO_MESSAGE_TOKEN`, `AFRO_MESSAGE_IDENTIFIER_ID`, Ethiopian phone normalization to `251...`, and an empty `sender` query parameter
- do not restore `AFRO_MESSAGE_URL`; see `Agents/SMS_SERVICE.md` before changing SMS behavior
- tests must mock `services.sms.send_sms` and must not hit the real provider

### Notifications

- notifications are stored as first-class records
- preferences and templates are in the database
- services centralize creation and state transitions

### Analytics

- overview, revenue, activity, and front-desk reporting live here
- there are both online query helpers and pre-aggregation components
- check both `services.py` and `services_frontdesk.py` when changing analytics behavior

## Booking And Payment Lifecycle

When reasoning about booking-like flows, trace all of these:

1. input validation
2. availability validation
3. row locking where needed
4. reservation/decrement of available units
5. terms acceptance and snapshotting
6. booking snapshot generation
7. payment transaction creation
8. callback/webhook verification
9. booking confirmation
10. notification and email side effects
11. cancellation or payment failure release path

If adding a new booking-type workflow, mirror the full lifecycle instead of implementing only the create endpoint.

## Where To Start For Common Tasks

### Add A New API Endpoint

1. find the app router in `apps/*/urls.py`
2. inspect the target view or nearby viewset in `views.py`
3. inspect serializer create/update/validation methods
4. inspect service methods used by those serializers/views
5. inspect existing tests in the same app
6. implement the smallest additive change possible

### Change Booking Behavior

Read in this order:

1. `apps/listing/views.py`
2. `apps/listing/serializers.py`
3. `apps/listing/services.py`
4. `apps/payment/services.py`
5. relevant tests in `apps/listing/tests/` and `apps/payment/tests/`

### Change Payment Behavior

Read in this order:

1. `apps/payment/views.py`
2. `apps/payment/serializers.py`
3. `apps/payment/services.py`
4. `apps/payment/models.py`
5. related booking confirmation methods in `apps/listing/services.py`

### Change Owner-Scoped Or Workspace Features

Always account for both ownership paths when relevant:

- `company`
- `individual_owner`

Also check staff workspace behavior in `apps/account/views.py` and `account.User.workspace`.

## Testing Guidance

Pytest is already configured:

- `pytest.ini` sets `DJANGO_SETTINGS_MODULE = config.settings.test`
- tests run with `--nomigrations`
- repo-wide coverage is enabled by default in pytest addopts

Main test folders:

- `apps/account/tests`
- `apps/core/tests`
- `apps/listing/tests`
- `apps/payment/tests`
- `apps/notifications/tests`
- `apps/analytics/tests`

High-value targeted test commands:

- `pytest apps/account/tests`
- `pytest apps/core/tests`
- `pytest apps/listing/tests`
- `pytest apps/payment/tests`
- `pytest apps/notifications/tests`
- `pytest apps/analytics/tests`

When changing:

- bookings: add or update listing tests
- pricing: add or update price preview / pricing tests
- payments: add or update payment tests plus booking confirmation coverage
- favorites: verify both serializer output and snapshot behavior
- analytics: verify auth requirements and returned aggregates

## Local Dev Commands

Typical Docker workflow:

- `docker compose up --build`
- `docker compose exec api python manage.py migrate`
- `docker compose exec api python manage.py createsuperuser`
- `docker compose exec api pytest`

Useful management command areas:

- `apps/core/management/commands`
- `apps/listing/management/commands`
- `apps/payment/management/commands`
- `apps/notifications/management/commands`
- `apps/analytics/management/commands`

## Performance And Query Hygiene

When adding fields to list/detail endpoints:

- preserve existing `select_related` / `prefetch_related` patterns
- avoid deep nested serializer additions on hot listing endpoints
- be careful with favorites and image lookups to avoid N+1 queries
- keep price preview and currency conversion logic centralized

## Known Codebase Hazards

These are worth remembering before building on top of them:

- `GuestHouseAvailabilityService` is defined twice in `apps/listing/services.py`; the later class overwrites the earlier import target.
- `manage.py`, `config/wsgi.py`, and `config/asgi.py` all default to `config.settings.dev`, which is risky for production if env overrides are missing.
- `StaffViewSet.available_workspaces()` references `car.make`, but `CarListing` uses `brand`.
- `WorkspaceStatusService` in `apps/listing/services.py` uses Python `sum('field_name')` inside ORM aggregates instead of `django.db.models.Sum`.
- favorites thumbnail snapshot logic checks `first.file`, while listing images use the `image` field.
- `apps/payment/services.py` contains duplicated Chapa initialize logic after `cancel_transaction`, which makes the file harder to maintain safely.

Treat these as existing hazards, not good patterns to copy.

## Safe Working Rules For Codex

- prefer reading the relevant service file before changing views or serializers
- assume `apps/listing/services.py` is the highest-coupling file in the repo
- keep changes additive unless the user explicitly asks for a refactor
- preserve public API contracts for the app
- ask before making breaking API changes
- verify generic relation paths end-to-end when touching images, favorites, terms, or payments
- when touching payments, trace both initiate and verify/callback flows
- when touching bookings, verify cancellation and release behavior too
- when touching owner-facing features, test both company-backed and individual-owner-backed cases
- when touching deployment or settings, inspect `manage.py`, `asgi.py`, `wsgi.py`, `compose.yaml`, and `compose.prod.yaml` together

## Recommended Review Workflow For Future Tasks

For most backend tasks, this sequence is reliable:

1. read the router
2. read the target view/viewset
3. read the serializer(s)
4. read the service(s)
5. read the related model(s)
6. read the existing tests
7. implement
8. run the narrowest relevant tests first
9. only then expand to broader test coverage if needed

## Final Rule

This codebase is already coupled to a client app.

When in doubt:

- prefer additive backend changes
- preserve existing contracts
- extend current patterns instead of inventing new ones
- ask the user before changing behavior that could break the app
