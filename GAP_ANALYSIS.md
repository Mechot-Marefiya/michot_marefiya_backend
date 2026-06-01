# GAP_ANALYSIS

## ✅ Already Implemented (Verify Only)

### 1. Multi-domain listing modules (hotels, guesthouses, event spaces, car rentals, properties)
- Feature name: Core listing domains and CRUD APIs.
- Endpoint(s) or component(s) involved: `apps.listing` models (`RoomListing`, `GuestHouseProfile`, `EventSpaceListing`, `CarListing`, `PropertyListing`), viewsets under `/api/v1/listing/*`, hotel profile APIs under `/api/v1/account/hotels/*`.
- Test coverage status: covered (listing creation and key domain flows are covered in `apps/listing/tests/test_listing.py` and related booking tests).
- Flutter API contract: yes.

### 2. Company onboarding with admin approval workflow
- Feature name: Company registration and approval/rejection.
- Endpoint(s) or component(s) involved: `/api/v1/account/companies/`, `/api/v1/account/companies/apply/`, `/api/v1/account/companies/{pk}/approve/`, `/api/v1/account/companies/{pk}/reject/`; `CompanyProfile.status`, `approved_at`, `approved_by`, `rejection_reason`.
- Test coverage status: covered (signup/registration flows covered in account tests; approval endpoints themselves are largely uncovered).
- Flutter API contract: yes.

### 3. Booking lifecycle with availability checks and pending status
- Feature name: Booking creation with availability validation and pending-first flow.
- Endpoint(s) or component(s) involved: booking endpoints for hotel/guesthouse/event/car; service layer in `apps.listing/services.py` (`BookingService`, `GuestHouseBookingService`, `EventSpaceBookingService`, `CarRentalService`).
- Test coverage status: covered (hotel and guesthouse booking suites cover create/cancel/overbooking behaviors).
- Flutter API contract: yes.

### 4. Terms & Conditions versioning and booking snapshots
- Feature name: T&C version archive and immutable booking-time acceptance snapshot.
- Endpoint(s) or component(s) involved: `TermsAndConditions` model, `/api/v1/listing/terms/*`, booking fields (`terms_accepted`, `terms_version`, `terms_accepted_at`, content snapshot fields).
- Test coverage status: covered (`apps/listing/tests/test_terms_conditions.py` and payment/T&C sync tests).
- Flutter API contract: yes.

### 5. Seasonal pricing and rate overrides
- Feature name: Seasonal pricing engine with priority and optional day-of-week targeting.
- Endpoint(s) or component(s) involved: `Season`, `SeasonalRate`, `/api/v1/listing/seasons/*`, `/api/v1/listing/seasonal-rates/*`, pricing services and preview flows.
- Test coverage status: covered for pricing behavior; uncovered for season CRUD endpoints directly.
- Flutter API contract: yes.

### 6. Add-on support and pricing separation at model level
- Feature name: Add-on offerings and booking add-on line items.
- Endpoint(s) or component(s) involved: `AddonOffering`, `BookingAddon`, `/api/v1/listing/addon-offerings/*`, hotel add-on read endpoint `/api/v1/account/hotels/{pk}/addons/`.
- Test coverage status: partially covered (pricing suites touch add-on behavior; addon CRUD endpoints are mostly uncovered).
- Flutter API contract: yes.

### 7. Walk-in booking support
- Feature name: Staff-initiated walk-in booking endpoints.
- Endpoint(s) or component(s) involved: `/api/v1/listing/bookings/walk-in/`, `/api/v1/listing/guesthouse-bookings/walk-in/`, `/api/v1/listing/bookings-eventspaces/walk-in/`.
- Test coverage status: partially covered (mainly uncovered at endpoint level).
- Flutter API contract: yes.

### 8. Payment gateway integration (Chapa) and transaction ledger
- Feature name: Chapa initialize/verify/callback/webhook plus owner ledger.
- Endpoint(s) or component(s) involved: `/api/v1/payment/initiate/`, `/api/v1/payment/verify/{tx_ref}/`, `/api/v1/payment/verify-public/{tx_ref}/`, `/api/v1/payment/callback/chapa/`, `/api/v1/payment/webhook/chapa/`, `/api/v1/payment/ledger/*`; `PaymentTransaction`; `ChapaPaymentService`.
- Test coverage status: partially covered (guesthouse payment initiation covered; most payment endpoints uncovered).
- Flutter API contract: yes.

### 9. Favorites with snapshot persistence
- Feature name: Save listing snapshot at favorite-time.
- Endpoint(s) or component(s) involved: `/api/v1/favorites/*`, `Favorite.snapshot`, serializer snapshot builder.
- Test coverage status: covered (favorites integration tests exist).
- Flutter API contract: yes.

### 10. Availability counters and auto-release/cancel tasks
- Feature name: Day-level availability tracking plus expiry cancellation automation.
- Endpoint(s) or component(s) involved: stay/car/guesthouse availability models, booking cancel services, celery tasks (`auto_cancel_pending_booking`, `auto_cancel_pending_guesthouse_booking`, `cancel_all_expired_bookings`).
- Test coverage status: covered for major booking cancel/release flows; task execution paths mostly uncovered.
- Flutter API contract: yes.

### 11. Vendor analytics endpoints
- Feature name: Owner/company analytics API surface.
- Endpoint(s) or component(s) involved: `/api/v1/analytics/company/overview/`, `/api/v1/analytics/company/revenue/`, `/api/v1/analytics/company/activity/`, `/api/v1/analytics/frontdesk/stats/`, `/api/v1/analytics/frontdesk/availability/`.
- Test coverage status: partially covered (auth checks covered for selected endpoints; response behavior mostly uncovered).
- Flutter API contract: yes.

### 12. Notification center and user notification preferences
- Feature name: In-app notifications CRUD-style operations with preference API.
- Endpoint(s) or component(s) involved: `/api/v1/notifications/*`, `/api/v1/notifications/preferences/`, `Notification`, `NotificationPreference`, async `send_notification_email_task`.
- Test coverage status: uncovered at API level (service tests exist).
- Flutter API contract: yes.

### 13. ETB-first pricing with multi-currency conversion helper APIs
- Feature name: Currency rates and conversion APIs used by listing responses.
- Endpoint(s) or component(s) involved: `/api/v1/core/currencies/`, `/api/v1/core/currencies/rates/`, `/api/v1/core/currency/convert/`, serializer conversion mixins.
- Test coverage status: covered (core currency API tests).
- Flutter API contract: yes.

## 🔧 Needs Modification

### 1. Authentication method (phone OTP as primary)
- What exists now (current behavior): JWT login is email/password based (`/api/v1/auth/token/`), with email verification and email password-reset flows.
- What the PRD requires (delta only): phone number + OTP as primary login and verification path; email must be optional/secondary.
- Endpoint(s) affected: `/api/v1/auth/token/`, `/api/v1/account/password-reset/`, `/api/v1/account/verify-email/`, and related account creation/auth endpoints.
- Flutter API impact: BREAKING.
- Test changes required: add auth suite for OTP request/verify/login/refresh/logout + migration tests for legacy email accounts.

### 2. User registration channel and verification
- What exists now (current behavior): standard user signup via email/password serializer; phone exists but is not OTP-gated.
- What the PRD requires (delta only): phone-first registration and phone verification for core account activation and booking legitimacy checks.
- Endpoint(s) affected: `/api/v1/account/users/`, auth endpoints, booking create flows for guest and registered users.
- Flutter API impact: BREAKING.
- Test changes required: signup validation by phone OTP, duplicate-phone controls, and phone verification lifecycle tests.

### 3. Guest conversion to registered user
- What exists now (current behavior): guest-capable booking models exist with `guest_phone`; no explicit conversion endpoint/flow transferring history to a new user via OTP proof.
- What the PRD requires (delta only): explicit guest-to-user conversion that migrates/links booking history by phone with OTP confirmation.
- Endpoint(s) affected: booking APIs (`/api/v1/listing/bookings/*`, `/guesthouse-bookings/*`, `/car-rentals/*`, `/bookings-eventspaces/*`) plus new account conversion endpoint.
- Flutter API impact: non-breaking for existing booking endpoints; new endpoint needed.
- Test changes required: conversion success, idempotency, ownership transfer, and fraud/OTP failure cases.

### 4. Individual owner onboarding governance
- What exists now (current behavior): public individual-owner registration endpoint exists.
- What the PRD requires (delta only): individual owners must be created manually by admin after in-person verification; no public self-register path.
- Endpoint(s) affected: `/api/v1/account/individual-owners/` create path.
- Flutter API impact: BREAKING.
- Test changes required: endpoint permission/auth behavior change tests and admin-only creation tests.

### 5. Listing verification model and display tags across all listing types
- What exists now (current behavior): listing activation exists (`is_active`), company approval exists; no universal verified/unverified tag + verification date per listing type.
- What the PRD requires (delta only): verified badge state and verification date for every listing type, independent of visibility activation.
- Endpoint(s) affected: listing serializers and list/detail endpoints across hotels, guesthouses, event spaces, cars, properties.
- Flutter API impact: non-breaking if additive fields; BREAKING only if replacing existing status fields.
- Test changes required: serializer output tests for verification fields and admin verification action tests.

### 6. Listing visibility policy for new submissions
- What exists now (current behavior): many public list endpoints filter `is_active=True`; behavior is not uniformly enforced per PRD policy language for all listing domains at submission time.
- What the PRD requires (delta only): all customer-submitted listings should default inactive until admin activates; verification is separate.
- Endpoint(s) affected: listing create serializers/services and list querysets for all listing families.
- Flutter API impact: non-breaking (behavioral tightening, no contract rename required).
- Test changes required: default inactive creation tests for each listing type and admin activation coverage.

### 7. First booking service-fee waiver by phone identity
- What exists now (current behavior): service/platform fee logic exists in pricing; no global “first booking free per phone number” rule enforced across guest and registered contexts.
- What the PRD requires (delta only): waive service fee for first booking tied to phone number, including guest and user flows.
- Endpoint(s) affected: price-preview and booking creation endpoints across hotel/guesthouse/event/car rental; payment initialization amount calculation.
- Flutter API impact: non-breaking (response values change, shape can stay).
- Test changes required: cross-domain pricing tests for first booking waiver and anti-abuse edge cases.

### 8. User phone-change abuse controls
- What exists now (current behavior): no explicit limit of three phone changes and one-week cooldown policy.
- What the PRD requires (delta only): max-change count and cooldown policy enforcement.
- Endpoint(s) affected: user profile update endpoints (`/api/v1/account/users/me/` and user update paths).
- Flutter API impact: non-breaking if additive error codes/messages; BREAKING only if field semantics change.
- Test changes required: policy enforcement tests for count limits and cooldown window.

### 9. Car rental compliance rules
- What exists now (current behavior): generic car rental booking exists without explicit “with-driver vs without-driver” product split, without-driver doc gate, code-3 + business-license enforcement, or owner-defined pre-rental form handling.
- What the PRD requires (delta only): enforce those rule branches in booking/validation flow.
- Endpoint(s) affected: `/api/v1/listing/cars/*`, `/api/v1/listing/car-rentals/*`.
- Flutter API impact: non-breaking if additive fields/validation gates; BREAKING if required request schema changes existing fields.
- Test changes required: matrix tests by rental mode, compliance document requirements, and eligibility rules.

### 10. Car rental date-change feature after booking
- What exists now (current behavior): cancel/confirm and CRUD-like update exist; no explicit controlled post-booking date-change workflow with availability-safe item-level checks.
- What the PRD requires (delta only): renter can adjust dates when target slots are available.
- Endpoint(s) affected: `/api/v1/listing/car-rentals/{pk}/` or dedicated reschedule action endpoint.
- Flutter API impact: non-breaking if new action endpoint; BREAKING if existing update schema semantics are redefined.
- Test changes required: reschedule availability checks, pricing recalculation, and race-condition tests.

### 11. Guest booking legitimacy OTP
- What exists now (current behavior): guest bookings allow phone fields but no OTP challenge/confirmation sequence in booking create flow.
- What the PRD requires (delta only): OTP verification for booking using submitted phone.
- Endpoint(s) affected: guest-permitted create endpoints across booking domains.
- Flutter API impact: BREAKING if immediate create flow changes from single-step to OTP-gated multi-step.
- Test changes required: OTP pending state, verified completion, timeout/retry, and abuse throttling tests.

### 12. Booking date forward restriction window
- What exists now (current behavior): no explicit configurable “cannot book check-in beyond N days” restriction policy endpoint/setting.
- What the PRD requires (delta only): configurable restriction (default 5 days), owner/admin controlled by category/listing scope.
- Endpoint(s) affected: booking create and price preview endpoints, plus settings/config endpoint(s).
- Flutter API impact: non-breaking if validation-only; no shape change required.
- Test changes required: boundary tests by configured window and role-based configuration tests.

### 13. No-refund rule enforcement and user-facing messaging
- What exists now (current behavior): cancel endpoints exist; payment cancel exists; explicit no-refund contract enforcement path is not clearly codified as dedicated policy responses/state.
- What the PRD requires (delta only): platform-level no-refund policy enforcement and explicit communication.
- Endpoint(s) affected: payment cancel/refund-related paths and booking cancellation response messaging.
- Flutter API impact: non-breaking if additive policy fields/messages; BREAKING if existing cancellation outcome semantics change.
- Test changes required: ensure no refund transaction path and expected policy messages.

### 14. Payment split scope and walk-in fee semantics
- What exists now (current behavior): split logic exists; walk-in booking endpoints exist; exact PRD rule boundaries (no platform commission for walk-ins, Chapa fee handling nuance) need explicit verification and possible adjustment.
- What the PRD requires (delta only): strict split on booking amount only (not add-ons) and walk-in exclusion from platform commission.
- Endpoint(s) affected: pricing services + payment initialization and booking confirmation routines.
- Flutter API impact: non-breaking (monetary outcome adjustment).
- Test changes required: split arithmetic tests including add-ons and walk-in scenarios.

### 15. Notification channels (SMS/push) and channel-level preferences
- What exists now (current behavior): in-app notification models and API exist; email async task exists; SMS/push dispatch and channel preference granularity are not implemented.
- What the PRD requires (delta only): dual-channel delivery (in-app + SMS/push) with configurable per-channel preference.
- Endpoint(s) affected: `/api/v1/notifications/preferences/`, notification service/task orchestration.
- Flutter API impact: non-breaking if additive preference fields.
- Test changes required: channel dispatch tests, preference filtering tests, and delivery-failure fallback tests.

### 16. Saved-listing deletion alert
- What exists now (current behavior): favorites snapshot exists; no explicit automatic notification trigger when a favorited listing is deleted and not booked.
- What the PRD requires (delta only): notify users when saved listing becomes unavailable.
- Endpoint(s) affected: listing delete flows + notifications service integration.
- Flutter API impact: non-breaking.
- Test changes required: deletion-trigger notification integration tests.

### 17. Analytics computation model (background precompute guarantee)
- What exists now (current behavior): analytics APIs and dirty-date models/signals exist; architecture is partially precompute-aware but not fully guaranteed for all reported metrics.
- What the PRD requires (delta only): background precomputed analytics as primary source for fast dashboard loads.
- Endpoint(s) affected: analytics services, celery tasks/beat pipeline, analytics endpoints.
- Flutter API impact: non-breaking if response shape unchanged.
- Test changes required: materialization job tests, freshness tests, and endpoint read-from-aggregate tests.

## 🆕 Net New

### 1. Car sales connector flow
- Feature name and description: Car sale listing and paid contact reveal flow where transaction closes off-platform.
- Suggested app to add it to: `apps.listing` + `apps.payment`.
- Models needed (new or extended): `CarSaleListing`, `ContactRevealRequest`, `ContactRevealTransaction` (or extend `PaymentTransaction` with reveal type).
- Endpoints to create (METHOD /path/): `GET/POST /api/v1/listing/car-sales/`, `GET /api/v1/listing/car-sales/{pk}/`, `POST /api/v1/listing/car-sales/{pk}/request-contact/`, `GET /api/v1/listing/car-sales/{pk}/contact/`.
- Celery tasks required (if any): async notification task after successful contact reveal.
- Flutter API contract to establish: listing detail shape + contact-reveal payment state machine (`pending_payment`, `paid_revealed`, `expired`).

### 2. House/property sales connector flow
- Feature name and description: Property sale listings with paid contact reveal.
- Suggested app to add it to: `apps.listing` + `apps.payment`.
- Models needed (new or extended): `PropertySaleListing` (or extend property listing with sale mode), `PropertyContactRevealRequest`.
- Endpoints to create (METHOD /path/): `GET/POST /api/v1/listing/property-sales/`, `GET /api/v1/listing/property-sales/{pk}/`, `POST /api/v1/listing/property-sales/{pk}/request-contact/`.
- Celery tasks required (if any): contact reveal notification dispatch.
- Flutter API contract to establish: clear buyer-initiated reveal workflow with reveal-fee payment proof.

### 3. Property rental booking flow (house/apartment rentals)
- Feature name and description: Actual booking lifecycle for property rentals, not only listing CRUD.
- Suggested app to add it to: `apps.listing`.
- Models needed (new or extended): `PropertyRentalBooking`, `PropertyRentalBookingItem` (if multi-unit needed), availability model for property rentals.
- Endpoints to create (METHOD /path/): `POST /api/v1/listing/property-rentals/bookings/`, `GET /api/v1/listing/property-rentals/bookings/{pk}/`, `POST /api/v1/listing/property-rentals/bookings/{pk}/cancel/`, `POST /api/v1/listing/property-rentals/bookings/price-preview/`.
- Celery tasks required (if any): auto-cancel pending property-rental bookings and release availability.
- Flutter API contract to establish: booking payload parity with existing booking domains including terms snapshot and status model.

### 4. 15% tax handling for unlicensed individual property rentals
- Feature name and description: Tax augmentation and remittance-tracking layer for individual-owner property rental transactions.
- Suggested app to add it to: `apps.payment` + `apps.listing`.
- Models needed (new or extended): extend `PaymentTransaction` with `tax_amount`, `tax_rate`, `tax_liability_status`; optional `TaxLedgerEntry`.
- Endpoints to create (METHOD /path/): additive fields on existing payment endpoints; optional admin tax-ledger endpoint `/api/v1/payment/tax-ledger/`.
- Celery tasks required (if any): periodic remittance reconciliation/export task.
- Flutter API contract to establish: price breakdown fields showing `owner_price`, `service_fee`, `tax_amount`, `grand_total`.

### 5. OTP service layer for auth and booking verification
- Feature name and description: reusable OTP issuance/verification for login, signup, and guest booking legitimacy.
- Suggested app to add it to: `apps.account` (or new `apps.identity`).
- Models needed (new or extended): `OtpChallenge` with phone, purpose, code hash, expiry, attempt count.
- Endpoints to create (METHOD /path/): `POST /api/v1/auth/otp/request/`, `POST /api/v1/auth/otp/verify/`, optional `POST /api/v1/account/guests/verify-phone/`.
- Celery tasks required (if any): async SMS delivery task and challenge cleanup task.
- Flutter API contract to establish: challenge token, cooldown metadata, verification result and next-step token.

### 6. Admin listing verification actions with date stamping across all listing types
- Feature name and description: verify/unverify actions and audit metadata for each listing.
- Suggested app to add it to: `apps.listing` + `apps.account` (admin controls).
- Models needed (new or extended): add `is_verified`, `verified_at`, `verified_by`, optional `verification_note` to listing models (or shared mixin).
- Endpoints to create (METHOD /path/): `POST /api/v1/listing/{domain}/{pk}/verify/`, `POST /api/v1/listing/{domain}/{pk}/unverify/`.
- Celery tasks required (if any): none required.
- Flutter API contract to establish: stable verification badge fields included in every listing detail/list response.

### 7. Promotional advertising module
- Feature name and description: admin-managed promotional campaigns for listing/category placement and scheduling.
- Suggested app to add it to: new `apps.promotions` (or `apps.analytics` + `apps.listing` extension).
- Models needed (new or extended): `PromotionCampaign`, `PromotionPlacement`, `PromotionImpression`, `PromotionClick`.
- Endpoints to create (METHOD /path/): admin CRUD under `/api/v1/promotions/*`, plus public read surface for active placements.
- Celery tasks required (if any): campaign activation/deactivation scheduler and aggregation tasks.
- Flutter API contract to establish: ad slot payload shape with campaign metadata and click tracking endpoint contract.

### 8. Platform-admin dashboard metrics endpoints
- Feature name and description: platform-wide operational dashboard (transactions, platform revenue, pending approvals, failed payouts, active listings by category).
- Suggested app to add it to: `apps.analytics`.
- Models needed (new or extended): optional materialized aggregate models for platform totals.
- Endpoints to create (METHOD /path/): `GET /api/v1/analytics/admin/overview/`, `GET /api/v1/analytics/admin/revenue/`, `GET /api/v1/analytics/admin/payout-failures/`.
- Celery tasks required (if any): precompute tasks keyed by event stream or periodic sync.
- Flutter API contract to establish: admin-specific aggregate response schema with time-range controls.

## ⚠️ Flutter API Breaking Change Register

### 1. Auth login contract
- Old contract -> New contract: `POST /api/v1/auth/token/` with `email` + `password` -> phone OTP-first auth flow (`/api/v1/auth/otp/request/` + `/api/v1/auth/otp/verify/`), optionally issuing JWT afterward.
- Migration strategy: add OTP endpoints alongside existing token endpoint, deprecate email/password login in staged releases, then remove in next API version.

### 2. Individual owner public registration
- Old contract -> New contract: `POST /api/v1/account/individual-owners/` publicly available -> admin-only creation path.
- Migration strategy: keep endpoint but return controlled deprecation error for public clients, introduce admin-only backend flow, and version endpoint if client still depends on self-signup behavior.

### 3. Guest booking create single-step flow
- Old contract -> New contract: direct guest booking create on booking endpoints -> OTP-gated guest booking verification step before final booking creation.
- Migration strategy: additive two-phase flow (`precreate` + `confirm`) while preserving old route for a deprecation window; mark old flow deprecated in schema and telemetry-gate shutdown.

### 4. Primary registration identity fields
- Old contract -> New contract: account create centered around email/password fields -> phone-first identity required and OTP validated before account activation.
- Migration strategy: support both payload styles short-term (additive fields), emit warnings for email-primary payloads, then move strict phone-first behavior to `/api/v2/`.
